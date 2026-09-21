import os

import uvicorn
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from config import DOMAIN_NAME, PORT_BASE
from routers.auth import router as auth_router

app = FastAPI(title=f"DATA 260 HW3 - {DOMAIN_NAME}")

# Secret key for session signing. Set SECRET_KEY in the environment for
# anything beyond local manual verification.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret-key-change-me")

# https_only=True is what makes Starlette add the Secure attribute to the
# Set-Cookie header (HttpOnly is always added by SessionMiddleware, and
# SameSite comes from same_site below). Chrome and Edge treat http://localhost
# as a secure context, so the cookie still round-trips there during manual
# testing; Safari and Firefox do not grant that exception, so verify on those
# browsers with real HTTPS (e.g. `uvicorn main:app --ssl-keyfile ... --ssl-certfile ...`
# with a self-signed certificate) rather than plain http://localhost.
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=True,
    same_site="lax",
    max_age=3600,
)

# Register routes
app.include_router(auth_router)


# This block runs only when executing: python3 main.py
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=int(os.getenv("PORT_BASE", PORT_BASE)),
        reload=True,
    )
