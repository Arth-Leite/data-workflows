# data-workflows

A personal repo where I try out data engineering stuff outside of work. It's a uv workspace, so
everything under `apps/` is its own Python package sharing one lockfile (the Terraform-based
`apps/terraform-gke-project` is excluded from the workspace).

## What's in here

**`apps/web-crawler`** — An async crawler (only Wikipedia for now). Postgres is the whole backend: a `PostgresCrawlStore` keeps the durable queue and the visited titles (using indexes and row locks), and the scraped pages are stored there too. It replaced the earlier RabbitMQ+Redis frontier.

**`apps/airflow-pipelines`** — Airflow on Minikube with the KubernetesExecutor, tasks running as pods against a shared PVC. Mostly me trying out Airflow 3 on Kubernetes and Helm.

**`apps/dagster-pipelines`** — Same idea as the airflow one, but to try out Dagster.

**`apps/terraform-gke-project`** — A FastAPI service on GKE, provisioned end to end with Terraform. Users live in Cloud SQL and every request is logged to BigQuery so usage can be billed by time of day. An AWS billing service reads the billing views through Workload Identity Federation, without any keys. See its [README](apps/terraform-gke-project/README.md) for the deployment and the feature checks.

**`apps/ml`** — Vehicle reservation forecasting with data contracts, training, model evaluation, promotion, and an HTTP prediction service. Its DAG runs from `apps/airflow-pipelines`.

**`experimenting/`** — Throwaway scraping experiments (asyncio, notebooks, Playwright persistent sessions) kept outside the workspace.

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
