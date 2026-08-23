# Deploying Airflow on Minikube (Local GKE Simulation)

## What you're building

Airflow running entirely inside Minikube, the same way it would run on GKE.
No Docker Compose. No hybrid setup. Just Kubernetes.

```
Your laptop
    └── kubectl / browser (port-forwarded)
            │
            ▼
      Minikube Cluster
├── Namespace: airflow
│       ├── airflow-api-server     (pod)
│       ├── airflow-scheduler      (pod)
│       ├── airflow-dag-processor  (pod)
│       ├── airflow-triggerer      (pod)
│       ├── airflow-postgresql     (pod)
│       └── your task pods         (spawned by the KubernetesExecutor)
└── Namespace: default
        └── (no workloads — everything lives in airflow)
```

Tools you'll use:
- **Minikube** — local Kubernetes cluster
- **Helm** — Kubernetes package manager (installs Airflow for you)
- **kubectl** — CLI to interact with the cluster

---

## Prerequisites

Install these before starting:

```bash
# Minikube
brew install minikube        # macOS
# or: https://minikube.sigs.k8s.io/docs/start/

# kubectl
brew install kubectl

# Helm
brew install helm
```

Verify everything works:
```bash
minikube version
kubectl version --client
helm version
```

---

## Step 1 — Start Minikube with enough resources

Airflow needs more headroom than the defaults. Run these commands from the root of your repository:

```bash
colima start --cpu 4 --memory 6 --disk 60
minikube start --cpus=4 --memory=4096 --disk-size=20g
```

> **Note:** If you previously started with less memory, `minikube delete` and recreate —
> you can't change memory on an existing cluster.

Confirm it's running:
```bash
kubectl get nodes
# Should show: minikube   Ready   ...
```

> **Why this matters on GKE:** On a real cluster you'd pick a machine type (e.g. `e2-standard-4`).
> Minikube's `--cpus` and `--memory` flags are the local equivalent.

---

## Step 2 — Create a namespace for Airflow

Namespaces are logical partitions inside a cluster. Keeping Airflow in its own namespace
makes it easier to manage, monitor, and eventually tear down without affecting other workloads.

```bash
kubectl create namespace airflow
```

Confirm:
```bash
kubectl get namespaces
# You should see: airflow, default, kube-system, ...
```

> **Why this matters on GKE:** You'd do the exact same thing. Namespaces are a
> first-class Kubernetes concept, not a Minikube-specific one.

---

## Step 3 — Add the Airflow Helm chart repository

Helm uses repositories (like apt or brew) to fetch charts. Add the official Apache Airflow one:

```bash
helm repo add apache-airflow https://airflow.apache.org
helm repo update
```

You can browse what the chart contains:
```bash
helm show values apache-airflow/airflow > default-values.yaml
```

That file shows every configurable option. You don't need to touch most of it yet.

---

## Step 4 — Create your values file

Instead of modifying the default chart values directly, you override only what you need
in your own `values.yaml`. Create this file inside the `pipelines/` directory:

**`pipelines/k8s/airflow-values.yaml`**
```yaml
# Use the KubernetesExecutor so each task runs as its own pod
# This is the production-standard executor for cloud deployments
executor: KubernetesExecutor

# How Airflow finds your DAGs
# For now: mount them from a local path via a PersistentVolume (see Step 6)
dags:
  persistence:
    enabled: true
    size: 1Gi

# Disable the default example DAGs (optional, keeps things clean)
env:
  - name: AIRFLOW__CORE__LOAD_EXAMPLES
    value: "false"
```

> **KubernetesExecutor explained:** Instead of Airflow running your task functions
> inside its own process (like PythonOperator does), it creates a fresh Kubernetes pod
> for every task. When the task finishes, the pod is deleted. This is exactly how
> cloud Airflow deployments (GKE, MWAA, Cloud Composer) work.

---

## Step 5 — Install Airflow via Helm

```bash
helm install airflow apache-airflow/airflow \
  --namespace airflow \
  --values airflow-values.yaml \
  --debug
```

This will take 2–3 minutes. Watch the pods come up:

```bash
kubectl get pods -n airflow --watch
```

You're waiting for all pods to show `Running`:
```
airflow-scheduler-xxx        Running
airflow-webserver-xxx        Running
airflow-postgresql-xxx       Running
airflow-statsd-xxx           Running
```

