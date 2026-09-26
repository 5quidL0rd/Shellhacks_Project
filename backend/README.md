# Shellhacks backend

The frontend calls this FastAPI service. The service reads Snowflake, while
credentials remain only in `backend/.env` on the machine running the API.

## First-time setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item backend/.env.example backend/.env
```

Edit `backend/.env` with the Snowflake account identifier and either:

- `keypair`: the path to the private key belonging to `SHELLHACKS_APP`; or
- `pat`: a Snowflake programmatic-access token.

The private key or token never belongs in GitHub. The required role and grants
are documented in `snowflake/service_access_setup.sql`.

Run the API from the repository root:

```powershell
python -m uvicorn backend.main:app --reload
```

## Available endpoints

- `GET /health` verifies the Snowflake connection.
- `GET /graph/summary` returns the graph-table row counts.
- `GET /graph/NVDA/connections` returns companies connected to NVDA from the
  Snowflake graph mirror.

When running locally, try `http://127.0.0.1:8000/docs` for the interactive API
page. The Story Mode, news feed, and research endpoints will be added after
their Snowflake tables are populated.
