import pandera.engines.pandas_engine as pe
import pandera.pandas as pa

CREATED_AT_FORMAT = "%Y-%m-%d %H:%M:%S"

POSITIVE = pa.Check.gt(0)
NOT_NEGATIVE = pa.Check.ge(0)
AT_LEAST_ONE_IMAGE = pa.Check.ge(1)
BINARY = pa.Check.isin([0, 1])


vehicles_schema = pa.DataFrameSchema(
    {
        "vehicle_id": pa.Column(int, unique=True, nullable=False),
        "technology": pa.Column("Int64", BINARY, nullable=True, coerce=True),
        "actual_price": pa.Column(float, POSITIVE, nullable=False, coerce=True),
        "recommended_price": pa.Column(float, POSITIVE, nullable=False, coerce=True),
        "num_images": pa.Column(
            "Int64",
            AT_LEAST_ONE_IMAGE,
            nullable=True,
            coerce=True,
        ),
        "street_parked": pa.Column("Int64", BINARY, nullable=True, coerce=True),
        "description": pa.Column("Int64", NOT_NEGATIVE, nullable=True, coerce=True),
    },
    strict=False,  # extra columns allowed
)

reservations_schema = pa.DataFrameSchema(
    {
        "vehicle_id": pa.Column(int, nullable=False),
        "created_at": pa.Column(
            pe.DateTime(to_datetime_kwargs={"format": CREATED_AT_FORMAT}),
            nullable=False,
            coerce=True,
        ),
    },
    strict=False,
)


# Serving receives the same listings without the key.
request_schema = vehicles_schema.remove_columns(["vehicle_id"])
