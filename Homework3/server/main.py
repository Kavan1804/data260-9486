import os, uuid
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .routers import chat, introspect
from .dbimpl import sql as db

load_dotenv(".env")

app = FastAPI(title="OpenAI Memory Demo")

# Init DB
db.init_db()

# Routers
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(introspect.router, prefix="/api", tags=["introspect"])

# Static UI
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse("static/index.html")
