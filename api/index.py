"""Vercel Serverless Function entry point for the FastAPI backend.

Routes incoming /api/* requests to the FastAPI application defined in backend/app/main.py.
"""
import sys
from pathlib import Path

# Add backend directory to sys.path so app modules can be resolved
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.main import app as main_app

# Wrapper application that mounts main_app at both "/" and "/api"
# to seamlessly handle both prefix-stripped and non-stripped request paths on Vercel.
app = FastAPI(title="Portfolio Story API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/api", main_app)

# The FastAPI deployment is the Vercel entry point. Serve the Vite bundle from
# the same function so the browser never receives FastAPI's default 404 at /.
FRONTEND_DIR = ROOT_DIR / "frontend" / "dist"
if FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    app.mount("/", main_app)
