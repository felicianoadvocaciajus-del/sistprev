"""
Rotas de cálculo previdenciário.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import List

from fastapi import APIRouter, HTTPException

from ..schemas import (
    CalculoAposentadoriaRequest, CalculoAuxilioDoencaRequest,
    CalculoInvalidezRequest, CalculoPensaoRequest,
    RevisaoVidaTodaRequest, RevisaoTetoRequest, AtrasadosRequest,
    CalculoResponse, ResumoSeguradoResponse, RevisaoVidaTodaResponse,
    RevisaoTetoResponse, ParcelasAtrasadasResponse,
)
from ..converters import (
    segurado_from_schema, cenario_to_response, parse_date, fmt_decimal, fmt_brl
)
from ...services.calculo_service import CalculoService

router = APIRouter(prefix="/calculo", tags=["Cálculos"])


@router.post("/aposentadoria", response_model=CalculoResponse)
def calcular_aposentadoria(req: CalculoAposentadoriaRequest):
    try:
        segurado = segurado_from_schema(req.segurado)
        der = parse_date(req.der)
        result = CalculoService.calcular_aposentadoria(segurado, der, req.tipo)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    cenarios = [cenario_to_response(c) for c in result.get("cenarios", [])]
    melhor = cenario_to_response(result["melhor"]) if result.get("melhor") else None
    rmi = result.get("rmi", Decimal("0"))

    return CalculoResponse(
        elegivel=result.get("elegivel", False),
        der=req.der,
        tipo=req.tipo,
        rmi=str(rmi),
        rmi_formatada=fmt_brl(rmi),
        melhor_cenario=melhor,
        todos_cenarios=cenarios,
        erros=result.get("erros", []),
    )


@router.post("/auxilio-doenca", response_model=CalculoResponse)
def calcular_auxilio_doenca(req: CalculoAuxilioDoencaRequest):
    try:
        segurado = segurado_from_schema(req.segurado)
        der = parse_date(req.der)
        result = CalculoService.calcular_auxilio_doenca(segurado, der, req.acidentario)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    r = result["resultado"]
    cenarios = [cenario_to_response(r)]
    rmi = result.get("rmi", Decimal("0"))

    return CalculoResponse(
        elegivel=result["elegivel"],
        der=req.der,
        tipo=result["tipo"],
        rmi=str(rmi),
        rmi_formatada=fmt_brl(rmi),
        melhor_cenario=cenarios[0] if result["elegivel"] else None,
        todos_cenarios=cenarios,
    )


@router.post("/invalidez", response_model=CalculoResponse)
def calcular_invalidez(req: CalculoInvalidezRequest):
    try:
        segurado = segurado_from_schema(req.segurado)
        der = parse_date(req.der)
        result = CalculoService.calcular_invalidez(
            segurado, der, req.acidentaria, req.grande_invalido
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    r = result["resultado"]
    cenarios = [cenario_to_response(r)]
    rmi = result.get("rmi", Decimal("0"))

    return CalculoResponse(
        elegivel=result["elegivel"],
        der=req.der,
        tipo=result["tipo"],
        rmi=str(rmi),
        rmi_formatada=fmt_brl(rmi),
        melhor_cenario=cenarios[0] if result["elegivel"] else None,
        todos_cenarios=cenarios,
    )


@router.post("/pensao-morte", response_model=CalculoResponse)
def calcular_pensao_morte(req: CalculoPensaoRequest):
    try:
        segurado = segurado_from_schema(req.segurado)
        der = parse_date(req.der)
        data_obito = parse_date(req.data_obito)
        rma = Decimal(_limpar_valor(req.rma_instituidor)) if req.rma_instituidor else None
        result = CalculoService.calcular_pensao_morte(
            segurado, der, req.num_dependentes, data_obito,
            req.tem_dependente_invalido, rma,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    r = result["resultado"]
    cenarios = [cenario_to_response(r)]
    rmi = result.get("rmi", Decimal("0"))

    return CalculoResponse(
        elegivel=result["elegivel"],
        der=req.der,
        tipo="B21",
        rmi=str(rmi),
        rmi_formatada=fmt_brl(rmi),
        melhor_cenario=cenarios[0] if result["elegivel"] else None,
        todos_cenarios=cenarios,
    )


@router.post("/resumo", response_model=ResumoSeguradoResponse)
def resumo_segurado(req: CalculoAposentadoriaRequest):
    """Retorna resumo rápido (TC, carência, SB estimado) sem fazer cálculo completo."""
    try:
        segurado = segurado_from_schema(req.segurado)
        der = parse_date(req.der)
        r = CalculoService.resumo_segurado(segurado, der)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    from ..schemas import TempoContribuicaoResponse
    tc = r["tempo_contribuicao"]

    return ResumoSeguradoResponse(
        nome=r["nome"],
        cpf=r.get("cpf"),
        data_nascimento=r["data_nascimento"].strftime("%d/%m/%Y"),
        sexo=r["sexo"],
        idade_na_der=r["idade_na_der"],
        tempo_contribuicao=TempoContribuicaoResponse(**tc),
        carencia_meses=r["carencia_meses"],
        teto_vigente=str(r["teto_vigente"]),
        piso_vigente=str(r["piso_vigente"]),
        num_vinculos=r["num_vinculos"],
        salario_beneficio=str(r["salario_beneficio"]) if r.get("salario_beneficio") else None,
        media_salarios=str(r["media_salarios"]) if r.get("media_salarios") else None,
    )


@router.post("/revisao/vida-toda", response_model=RevisaoVidaTodaResponse, deprecated=True)
def revisao_vida_toda(req: RevisaoVidaTodaRequest):
    """
    DEPRECATED: A Revisão da Vida Toda foi DEFINITIVAMENTE ENCERRADA pelo STF
    em 26/11/2025 (Embargos de Declaração do Tema 1102).
    ADIs 2.110 e 2.111 reverteram a tese por 8x3.
    Esta rota é mantida apenas por compatibilidade.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Revisao da Vida Toda ENCERRADA. O STF, em 26/11/2025, encerrou "
            "definitivamente o Tema 1102 nos Embargos de Declaracao. "
            "ADIs 2.110 e 2.111 (21/03/2024) reverteram a tese por 8x3. "
            "Nao cabe mais acao com base nesta revisao."
        ),
    )


