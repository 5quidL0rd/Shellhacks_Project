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
app.mount("/", main_app)
