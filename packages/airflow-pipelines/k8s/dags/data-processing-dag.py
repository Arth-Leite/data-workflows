import datetime

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.sdk import DAG
from kubernetes.client import (
    V1PersistentVolumeClaimVolumeSource,
    V1Volume,
    V1VolumeMount,
)

SHARED_VOLUME = V1Volume(
    name="task-outputs",
    persistent_volume_claim=V1PersistentVolumeClaimVolumeSource(
        claim_name="task-outputs-pvc"
    ),
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
            "--input",
            "/data/task-outputs/employees.csv",
            "--output",
            "/data/task-outputs/metrics.csv",
        ],
        name="calculate-metrics",
        volumes=[SHARED_VOLUME],
        volume_mounts=[SHARED_MOUNT],
        is_delete_operator_pod=False,
        get_logs=True,
    )

    generate_data >> calculate_metrics
