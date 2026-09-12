from __future__ import annotations

import os
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
PORT_BASE = int(os.getenv("PORT_BASE", "8986"))

app = FastAPI(title="User Management App", version="2.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class User(BaseModel):
    id: int
    name: str
    email: str


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=200)


class UserUpdate(UserCreate):
    pass


users: List[User] = [
    User(id=1, name="Alice", email="alice@example.com"),
    User(id=2, name="Bob", email="bob@example.com"),
]


def clean(value: str, label: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{label} is required")
    return value


@app.get("/")
async def read_root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/users", response_model=List[User])
async def get_users(response: Response, search: str = Query(default="")):
    response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
    term = search.strip().casefold()
    if not term:
        return users
    return [u for u in users if term in u.name.casefold() or term in u.email.casefold()]


@app.get("/api/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    user = next((u for u in users if u.id == user_id), None)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/api/users", response_model=User, status_code=201)
async def create_user(data: UserCreate):
    name, email = clean(data.name, "Name"), clean(data.email, "Email")
    new_user = User(id=max((u.id for u in users), default=0) + 1, name=name, email=email)
    users.append(new_user)
    return new_user


@app.put("/api/users/{user_id}", response_model=User)
async def update_user(user_id: int, data: UserUpdate):
    user = next((u for u in users if u.id == user_id), None)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.name, user.email = clean(data.name, "Name"), clean(data.email, "Email")
    return user


@app.delete("/api/users/highest", response_model=User)
async def delete_highest_id():
    if not users:
        raise HTTPException(status_code=404, detail="No users to delete")
    highest = max(users, key=lambda u: u.id)
    users.remove(highest)
    return highest


@app.delete("/api/users/{user_id}", status_code=204)
async def delete_user(user_id: int):
    user = next((u for u in users if u.id == user_id), None)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    users.remove(user)
    return Response(status_code=204)


if __name__ == "__main__":
    uvicorn.run("user_management_app.main:app", host="0.0.0.0", port=PORT_BASE, reload=False)