@router.post("/revisao/teto", response_model=RevisaoTetoResponse)
def revisao_teto(req: RevisaoTetoRequest):
    try:
        result = CalculoService.calcular_revisao_teto(
            dib=parse_date(req.dib),
            rmi_original=Decimal(_limpar_valor(req.rmi_original)),
            sb_original=Decimal(_limpar_valor(req.sb_original)),
            der_revisao=parse_date(req.der_revisao),
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    return RevisaoTetoResponse(
        ec20_aplicavel=result["ec20_aplicavel"],
        ec41_aplicavel=result["ec41_aplicavel"],
        rmi_original=req.rmi_original,
        rmi_revisada=str(result["rmi_revisada"]),
        diferenca_mensal=str(result["diferenca_mensal"]),
        rmi_pos_ec20=str(result["rmi_pos_ec20"]) if result.get("rmi_pos_ec20") else None,
        rmi_pos_ec41=str(result["rmi_pos_ec41"]) if result.get("rmi_pos_ec41") else None,
    )


def _limpar_valor(v: str) -> str:
    """Limpa valor monetário: remove R$, espaços, converte formato BR."""
    import re
    s = re.sub(r'[R$\s]', '', v).strip()
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        pontos = s.count('.')
        if pontos > 1:
            idx = s.rfind('.')
            s = s[:idx].replace('.', '') + '.' + s[idx + 1:]
    return s


@router.post("/atrasados", response_model=ParcelasAtrasadasResponse)
def calcular_atrasados(req: AtrasadosRequest):
    try:
        result = CalculoService.calcular_atrasados(
            dib=parse_date(req.dib),
            rmi_original=Decimal(_limpar_valor(req.rmi_original)),
            data_atualizacao=parse_date(req.data_atualizacao),
            data_ajuizamento=parse_date(req.data_ajuizamento) if req.data_ajuizamento else None,
            incluir_juros=req.incluir_juros,
            rmi_paga=Decimal(_limpar_valor(req.rmi_paga)) if req.rmi_paga else None,
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    parcelas_serializadas = []
    for p in result["parcelas"]:
        parcelas_serializadas.append({
            "competencia": p["competencia"],
            "valor_base": str(p["valor_base"]),
            "fator_correcao": str(p["fator_correcao"]),
            "valor_corrigido": str(p["valor_corrigido"]),
            "juros": str(p["juros"]),
            "total_parcela": str(p["total_parcela"]),
        })

    return ParcelasAtrasadasResponse(
        total_principal=str(result["total_principal"]),
        total_juros=str(result["total_juros"]),
        total_geral=str(result["total_geral"]),
        parcelas_calculadas=result["parcelas_calculadas"],
        parcelas_prescritas=result["parcelas_prescritas"],
        parcelas=parcelas_serializadas,
        tipo_calculo=result.get("tipo_calculo", "integral"),
        rmi_correta=str(result["rmi_correta"]) if result.get("rmi_correta") else None,
        rmi_paga=str(result["rmi_paga"]) if result.get("rmi_paga") else None,
        diferenca_mensal=str(result["diferenca_mensal"]) if result.get("diferenca_mensal") else None,
        explicacao=result.get("explicacao"),
    )
