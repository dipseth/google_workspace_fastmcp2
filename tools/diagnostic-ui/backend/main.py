"""Card DSL Diagnostic UI — FastAPI Backend

Standalone diagnostic server that imports the codebase's DSL parsing,
symbol resolution, and wrapper APIs directly.

Run: PYTHONPATH=/path/to/repo uvicorn main:app --port 3001 --reload
"""
import sys
from pathlib import Path

# Add project root and backend dir to path
_project_root = Path(__file__).resolve().parent.parent.parent.parent
_backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_backend_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.symbols import router as symbols_router
from routes.dsl import router as dsl_router
from routes.ml_eval import router as ml_eval_router

app = FastAPI(title="Card DSL Diagnostic UI", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(symbols_router, prefix="/api")
app.include_router(dsl_router, prefix="/api")
app.include_router(ml_eval_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "diagnostic-ui"}
