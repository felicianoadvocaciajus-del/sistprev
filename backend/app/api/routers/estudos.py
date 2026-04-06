"""
Router para gerenciamento de estudos previdenciários.

Armazena os estudos como arquivos JSON locais na pasta `estudos/`.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ─────────────────────────────────────────────────────────────────────────────
# Configuração
# ─────────────────────────────────────────────────────────────────────────────

ESTUDOS_DIR = Path(r"C:\Users\Administrador\Documents\Documents\previdenciario\estudos")

router = APIRouter(prefix="/estudos", tags=["Estudos"])


# ─────────────────────────────────────────────────────────────────────────────
# Modelos
# ─────────────────────────────────────────────────────────────────────────────

class EstudoInput(BaseModel):
    segurado: Dict[str, Any]
    planejamento: Dict[str, Any]
    nome_advogado: str = ""
    observacoes: str = ""


class EstudoResumo(BaseModel):
    id: str
    nome_cliente: str
    data_elaboracao: str
    regra_melhor: Optional[str] = None
    rmi_melhor: Optional[str] = None
    arquivo: str


class EstudoSalvoResponse(BaseModel):
    id: str
    nome_cliente: str
    data_elaboracao: str
    arquivo: str


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sanitize_filename(name: str) -> str:
    """Remove caracteres problemáticos para nomes de arquivo."""
    keep = (" ", "-", "_")
    return "".join(c if c.isalnum() or c in keep else "_" for c in name).strip().replace(" ", "_")


def _decimal_serializer(obj: Any) -> Any:
    """Converte Decimal para str durante serialização JSON."""
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _extrair_nome_cliente(segurado: Dict[str, Any]) -> str:
    """Extrai o nome do cliente do dicionário do segurado."""
    dp = segurado.get("dados_pessoais", {})
    nome = dp.get("nome", "")
    if nome:
        return str(nome)
    for chave in ("nome", "nome_completo", "nome_cliente"):
        if chave in segurado and segurado[chave]:
            return str(segurado[chave])
    return "cliente_sem_nome"


def _extrair_melhor_regra(planejamento: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Extrai regra e RMI da melhor opção de aposentadoria do planejamento."""
    regra_melhor = planejamento.get("melhor_regra")
    rmi_melhor = planejamento.get("melhor_rmi")
    if rmi_melhor is not None:
        rmi_melhor = str(rmi_melhor)

    if not regra_melhor:
        projecoes = planejamento.get("projecoes", [])
        alcancaveis = [p for p in projecoes if p.get("data_elegibilidade")]
        if alcancaveis:
            alcancaveis.sort(key=lambda p: p.get("meses_faltantes", 9999))
            regra_melhor = alcancaveis[0].get("regra")
            rmi_melhor = alcancaveis[0].get("rmi_formatada", str(alcancaveis[0].get("rmi_projetada", "")))

    return regra_melhor, rmi_melhor


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/salvar", response_model=EstudoSalvoResponse)
def salvar_estudo(dados: EstudoInput):
    """Salva um novo estudo ou atualiza um existente."""
    ESTUDOS_DIR.mkdir(parents=True, exist_ok=True)

    estudo_id = uuid.uuid4().hex[:12]
    data_elaboracao = datetime.now().strftime("%Y-%m-%d")
    nome_cliente = _extrair_nome_cliente(dados.segurado)
    nome_sanitizado = _sanitize_filename(nome_cliente)

    nome_arquivo = f"{nome_sanitizado}_{data_elaboracao}_{estudo_id}.json"
    caminho = ESTUDOS_DIR / nome_arquivo

    documento = {
        "id": estudo_id,
        "nome_cliente": nome_cliente,
        "data_elaboracao": data_elaboracao,
        "nome_advogado": dados.nome_advogado,
        "observacoes": dados.observacoes,
        "segurado": dados.segurado,
        "planejamento": dados.planejamento,
        "arquivo": nome_arquivo,
    }

    try:
        caminho.write_text(
            json.dumps(documento, ensure_ascii=False, indent=2, default=_decimal_serializer),
            encoding="utf-8",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar estudo: {e}")

    return EstudoSalvoResponse(
        id=estudo_id,
        nome_cliente=nome_cliente,
        data_elaboracao=data_elaboracao,
        arquivo=nome_arquivo,
    )


@router.get("/listar", response_model=List[EstudoResumo])
def listar_estudos():
    """Lista todos os estudos salvos, do mais recente para o mais antigo."""
    ESTUDOS_DIR.mkdir(parents=True, exist_ok=True)

    estudos: List[EstudoResumo] = []
    for arq in ESTUDOS_DIR.glob("*.json"):
        try:
            conteudo = json.loads(arq.read_text(encoding="utf-8"))
            regra_melhor, rmi_melhor = _extrair_melhor_regra(conteudo.get("planejamento", {}))
            estudos.append(
                EstudoResumo(
                    id=conteudo.get("id", arq.stem),
                    nome_cliente=conteudo.get("nome_cliente", "—"),
                    data_elaboracao=conteudo.get("data_elaboracao", ""),
                    regra_melhor=regra_melhor,
                    rmi_melhor=rmi_melhor,
                    arquivo=arq.name,
                )
            )
        except Exception:
            continue  # ignora arquivos corrompidos

    estudos.sort(key=lambda e: e.data_elaboracao, reverse=True)
    return estudos


@router.get("/{estudo_id}")
def carregar_estudo(estudo_id: str):
    """Carrega um estudo completo pelo ID."""
    ESTUDOS_DIR.mkdir(parents=True, exist_ok=True)

    for arq in ESTUDOS_DIR.glob("*.json"):
        try:
            conteudo = json.loads(arq.read_text(encoding="utf-8"))
            if conteudo.get("id") == estudo_id:
                return conteudo
        except Exception:
            continue

    raise HTTPException(status_code=404, detail=f"Estudo '{estudo_id}' não encontrado.")


@router.delete("/{estudo_id}")
def deletar_estudo(estudo_id: str):
    """Remove um estudo pelo ID."""
    ESTUDOS_DIR.mkdir(parents=True, exist_ok=True)

    for arq in ESTUDOS_DIR.glob("*.json"):
        try:
            conteudo = json.loads(arq.read_text(encoding="utf-8"))
            if conteudo.get("id") == estudo_id:
                arq.unlink()
                return {"detail": f"Estudo '{estudo_id}' removido com sucesso."}
        except Exception:
            continue

    raise HTTPException(status_code=404, detail=f"Estudo '{estudo_id}' não encontrado.")
