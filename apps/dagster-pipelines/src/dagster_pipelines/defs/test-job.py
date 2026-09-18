import random

from dagster import job, op


@op
def generate_randint() -> int:
    return random.randint(1, 100)


@op
def read_randint(i: int):
    return i


@job()
def test_job():
    read_randint(generate_randint())
