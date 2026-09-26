"""One safe, reusable connection factory for Snowflake."""

import os
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))

REQUIRED_SETTINGS = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_PASSWORD",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
)


def get_connection():
    """Open a connection configured by backend/.env.

    Keeping connection values in environment variables means credentials never
    enter source control or get sent to the browser.
    """
    missing = [name for name in REQUIRED_SETTINGS if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Snowflake is not configured. Copy backend/.env.example to "
            "backend/.env and set: " + ", ".join(missing)
        )

    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )
