"""
Rotas de consulta a índices previdenciários.
"""
from __future__ import annotations
from fastapi import APIRouter, Query, HTTPException
from datetime import date

router = APIRouter(prefix="/indices", tags=["Índices e Tabelas"])


@router.get("/teto")
def teto_vigente(ano: int = Query(...), mes: int = Query(...)):
    """Retorna o teto previdenciário (RGPS) para o mês/ano informado."""
    try:
        from ...domain.indices.teto_previdenciario import teto_em
        valor = teto_em(ano, mes)
        return {"ano": ano, "mes": mes, "teto": str(valor)}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/salario-minimo")
def salario_minimo(ano: int = Query(...), mes: int = Query(...)):
    """Retorna o salário mínimo vigente no mês/ano informado."""
    try:
        from ...domain.indices.salario_minimo import salario_minimo_em
        d = date(ano, mes, 1)
        from ...domain.indices.salario_minimo import salario_minimo_na_data
        valor = salario_minimo_na_data(d)
        return {"ano": ano, "mes": mes, "salario_minimo": str(valor)}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/correcao-monetaria")
def fator_correcao(
    ano_inicio: int = Query(...),
    mes_inicio: int = Query(...),
    ano_fim: int = Query(...),
    mes_fim: int = Query(...),
):
    """Retorna o fator de correção monetária (INPC) entre duas competências."""
    try:
        from ...domain.indices.correcao_monetaria import fator_acumulado
        fator = fator_acumulado((ano_inicio, mes_inicio), (ano_fim, mes_fim))
        return {
            "de": f"{mes_inicio:02d}/{ano_inicio}",
            "ate": f"{mes_fim:02d}/{ano_fim}",
            "fator": str(fator),
        }
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/expectativa-sobrevida")
def expectativa_sobrevida(
    idade: int = Query(..., ge=0, le=120),
    ano: int = Query(...),
):
    """Retorna a expectativa de sobrevida do IBGE para a idade e ano informados."""
    try:
        from ...domain.indices.expectativa_sobrevida import expectativa_sobrevida as es
        valor = es(idade, ano)
        return {"idade": idade, "ano": ano, "expectativa_anos": str(valor)}
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/pontos-ec103")
def pontos_ec103(ano: int = Query(...)):
    """Retorna os pontos exigidos pelas regras de transição EC 103/2019 para o ano."""
    try:
        from ...domain.constantes import PONTOS_EC103
        pontos = PONTOS_EC103.get(ano)
        if pontos is None:
            raise HTTPException(status_code=404, detail=f"Pontos não definidos para {ano}")
        return {"ano": ano, "homem": pontos[0], "mulher": pontos[1]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
