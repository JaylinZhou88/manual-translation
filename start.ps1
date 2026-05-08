$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    python -m venv .venv
}

.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