If a pod is stuck in `Pending` or `CrashLoopBackOff`, check why:
```bash
kubectl describe pod <pod-name> -n airflow
kubectl logs <pod-name> -n airflow
```

---

## Step 6 — Access the Airflow UI

Kubernetes doesn't expose services to your laptop by default. Use port-forwarding:

```bash
kubectl port-forward deploy/airflow-api-server 8080:8080 -n airflow
```

> Airflow 3.x uses `airflow-api-server` instead of the old `airflow-webserver`.

Now open: **http://localhost:8080**

Default credentials:
- Username: `admin`
- Password: `admin`

> **Why this matters on GKE:** On a real cluster you'd set up an Ingress with a
> public IP and a domain name instead of port-forwarding. The underlying service
> is identical — you're just changing how it's exposed.

---

## Step 7 — Write the `run_task.py` script

This is the entrypoint your pods will execute. Create `scripts/run_task.py`:

```python
import argparse

def generate_data(output_path: str):
    # your existing _generate_and_save_data logic here
    pass

def calculate_metrics(input_path: str, output_path: str):
    # your existing _calculate_salary_metrics_duckdb logic here
    pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    gen = subparsers.add_parser("generate-data")
    gen.add_argument("--output", required=True)

    calc = subparsers.add_parser("calculate-metrics")
    calc.add_argument("--input", required=True)
    calc.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command == "generate-data":
        generate_data(args.output)
    elif args.command == "calculate-metrics":
        calculate_metrics(args.input, args.output)
```

---

## Step 8 — Write the Dockerfile for task pods

Create `apps/airflow-pipelines/k8s/Dockerfile.task-runner`. It installs the
`airflow-pipelines` package (and its shared `airflow_pipelines` task logic) from
the workspace's root lockfile, the same way the main Airflow image does — instead
of a separate hand-picked `pip install`:

```dockerfile
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY apps/airflow-pipelines/pyproject.toml apps/airflow-pipelines/pyproject.toml
COPY apps/airflow-pipelines/src/ apps/airflow-pipelines/src/

RUN uv sync --frozen --no-dev --package airflow-pipelines

COPY apps/airflow-pipelines/k8s/scripts/run_task.py ./run_task.py

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "run_task.py"]
```

Because it needs the root `uv.lock`, the build context must be the **repository root**,
not the `pipelines/` directory.

---

## Step 9 — Build and load your task runner image

Your tasks run as pods, so they need a Docker image that Minikube can access.

Build the image **inside Minikube's Docker daemon** so it's immediately available
without needing a registry. Run this from the **repository root**:

```bash
# Point your shell's Docker CLI at Minikube's internal Docker daemon
eval $(minikube docker-env)

# Build the image (now it lives inside Minikube)
docker build -t data-pipeline-task-runner:latest -f apps/airflow-pipelines/k8s/Dockerfile.task-runner .
```

Verify the image is there:
```bash
docker images | grep data-pipeline-task-runner
```

> **Important:** Any terminal tab that hasn't run `eval $(minikube docker-env)` is
> still talking to your laptop's Docker. Run it in every new tab where you build images.

---

## Step 10 — Set up shared storage between task pods

Two tasks need to share a CSV file. Create `pipelines/k8s/task-pvc.yaml`:
```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: task-outputs-pv
spec:
  capacity:
    storage: 1Gi
  accessModes:
    - ReadWriteMany
  hostPath:
    path: /data/task-outputs   # path on the Minikube node

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: task-outputs-pvc
  namespace: airflow
spec:
  accessModes:
    - ReadWriteMany
  resources:
    requests:
      storage: 1Gi
```

Apply it:
```bash
kubectl apply -f k8s/task-pvc.yaml
```

> **Why this matters on GKE:** You'd replace `hostPath` with a `StorageClass`
> that provisions a GCP Persistent Disk automatically. Everything else
> (the PVC name, how pods reference it) stays identical.

---

## Step 11 — Rewrite the DAG

Replace `PythonOperator` with `KubernetesPodOperator`.

