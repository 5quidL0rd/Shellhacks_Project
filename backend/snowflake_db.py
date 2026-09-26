"""One safe, reusable connection factory for Snowflake."""

import os
from pathlib import Path

import snowflake.connector
from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"))

REQUIRED_SETTINGS = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
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

    params = dict(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )

    auth_mode = os.getenv("SNOWFLAKE_AUTH_MODE", "").lower()
    if auth_mode == "keypair":
        key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
        if not key_path:
            raise RuntimeError("Set SNOWFLAKE_PRIVATE_KEY_FILE for key-pair authentication.")
        params.update(authenticator="SNOWFLAKE_JWT", private_key_file=key_path)
        if passphrase := os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"):
            params["private_key_file_pwd"] = passphrase
    elif auth_mode == "pat":
        token = os.getenv("SNOWFLAKE_PROGRAMMATIC_ACCESS_TOKEN")
        if not token:
            raise RuntimeError("Set SNOWFLAKE_PROGRAMMATIC_ACCESS_TOKEN for PAT authentication.")
        # The Python connector accepts a Snowflake PAT as its password value.
        params["password"] = token
    else:
        raise RuntimeError("Set SNOWFLAKE_AUTH_MODE to either 'keypair' or 'pat'.")

    return snowflake.connector.connect(**params)
