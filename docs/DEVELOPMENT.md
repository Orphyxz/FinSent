# FinSent Development Guide

This guide describes the current local Windows PowerShell workflow.

## Create Environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

## Optional Dependencies

FinBERT / research:

```powershell
python -m pip install -r requirements-research.txt
```

Presentation tooling:

```powershell
python -m pip install -r requirements-presentation.txt
```

## Test

```powershell
python -m pytest finsent\tests -q
```

## Compile Check

```powershell
python -m compileall -q finsent scripts
```

## Dependency Check

```powershell
python -m pip check
```

## Import Smoke

```powershell
python -c "from finsent.app.dashboard.app import create_app; from finsent.app.services.pipeline import FinSentPipeline; print('ok')"
```

## Database Smoke

```powershell
python -c "from finsent.app.database.base import init_db; init_db(); print('db ok')"
```

## Dashboard Smoke

```powershell
python -c "from finsent.app.dashboard.app import create_app; app=create_app(); print(app.server.test_client().get('/').status_code)"
```

Expected output:

```text
200
```

## Start Dashboard

```powershell
python -m finsent.scripts.run_dashboard
```

Open `http://127.0.0.1:8050`.

## Pipeline Smoke

```powershell
python -m finsent.scripts.run_pipeline --ticker AAPL --limit 15
```

This may run in degraded mode when provider credentials are not configured.

## Logging

Default logging level is `INFO`.

Set locally in `.env`:

```text
FINSENT_LOG_LEVEL=WARNING
```

Use `DEBUG` only while diagnosing local provider behavior.