**`dags/data-processing-dag.py`**
```python
import datetime

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.sdk import DAG
from kubernetes.client import V1Volume, V1VolumeMount, V1PersistentVolumeClaimVolumeSource

SHARED_VOLUME = V1Volume(
    name="task-outputs",
    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(claim_name="task-outputs-pvc"),
)

SHARED_MOUNT = V1VolumeMount(
    name="task-outputs",
    mount_path="/data/task-outputs",
)

with DAG(
    dag_id="data_processing_pipeline",
    start_date=datetime.datetime(2024, 1, 1),
    schedule=None,
    catchup=False,
    tags=["data-processing", "fake-data", "metrics"],
) as dag:

    generate_data = KubernetesPodOperator(
        task_id="generate_fake_employee_data",
        namespace="airflow",
        image="data-pipeline-task-runner:latest",
        image_pull_policy="Never",
        arguments=["generate-data", "--output", "/data/task-outputs/employees.csv"],
        name="generate-data",
        volumes=[SHARED_VOLUME],
        volume_mounts=[SHARED_MOUNT],
        is_delete_operator_pod=False,
        get_logs=True,
    )

    calculate_metrics = KubernetesPodOperator(
        task_id="calculate_salary_metrics",
        namespace="airflow",
        image="data-pipeline-task-runner:latest",
        image_pull_policy="Never",
        arguments=[
            "calculate-metrics",
            "--input", "/data/task-outputs/employees.csv",
            "--output", "/data/task-outputs/metrics.csv",
        ],
        name="calculate-metrics",
        volumes=[SHARED_VOLUME],
        volume_mounts=[SHARED_MOUNT],
        is_delete_operator_pod=False,
        get_logs=True,
    )

    generate_data >> calculate_metrics
```

> **Airflow 3.x differences:** Import `DAG` from `airflow.sdk` (not `airflow`),
> task pods run in the `airflow` namespace (not `default`), and the `dag_id`
> in the DAG definition must match the filename's dag_id.

---

## Step 12 — Load your DAG into Airflow

The Helm chart already mounts an `airflow-dags` PVC into the **dag-processor** pod.
The scheduler pod does NOT mount this PVC — it gets DAG info from the database.

So you must copy the DAG file to both the scheduler AND the dag-processor (run these from the `pipelines/` directory):

```bash
# Copy to the scheduler (for manual `airflow dags reserialize`)
kubectl cp dags/data-processing-dag.py \
  airflow/<scheduler-pod>:/opt/airflow/dags/data-processing-dag.py \
  -c scheduler

# Copy to the dag-processor (for automated DAG parsing)
cat dags/data-processing-dag.py | kubectl exec -n airflow \
  deploy/airflow-dag-processor -c dag-processor -i -- \
  bash -c 'cat > /opt/airflow/dags/data-processing-dag.py'
```

After copying, force Airflow to re-serialize the DAG:

```bash
kubectl exec -n airflow deploy/airflow-scheduler -c scheduler \
  -- airflow dags reserialize
```

Then refresh the UI. The DAG should appear within a few seconds.

> **Better long-term approach:** Mount a PersistentVolume to `/opt/airflow/dags`
> and sync your DAG files there. On GKE you'd use Git-sync (a sidecar container
> that pulls from your repo automatically).

---

## Step 13 — Run it and watch what happens

Trigger the DAG from the UI, then watch the pods appear and disappear in real time:

```bash
kubectl get pods -n airflow --watch
```

You should see your task pods spin up, run, and terminate. That's the
KubernetesExecutor in action — ephemeral pods, one per task.

Check task logs directly:
```bash
kubectl logs -n airflow -l task_id=<task_id> --tail 50
```

---

## Teardown

When you're done for the day:
```bash
minikube stop
```

To wipe everything and start fresh:
```bash
minikube delete
```

---

## What transfers directly to GKE

| This setup | GKE equivalent |
|---|---|
| `minikube start` | Create a GKE cluster in Cloud Console |
| `eval $(minikube docker-env)` + local build | Push image to Artifact Registry |
| `hostPath` PersistentVolume | `StorageClass: standard` (GCP Persistent Disk) |
| `kubectl port-forward` | Ingress with a public IP + domain |
| `helm install` command | Identical — same command, different cluster |
| Namespaces, PVCs, pod specs | All identical — pure Kubernetes concepts |

The Helm install command and every Kubernetes manifest you write here will work
on GKE without modification, except swapping `hostPath` for a cloud storage class
and removing `image_pull_policy: Never`.
