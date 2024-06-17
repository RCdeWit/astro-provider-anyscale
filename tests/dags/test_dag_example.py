import os
from pathlib import Path

import pytest
from airflow.models import Connection, DagBag
from airflow.utils.db import create_default_connections
from airflow.utils.session import create_session

# Correctly construct the example DAGs directory path
EXAMPLE_DAGS_DIR = Path(__file__).parent / "example_dags"
print(f"EXAMPLE_DAGS_DIR: {EXAMPLE_DAGS_DIR}")


def get_dags(dag_folder=None):
    dag_bag = (
        DagBag(dag_folder=str(dag_folder), include_examples=False) if dag_folder else DagBag(include_examples=False)
    )

    def strip_path_prefix(path):
        return os.path.relpath(path, os.environ.get("AIRFLOW_HOME", ""))

    dags_info = [(k, v, strip_path_prefix(v.fileloc)) for k, v in dag_bag.dags.items()]

    for dag_id, dag, fileloc in dags_info:
        print(f"DAG ID: {dag_id}, File Location: {fileloc}")

    return dags_info


@pytest.fixture(scope="module")
def setup_airflow_db():
    os.system("airflow db init")
    # Explicitly create the tables if necessary
    create_default_connections()
    with create_session() as session:
        conn = Connection(
            conn_id="anyscale_conn",
            conn_type="anyscale",
            extra=f'{{"ANYSCALE_CLI_TOKEN": "{os.environ.get("ANYSCALE_CLI_TOKEN", "")}"}}',
        )
        session.add(conn)
        session.commit()


dags = get_dags(EXAMPLE_DAGS_DIR)
print(f"Discovered DAGs: {dags}")


@pytest.mark.integration
@pytest.mark.parametrize("dag_id,dag,fileloc", dags, ids=[x[2] for x in dags])
def test_dag_runs(setup_airflow_db, dag_id, dag, fileloc):
    print(f"Testing DAG: {dag_id}, located at: {fileloc}")
    assert dag is not None, f"DAG {dag_id} not found!"
    try:
        dag.test()
    except Exception as e:
        print(f"Error running DAG {dag_id}: {e}")
        raise e
