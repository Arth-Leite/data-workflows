from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG, get_current_context


def process_random():
    context = get_current_context()
    task_instance = context["task_instance"]
    randint = task_instance.xcom_pull(task_ids="generate_randint")
    return f"The randint is {randint}"


with DAG(
    dag_id="test-dag",
    description="This DAG is for test only",
    default_args={"retries": 0},
) as dag:
    generate_randint = BashOperator(
        task_id="generate_randint", bash_command="shuf -i 1-100 -n 1", do_xcom_push=True
    )

    retrieve_randint = PythonOperator(
        task_id="retrieve_randint", python_callable=process_random
    )

    generate_randint >> retrieve_randint
