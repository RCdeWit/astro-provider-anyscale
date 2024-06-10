from datetime import datetime, timedelta
from airflow import DAG
from pathlib import Path
from anyscale_provider.operators.anyscale import SubmitAnyscaleJob

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 4, 2),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Define the Anyscale connection
ANYSCALE_CONN_ID = "anyscale_conn"

# Constants
FOLDER_PATH = Path(__file__).parent /"ray_scripts"

dag = DAG(
    'sample_anyscale_workflow',
    default_args=default_args,
    description='A DAG to interact with Anyscale triggered manually',
    schedule_interval=None,  # This DAG is not scheduled, only triggered manually
    catchup=False,
)

submit_anyscale_job = SubmitAnyscaleJob(
    task_id='submit_anyscale_job',
    conn_id = ANYSCALE_CONN_ID,
    name = 'AstroJob',
    image_uri = 'anyscale/ray:2.23.0-py311', 
    compute_config = 'my-compute-config:1',
    working_dir = FOLDER_PATH,
    entrypoint= 'python script.py',
    requirements = ["requests","pandas","numpy","torch"],
    max_retries = 1,
    dag=dag,
)


# Defining the task sequence
submit_anyscale_job
