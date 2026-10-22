# airflow-pipelines

Airflow 3 pipelines for this workspace.

The `vehicle_reservations_training` DAG trains a model from `apps/ml`, compares
it with the active champion, and promotes it through the model registry.

## Docker Compose

```bash
docker compose up --build
```

Airflow is available at http://localhost:8080 and the model API at
http://localhost:8000/docs. Run the DAG once before calling the prediction API.

## Kubernetes

The existing `k8s/` files deploy Airflow with `KubernetesExecutor`. The ML DAG
uses the Airflow image, so build and push that image before scheduling it.
