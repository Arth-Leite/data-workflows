import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import pg8000.dbapi
from db import get_conn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

app = FastAPI()

Conn = Annotated[pg8000.dbapi.Connection, Depends(get_conn)]


@app.middleware("http")
async def log_request(request: Request, call_next):
    # Kubelet probes: not API calls, keep them out of the billing logs
    if request.url.path == "/healthz":
        return await call_next(request)
    start = datetime.now(timezone.utc).isoformat()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        print(
            json.dumps(
                {
                    # "time" (RFC 3339) is the key the GKE logging agent reads as the entry timestamp
                    "time": start,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                }
            )
        )


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr = Field(max_length=320)


class UserOut(BaseModel):
    id: UUID
    name: str
    email: EmailStr
    created_at: datetime


def run_query(conn: pg8000.dbapi.Connection, query: str, params: tuple = ()) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute(query, params)
    columns = [col[0] for col in cursor.description or ()]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


@app.get("/")
def read_root():
    return "Hello world"


@app.get("/healthz", include_in_schema=False)
def healthz():
    return "ok"


@app.post("/users", status_code=status.HTTP_201_CREATED, response_model=UserOut)
def create_user(user: UserIn, conn: Conn):
    rows = run_query(
        conn,
        "INSERT INTO users (name, email) VALUES (%s, %s) "
        "ON CONFLICT (email) DO NOTHING "
        "RETURNING id, name, email, created_at",
        (user.name, user.email.lower()),
    )
    conn.commit()
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    return rows[0]


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: UUID, conn: Conn):
    rows = run_query(conn, "SELECT id, name, email, created_at FROM users WHERE id = %s", (user_id,))
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return rows[0]


@app.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, conn: Conn):
    rows = run_query(conn, "DELETE FROM users WHERE id = %s RETURNING id", (user_id,))
    conn.commit()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
