"""
Rota de geração de relatório pericial PDF.
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional
import io

router = APIRouter(prefix="/relatorio", tags=["Relatório Pericial"])


class RelatorioRequest(BaseModel):
    segurado: Dict[str, Any]
    calculo: Dict[str, Any]
    titulo: str = "Relatório Pericial Previdenciário"


class RelatorioPlanejamentoRequest(BaseModel):
    segurado: Dict[str, Any]
    planejamento: Dict[str, Any]
    nome_advogado: Optional[str] = None


@router.post("/pdf")
def gerar_relatorio_pdf(req: RelatorioRequest):
    """
    Gera o relatório pericial em PDF com memória de cálculo completa.
    Requer WeasyPrint instalado.
    """
    try:
        from ...relatorio.gerador import gerar_pdf
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Módulo de relatório não disponível: {e}. Instale: pip install weasyprint"
        )

    try:
        pdf_bytes = gerar_pdf(req.segurado, req.calculo, req.titulo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar relatório: {e}")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="relatorio_previdenciario.pdf"'
        },
    )


@router.post("/html")
def gerar_relatorio_html(req: RelatorioRequest):
    """Retorna o relatório em HTML (para preview ou impressão pelo navegador)."""
    try:
        from ...relatorio.gerador import gerar_html
    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        html = gerar_html(req.segurado, req.calculo, req.titulo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.post("/planejamento/html")
def gerar_relatorio_planejamento_html(req: RelatorioPlanejamentoRequest):
    """Retorna relatório de planejamento previdenciário em HTML profissional."""
    try:
        from ...relatorio.gerador import gerar_html_planejamento
    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        html = gerar_html_planejamento(req.segurado, req.planejamento, req.nome_advogado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.post("/planejamento/docx")
def gerar_relatorio_planejamento_docx(req: RelatorioPlanejamentoRequest):
    """Gera relatório de planejamento previdenciário em DOCX profissional (Visual Law)."""
    try:
        from ...relatorio.gerador_docx import gerar_docx_planejamento
    except ImportError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        docx_bytes = gerar_docx_planejamento(req.segurado, req.planejamento, req.nome_advogado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar DOCX: {e}")

    nome_seg = req.segurado.get("dados_pessoais", {}).get("nome", "Cliente").replace(" ", "_")
    filename = f"Planejamento_{nome_seg}.docx"

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
