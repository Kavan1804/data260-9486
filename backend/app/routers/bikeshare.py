"""HW7 Part 4: HTTP entry point for the bike-share ReAct agent (used by the React page /bikeshare).

POST /api/bikeshare/run   multipart form: file (trip CSV), url (pricing page), page_mode (snapshot|live)
GET  /api/bikeshare/fixtures/{name}   serves the local Part 5 hostile fixture so it can be fetched by URL

These routes are not domain CRUD, so they do not use the HW7 role checks.
"""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

import config

router = APIRouter(prefix="/api/bikeshare", tags=["HW7 bike-share agent"])
FIXTURES = Path(config.ROOT) / "Homework7" / "fixtures"
MAX_CSV_BYTES = 20 * 1024 * 1024


@router.post("/run")
def run(file: UploadFile = File(...), url: str = Form(...), page_mode: str = Form("snapshot")):
    from bikeshare.agent import run_bikeshare

    if page_mode not in ("snapshot", "live"):
        raise HTTPException(status_code=422, detail="page_mode must be 'snapshot' or 'live'")
    raw = file.file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV is larger than 20 MB")
    try:
        text = raw.decode("utf-8-sig")
        return run_bikeshare(text, url.strip(), csv_name=file.filename or "uploaded.csv", page_mode=page_mode)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Could not read the CSV: {exc}")


@router.get("/fixtures/{name}", response_class=HTMLResponse)
def fixture(name: str):
    path = (FIXTURES / name).resolve()
    if path.parent != FIXTURES.resolve() or path.suffix != ".html" or not path.exists():
        raise HTTPException(status_code=404, detail="fixture not found")
    return path.read_text(encoding="utf-8")
