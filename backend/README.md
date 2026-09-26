# Shellhacks backend

One FastAPI service for the frontend. Story Mode serves precomputed stories from
`data/cache/`, so it keeps working without Snowflake. The `/graph` routes read
Snowflake live. Credentials live only in `.env` on the machine running the API.

## First-time setup

macOS / Linux, from the project root:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r backend/requirements.txt
cp .env.example .env    # then fill in the values
```

Windows (PowerShell), from the project root:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r backend/requirements.txt
Copy-Item .env.example .env
```

Settings are read from `backend/.env` first, then the project-root `.env`.
Keeping everything in the root `.env` is simplest. `backend/.env.example`
lists every backend setting.

Snowflake needs either:
- `keypair`: the path to the private key belonging to `SHELLHACKS_APP`, or
- `pat`: a Snowflake programmatic access token.

The private key or token never belongs in GitHub. The required role and grants
are in `snowflake/service_access_setup.sql`. The account identifier for an AWS
US East account is `<locator>.us-east-1`, with no `.aws` suffix.

## Run the API

From the `backend` folder:
```bash
../.venv/bin/uvicorn app.main:app --reload
```
Then open `http://127.0.0.1:8000/docs` for the interactive API page.

## Endpoints

| Endpoint | Reads | Returns |
|---|---|---|
| `GET /health` | nothing | Liveness; never touches Snowflake |
| `GET /health/snowflake` | Snowflake | Confirms the Snowflake connection |
| `GET /universe` | graph export | The 5 companies with their graph connections |
| `GET /story/{symbol}` | story cache | Price series and cited explanations of big moves |
| `GET /story/{symbol}/citation/{id}` | story cache | One evidence row for the drill-down panel |
| `GET /graph/summary` | Snowflake | Row counts of the graph tables |
| `GET /graph/{ticker}/connections` | Snowflake | Companies linked to a ticker, with `role`: supplier, customer, or competitor |

The feed and research endpoints will be added once their Snowflake tables are
populated. See `data_sources.md` for Story Mode's sources and citation rules,
and `snowflake/schema_contract.sql` for the table definitions.

## Tests

From the `backend` folder:
```bash
../.venv/bin/python -m pytest tests
```
