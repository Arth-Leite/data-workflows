import os
from functools import cache

import pg8000.dbapi
from google.cloud.sql.connector import Connector, IPTypes


@cache
def get_connector() -> Connector:
    return Connector(ip_type=IPTypes.PRIVATE, refresh_strategy="lazy")


def get_conn():
    """One connection per request, authenticated with the pod's service account (IAM auth, no password).

    No pool: traffic is low and the connector caches the certificate, so opening a connection is cheap enough.
    """
    conn: pg8000.dbapi.Connection = get_connector().connect(
        os.environ["INSTANCE_CONNECTION_NAME"],
        "pg8000",
        user=os.environ["DB_IAM_USER"],
        db=os.environ["DB_NAME"],
        enable_iam_auth=True,
    )
    try:
        yield conn
    finally:
        conn.close()
