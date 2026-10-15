# data-workflows

A personal repo where I try out data engineering stuff outside of work. It's a uv workspace, so
everything under `apps/` is its own Python package sharing one lockfile (the Terraform-based
`apps/terraform-gke-project` is excluded from the workspace).

## What's in here

**`apps/web-crawler`** — For the moment the most interesting part. An async crawler (only Wikipedia for now): It supports two frontiers options to handle durable queues and visited urls: **RabbitMQ+Redis** and **Postgres** alternative with indexes and locks to replace both tools.
All the scraped pages are stored in **Postgres**.

Workers pull from the queue, fetch the extract and the outgoing links, push the new titles back.

**`apps/airflow-pipelines`** — Airflow on Minikube with the KubernetesExecutor, tasks running as pods against a shared PVC. Mostly me trying out Airflow 3 on Kubernetes and Helm.

**`apps/dagster-pipelines`** — Same idea as the airflow one, but to try out Dagster.

**`apps/terraform-gke-project`** — A FastAPI service on GKE, provisioned end to end with Terraform. Users live in Cloud SQL and every request is logged to BigQuery so usage can be billed by time of day. An AWS billing service reads the billing views through Workload Identity Federation, without any keys. See its [README](apps/terraform-gke-project/README.md) for the deployment and the feature checks.

## Running the crawler

```bash
cd apps/web-crawler/wikipedia
docker compose up --build
```

That brings up four containers: the crawler, Postgres, Redis and RabbitMQ. It seeds from a single
article and stops after 20 pages — both are set in `crawler.py`.

The RabbitMQ image includes the management UI but the port isn't published. Add `15672:15672` to
the compose file if you want to watch the queue while it runs.

## Running Airflow on Minikube

Start the cluster and install the chart, from `apps/airflow-pipelines`:

```bash
minikube start --cpus=4 --memory=4096 --disk-size=20g
kubectl create namespace airflow

helm repo add apache-airflow https://airflow.apache.org
helm repo update
helm install airflow apache-airflow/airflow -n airflow --values k8s/airflow-values.yaml
```

Once this is done you can simply create the image with `docker build` and `kubectl apply` the `task-pvc.yaml`.

You will need to copy the DAGs to the airflow pod as well, and then you can run it with the airflow cli inside the pod with `kubectl exec`.
