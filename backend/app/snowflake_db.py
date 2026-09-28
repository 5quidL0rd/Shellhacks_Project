"""One safe, reusable connection factory for Snowflake."""

import os
import base64
from pathlib import Path

try:
    import snowflake.connector
except ImportError:
    snowflake = None

from .config import BACKEND_DIR  # loads backend/.env, then the project-root .env

REQUIRED_SETTINGS = (
    "SNOWFLAKE_ACCOUNT",
    "SNOWFLAKE_USER",
    "SNOWFLAKE_ROLE",
    "SNOWFLAKE_WAREHOUSE",
    "SNOWFLAKE_DATABASE",
    "SNOWFLAKE_SCHEMA",
)


def get_connection():
    """Open a connection configured by backend/.env or the project-root .env.

    Keeping connection values in environment variables means credentials never
    enter source control or get sent to the browser.
    """
    if snowflake is None:
        raise RuntimeError("snowflake-connector-python is not installed.")

    missing = [name for name in REQUIRED_SETTINGS if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Snowflake is not configured. Set these in the project-root .env "
            "(see backend/.env.example): " + ", ".join(missing)
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
        encoded_key = os.getenv("SNOWFLAKE_PRIVATE_KEY_B64")
        if encoded_key:
            from cryptography.hazmat.primitives import serialization
            pem = base64.b64decode(encoded_key)
            passphrase = os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE")
            key = serialization.load_pem_private_key(
                pem, password=passphrase.encode() if passphrase else None)
            params["private_key"] = key.private_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            return snowflake.connector.connect(**params)
        key_path = os.getenv("SNOWFLAKE_PRIVATE_KEY_FILE")
        if not key_path:
            raise RuntimeError("Set SNOWFLAKE_PRIVATE_KEY_FILE for key-pair authentication.")
        # A relative path means relative to the project root, wherever the
        # API was started from.
        path = Path(key_path)
        if not path.is_absolute():
            path = BACKEND_DIR.parent / path
        params.update(authenticator="SNOWFLAKE_JWT", private_key_file=str(path))
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
