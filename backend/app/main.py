"""
Aplicação FastAPI — Sistema Previdenciário.

Iniciar:
  uvicorn app.main:app --reload --port 8000

Documentação interativa: http://localhost:8000/docs
"""
from __future__ import annotations
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from .api.routers import calculo_router, upload_router, indices_router, relatorio_router, planejamento_router, estudos_router

# ─────────────────────────────────────────────────────────────────────────────
# Aplicação
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Sistema Previdenciário",
    description=(
        "Cálculos previdenciários conforme Lei 8.213/91, EC 103/2019 "
        "e Manual de Cálculos da Justiça Federal (CJF Resolução 963/2025)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — permite acesso do frontend local durante desenvolvimento
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Rotas da API
# ─────────────────────────────────────────────────────────────────────────────

app.include_router(calculo_router, prefix="/api/v1")
app.include_router(upload_router, prefix="/api/v1")
app.include_router(indices_router, prefix="/api/v1")
app.include_router(relatorio_router, prefix="/api/v1")
app.include_router(planejamento_router, prefix="/api/v1")
app.include_router(estudos_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "sistema": "Previdenciário v1.0"}


# ─────────────────────────────────────────────────────────────────────────────
# Frontend estático
# ─────────────────────────────────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        """Retorna index.html para todas as rotas do SPA (exceto /api)."""
        if full_path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)
        index_file = FRONTEND_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
