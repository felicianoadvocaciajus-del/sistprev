"""
Conversores entre schemas Pydantic e objetos de domínio.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional, List, Any, Dict

from .schemas import (
    SeguradoSchema, VinculoSchema, ContribuicaoSchema,
    CenarioResponse, TempoContribuicaoResponse, BeneficioAnteriorSchema,
)
from ..domain.models.segurado import Segurado, DadosPessoais, BeneficioAnterior
from ..domain.models.vinculo import Vinculo
from ..domain.models.contribuicao import Contribuicao, Competencia
from ..domain.models.resultado import ResultadoRegra, MemoriaCalculo
from ..domain.enums import (
    Sexo, TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado,
    TipoBeneficio,
)


def segurado_from_schema(s: SeguradoSchema) -> Segurado:
    dp = DadosPessoais(
        nome=s.dados_pessoais.nome,
        data_nascimento=parse_date(s.dados_pessoais.data_nascimento),
        sexo=Sexo.MASCULINO if s.dados_pessoais.sexo == "MASCULINO" else Sexo.FEMININO,
        cpf=s.dados_pessoais.cpf or "",
        nit=s.dados_pessoais.nit or "",
    )
    vinculos = [vinculo_from_schema(v) for v in s.vinculos]

    # Reconstruir benefícios anteriores (B31 etc.) — ESSENCIAL para TC
    beneficios_anteriores = []
    for b in (s.beneficios_anteriores or []):
        try:
            especie = TipoBeneficio(b.especie)
        except (ValueError, KeyError):
            # Tentar pelo nome do enum
            try:
                especie = TipoBeneficio[b.especie]
            except (ValueError, KeyError):
                continue  # Espécie desconhecida, pular
        beneficios_anteriores.append(BeneficioAnterior(
            numero_beneficio=b.numero_beneficio or "",
            especie=especie,
            dib=parse_date(b.dib),
            dcb=parse_date(b.dcb) if b.dcb else None,
            rmi=Decimal(b.rmi) if b.rmi else Decimal("0"),
        ))

    return Segurado(
        dados_pessoais=dp,
        vinculos=vinculos,
        beneficios_anteriores=beneficios_anteriores,
    )


def vinculo_from_schema(v: VinculoSchema) -> Vinculo:
    contribuicoes = [contribuicao_from_schema(c) for c in v.contribuicoes]
    return Vinculo(
        tipo_vinculo=TipoVinculo[v.tipo_vinculo],
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade[v.tipo_atividade],
        empregador_cnpj=v.empregador_cnpj,
        empregador_nome=v.empregador_nome,
        data_inicio=parse_date(v.data_inicio),
        data_fim=parse_date(v.data_fim) if v.data_fim else None,
        contribuicoes=contribuicoes,
        origem=OrigemDado.MANUAL,
        indicadores=v.indicadores or "",
    )


def contribuicao_from_schema(c: ContribuicaoSchema) -> Contribuicao:
    mes = int(c.competencia[:2])
    ano = int(c.competencia[3:])
    comp = Competencia.criar(ano, mes)
    return Contribuicao(
        competencia=comp,
        salario_contribuicao=Decimal(c.salario),
    )


def cenario_to_response(r: ResultadoRegra) -> CenarioResponse:
    tc_resp = None
    if r.tempo_contribuicao:
        tc = r.tempo_contribuicao
        tc_resp = TempoContribuicaoResponse(
            anos=tc.anos,
            meses=tc.meses_restantes,
            dias=tc.dias_restantes,
            total_dias=tc.dias_total,
            anos_decimal=float(tc.anos_decimal),
        )
    return CenarioResponse(
        nome_regra=r.nome_regra,
        base_legal=r.base_legal,
        elegivel=r.elegivel,
        rmi=str(r.rmi_teto),
        rmi_formatada=r.rmi_formatada,
        salario_beneficio=str(r.salario_beneficio),
        coeficiente=str(r.coeficiente),
        fator_previdenciario=str(r.fator_previdenciario) if r.fator_previdenciario else None,
        tempo_contribuicao=tc_resp,
        faltam_dias=r.faltam_dias,
        avisos=r.avisos,
        memoria=_memoria_to_list(r.memoria),
    )


def _memoria_to_list(mem: MemoriaCalculo) -> List[Dict[str, Any]]:
    resultado = []
    for item in mem.itens:
        d: Dict[str, Any] = {
            "descricao": item.descricao,
            "nivel": item.nivel,
        }
        if item.valor is not None:
            d["valor"] = _format_valor(item.valor)
        if item.formula:
            d["formula"] = item.formula
        if item.fundamentacao:
            d["fundamentacao"] = {
                "norma": item.fundamentacao.norma,
                "artigo": item.fundamentacao.artigo,
                "descricao": item.fundamentacao.descricao,
            }
        resultado.append(d)
    return resultado


def _format_valor(v: Any) -> str:
    if isinstance(v, Decimal):
        return str(v)
    return str(v)


def parse_date(s) -> date:
    if isinstance(s, date):
        return s
    if isinstance(s, str):
        s = s.strip()
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                return date(int(parts[2]), int(parts[1]), int(parts[0]))
        return date.fromisoformat(s)
    raise ValueError(f"Data inválida: {s!r}")


def fmt_decimal(d: Optional[Decimal]) -> Optional[str]:
    return str(d) if d is not None else None


def fmt_brl(d: Optional[Decimal]) -> str:
    if d is None:
        return "R$ 0,00"
    return f"R$ {d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
