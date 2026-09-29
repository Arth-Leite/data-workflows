"""Creates the schema and grants the app's IAM user only the rights it needs.

Runs as the db-migrator IAM user (cloudsqlsuperuser), separately from the API,
so the runtime identity never has DDL rights.
"""

import os

from google.cloud.sql.connector import Connector, IPTypes


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def main() -> None:
    app_user = quote_ident(os.environ["DB_IAM_USER"])

    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       TEXT NOT NULL,
            email      TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        f"GRANT SELECT, INSERT, DELETE ON users TO {app_user}",
    ]

    with Connector(ip_type=IPTypes.PRIVATE) as connector:
        conn = connector.connect(
            os.environ["INSTANCE_CONNECTION_NAME"],
            "pg8000",
            user=os.environ["DB_MIGRATOR_USER"],
            db=os.environ["DB_NAME"],
            enable_iam_auth=True,
        )
        try:
            cursor = conn.cursor()
            for statement in statements:
                cursor.execute(statement)
            conn.commit()
        finally:
            conn.close()

    print("Migration done")


if __name__ == "__main__":
    main()
