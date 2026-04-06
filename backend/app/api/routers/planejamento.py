"""
Rota de planejamento previdenciário.
"""
from __future__ import annotations
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..converters import segurado_from_schema, parse_date
from ..schemas import SeguradoSchema

router = APIRouter(prefix="/planejamento", tags=["Planejamento Previdenciário"])


class PcDRequest(BaseModel):
    segurado: SeguradoSchema
    der: str
    grau_deficiencia: str  # GRAVE, MODERADA, LEVE
    periodos_pcd: list  # [{grau, data_inicio, data_fim}]


class PlanejamentoRequest(BaseModel):
    segurado: SeguradoSchema
    der: str
    salario_projetado: Optional[str] = None
    beneficios: Optional[list] = None  # Benefícios detectados do CNIS


@router.post("/projecao")
def projecao_aposentadoria(req: PlanejamentoRequest):
    """
    Projeta as datas de aposentadoria para cada regra de transição.
    Calcula quando o segurado se tornará elegível continuando a contribuir.
    """
    try:
        from ...domain.planejamento.projecao import calcular_planejamento
        from ...domain.models.segurado import BeneficioAnterior
        from ...domain.enums import TipoBeneficio
        segurado = segurado_from_schema(req.segurado)
        der = parse_date(req.der)
        sal = Decimal(req.salario_projetado) if req.salario_projetado else None

        # Converter benefícios do CNIS em BeneficioAnterior para cálculo de TC
        # (auxílio-doença intercalado conta como TC)
        if req.beneficios:
            _MAPA_ESP = {
                31: TipoBeneficio.AUXILIO_DOENCA_PREV,
                91: TipoBeneficio.AUXILIO_DOENCA_ACID,
                32: TipoBeneficio.APOSENTADORIA_INVALIDEZ_PREV,
                41: TipoBeneficio.APOSENTADORIA_IDADE,
                42: TipoBeneficio.APOSENTADORIA_IDADE_RURAL,
                46: TipoBeneficio.APOSENTADORIA_ESPECIAL,
                57: TipoBeneficio.APOSENTADORIA_TEMPO_CONTRIB,
            }
            for b in req.beneficios:
                cod = b.get("especie_codigo", 0)
                if isinstance(cod, str):
                    try:
                        cod = int(cod)
                    except ValueError:
                        cod = 0
                especie = _MAPA_ESP.get(cod, TipoBeneficio.AUXILIO_DOENCA_PREV)
                dib = parse_date(b["data_inicio"]) if b.get("data_inicio") else None
                dcb = parse_date(b["data_fim"]) if b.get("data_fim") else None
                if b.get("situacao") == "ATIVO":
                    dcb = None
                if dib:
                    segurado.beneficios_anteriores.append(BeneficioAnterior(
                        numero_beneficio=b.get("nb", ""),
                        especie=especie,
                        dib=dib,
                        dcb=dcb,
                    ))

        resultado = calcular_planejamento(segurado, der, sal)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Se há benefícios ativos, executar análise de revisão automática
    beneficio_ativo = None
    if req.beneficios:
        beneficio_ativo = next(
            (b for b in req.beneficios if b.get("situacao") == "ATIVO"), None
        )
        if beneficio_ativo:
            # 1) Análise genérica de tipos de revisão
            try:
                from ...domain.revisao.analise_revisao import analisar_possibilidade_revisao
                dp = req.segurado.dados_pessoais
                vinculos_dict = []
                for v in req.segurado.vinculos:
                    vinculos_dict.append({
                        "data_inicio": v.data_inicio,
                        "data_fim": v.data_fim,
                        "empregador_nome": v.empregador_nome,
                    })
                resultado["analise_revisao"] = analisar_possibilidade_revisao(
                    dados_pessoais={"nome": dp.nome, "sexo": dp.sexo},
                    vinculos=vinculos_dict,
                    beneficio=beneficio_ativo,
                    der_base=der,
                )
            except Exception:
                pass

            # 2) REVISÃO COMPLETA: recalcular RMI na DER com cenários
            try:
                from ...domain.transicao.comparador import comparar_todas
                from ...domain.tempo.contagem import calcular_tempo_contribuicao, calcular_carencia
                from copy import deepcopy

                # DER original = data do requerimento (usar a DER informada pelo usuário)
                der_revisao = der

                # RMI que o INSS concedeu (se informada no benefício)
                rmi_inss_str = beneficio_ativo.get("rmi", "0")
                try:
                    rmi_inss = Decimal(str(rmi_inss_str).replace(",", ".")) if rmi_inss_str else Decimal("0")
                except Exception:
                    rmi_inss = Decimal("0")

                # Cenário A: Cálculo NORMAL (como o INSS fez — sem especial)
                seg_normal = deepcopy(segurado)
                for v in seg_normal.vinculos:
                    v.tipo_atividade = segurado.vinculos[0].__class__.__bases__[0] if False else v.tipo_atividade
                # Pegar os cenários na DER com os dados como estão
                cenarios_normal = comparar_todas(segurado, der_revisao)
                elegiveis_normal = [c for c in cenarios_normal if c.elegivel]
                melhor_normal = max(elegiveis_normal, key=lambda c: c.rmi_teto) if elegiveis_normal else None

                # TC na DER
                tc_na_der = calcular_tempo_contribuicao(
                    segurado.vinculos, der_revisao, segurado.sexo,
                    beneficios_anteriores=segurado.beneficios_anteriores,
                )
                carencia_na_der = calcular_carencia(
                    segurado.vinculos, der_revisao,
                    beneficios_anteriores=segurado.beneficios_anteriores,
                )

                # Cenário B: Se algum vínculo está marcado como especial, calcular o cenário
                tem_especial = any(v.is_especial for v in segurado.vinculos)

                cenarios_revisao = {
                    "modo": "revisao",
                    "der_revisao": der_revisao.strftime("%d/%m/%Y"),
                    "rmi_inss": str(rmi_inss) if rmi_inss > 0 else None,
                    "tc_na_der": {
                        "anos": tc_na_der.anos,
                        "meses": tc_na_der.meses_restantes,
                        "dias": tc_na_der.dias_restantes,
                        "total_dias": tc_na_der.dias_total,
                        "dias_especial": tc_na_der.dias_especial_convertido,
                        "dias_comum": tc_na_der.dias_comum,
                    },
                    "carencia_na_der": carencia_na_der,
                    "tem_especial": tem_especial,
                    "cenarios": [],
                }

                # Adicionar cada cenário elegível
                for c in cenarios_normal:
                    cen = {
                        "regra": c.nome_regra,
                        "base_legal": c.base_legal,
                        "elegivel": c.elegivel,
                        "rmi": str(c.rmi_teto),
                        "rmi_formatada": c.rmi_formatada,
                        "salario_beneficio": str(c.salario_beneficio) if c.salario_beneficio else "0",
                        "coeficiente": str(c.coeficiente) if c.coeficiente else "0",
                        "fator_previdenciario": str(c.fator_previdenciario) if c.fator_previdenciario else None,
                    }
                    # Se RMI do INSS foi informada, calcular diferença
                    if rmi_inss > 0 and c.elegivel and c.rmi_teto > 0:
                        diferenca = c.rmi_teto - rmi_inss
                        cen["diferenca_mensal"] = str(diferenca)
                        cen["diferenca_favoravel"] = diferenca > 0
                    cenarios_revisao["cenarios"].append(cen)

                # Melhor benefício na DER (princípio do melhor benefício)
                if melhor_normal:
                    cenarios_revisao["melhor_beneficio"] = {
                        "regra": melhor_normal.nome_regra,
                        "rmi": str(melhor_normal.rmi_teto),
                        "rmi_formatada": melhor_normal.rmi_formatada,
                    }
                    if rmi_inss > 0:
                        dif = melhor_normal.rmi_teto - rmi_inss
                        cenarios_revisao["melhor_beneficio"]["diferenca_mensal"] = str(dif)
                        cenarios_revisao["melhor_beneficio"]["diferenca_favoravel"] = dif > 0
                        if dif > 0:
                            cenarios_revisao["melhor_beneficio"]["explicacao"] = (
                                f"Na DER ({der_revisao.strftime('%d/%m/%Y')}), o segurado tinha direito "
                                f"a RMI de R$ {melhor_normal.rmi_formatada} pela regra "
                                f"\"{melhor_normal.nome_regra}\", mas o INSS concedeu "
                                f"R$ {rmi_inss:.2f}. Diferenca mensal: R$ {dif:.2f}. "
                                f"Fundamentacao: Art. 687, IN PRES/INSS 128/2022 — "
                                f"principio do melhor beneficio (STF Tema 334, RE 630.501/RS)."
                            )

                # Se tem especial, mostrar o ganho
                if tem_especial:
                    vinculos_especiais = [v for v in segurado.vinculos if v.is_especial]
                    cenarios_revisao["especial_info"] = {
                        "total_vinculos_especiais": len(vinculos_especiais),
                        "vinculos": [],
                    }
                    for v in vinculos_especiais:
                        dias_brutos = (min(v.data_fim or der_revisao, der_revisao) - v.data_inicio).days + 1
                        from ...domain.tempo.conversao_especial import fator_conversao as fc
                        fator = fc(v.tipo_atividade, segurado.sexo)
                        dias_convertidos = int(Decimal(str(dias_brutos)) * fator)
                        ganho = dias_convertidos - dias_brutos
                        cenarios_revisao["especial_info"]["vinculos"].append({
                            "empregador": v.empregador_nome or "—",
                            "periodo": f"{v.data_inicio.strftime('%d/%m/%Y')} a {(v.data_fim or der_revisao).strftime('%d/%m/%Y')}",
                            "tipo": v.tipo_atividade.value,
                            "dias_reais": dias_brutos,
                            "fator": str(fator),
                            "dias_convertidos": dias_convertidos,
                            "ganho_dias": ganho,
                            "ganho_texto": f"+{ganho // 365}a {(ganho % 365) // 30}m {ganho % 30}d",
                        })
                    cenarios_revisao["especial_info"]["total_ganho_dias"] = sum(
                        vi["ganho_dias"] for vi in cenarios_revisao["especial_info"]["vinculos"]
                    )

                resultado["cenarios_revisao"] = cenarios_revisao
            except Exception as e:
                resultado["cenarios_revisao"] = {"erro": str(e)}

    # Serializar (Decimal, date → str/string)
    projecoes_serial = []
    for p in resultado["projecoes"]:
        ps = dict(p)
        if ps.get("data_elegibilidade"):
            de = ps["data_elegibilidade"]
            ps["data_elegibilidade"] = de.strftime("%d/%m/%Y") if hasattr(de, 'strftime') else str(de)
        if ps.get("rmi_projetada") is not None:
            ps["rmi_projetada"] = str(ps["rmi_projetada"])
        if ps.get("salario_beneficio") is not None:
            ps["salario_beneficio"] = str(ps["salario_beneficio"])
        if ps.get("coeficiente") is not None:
            ps["coeficiente"] = str(ps["coeficiente"])
        if ps.get("fator_previdenciario") is not None:
            ps["fator_previdenciario"] = str(ps["fator_previdenciario"])
        tc = ps.get("tc_na_data")
        if tc is not None:
            ps["tc_na_data"] = {
                "anos": tc.anos,
                "meses": tc.meses_restantes,
                "dias": tc.dias_restantes,
                "total_dias": tc.dias_total,
            }
        projecoes_serial.append(ps)

    tc = resultado["tc_atual"]

    # Serializar cenários de vida (Decimal → str)
    cenarios_vida_serial = []
    for cv in resultado.get("cenarios_vida", []):
        cvs = dict(cv)
        for k in ("monthly_cost", "fgts_mensal", "annual_cost", "total_cost_until_retirement",
                   "custo_total_com_mei"):
            if k in cvs and isinstance(cvs[k], Decimal):
                cvs[k] = str(cvs[k])
        if isinstance(cvs.get("impact_on_rmi"), Decimal):
            cvs["impact_on_rmi"] = f"R$ {cvs['impact_on_rmi']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        cenarios_vida_serial.append(cvs)

    # Serializar pensão (Decimal → str)
    pensao = resultado.get("pensao_projetada", {})
    if pensao:
        pensao_serial = dict(pensao)
        if isinstance(pensao_serial.get("rmi_base"), Decimal):
            pensao_serial["rmi_base"] = str(pensao_serial["rmi_base"])
        cenarios_pensao = []
        for c in pensao_serial.get("cenarios", []):
            cs = dict(c)
            if isinstance(cs.get("valor"), Decimal):
                cs["valor"] = str(cs["valor"])
            cenarios_pensao.append(cs)
        pensao_serial["cenarios"] = cenarios_pensao
    else:
        pensao_serial = pensao

    return {
        "der_base": resultado["der_base"].strftime("%d/%m/%Y") if hasattr(resultado["der_base"], 'strftime') else str(resultado["der_base"]),
        "tc_atual": tc,
        "carencia_meses": resultado.get("carencia_meses", 0),
        "analise_tc_carencia": resultado.get("analise_tc_carencia", {}),
        "salario_projetado": str(resultado["salario_projetado"]),
        "elegiveis_agora": resultado["elegiveis_agora"],
        "melhor_data": (resultado["melhor_data"].strftime("%d/%m/%Y") if hasattr(resultado["melhor_data"], 'strftime') else str(resultado["melhor_data"])) if resultado["melhor_data"] else None,
        "melhor_regra": resultado["melhor_regra"],
        "melhor_rmi": str(resultado["melhor_rmi"]),
        "projecoes": projecoes_serial,
        "recomendacao": resultado["recomendacao"],
        "argumentos_cliente": resultado["argumentos_cliente"],
        "custo_beneficio": resultado["custo_beneficio"],
        "expectativa_vida": resultado["expectativa_vida"],
        "qualidade_segurado": resultado.get("qualidade_segurado", {}),
        "pensao_projetada": pensao_serial,
        "cenarios_vida": cenarios_vida_serial,
        "plano_acao": resultado.get("plano_acao", []),
        "resumo_executivo": resultado.get("resumo_executivo", {}),
        "score_prontidao": resultado.get("score_prontidao", {}),
        "marcos_legais": resultado.get("marcos_legais", []),
        "competencias_sem_salario": resultado.get("competencias_sem_salario", {}),
        "analise_especial": resultado.get("analise_especial", []),
        "analise_revisao": resultado.get("analise_revisao", {}),
        "cenarios_revisao": resultado.get("cenarios_revisao", {}),
        "memoria_calculo": resultado.get("memoria_calculo", {}),
    }


@router.post("/pcd")
def calculo_pcd(req: PcDRequest):
    """Calcula aposentadoria PcD (LC 142/2013)."""
    try:
        from ...domain.pcd.calculo_pcd import calcular_aposentadoria_pcd, PeriodoPcD, GrauDeficiencia
        segurado = segurado_from_schema(req.segurado)
        der = parse_date(req.der)

        periodos = []
        for p in req.periodos_pcd:
            periodos.append(PeriodoPcD(
                grau=GrauDeficiencia(p["grau"]),
                data_inicio=parse_date(p["data_inicio"]),
                data_fim=parse_date(p["data_fim"]) if p.get("data_fim") else None,
            ))

        # Collect all salaries
        salarios = []
        tempo_comum = 0
        for v in segurado.vinculos:
            for c in v.contribuicoes:
                salarios.append(c.salario_contribuicao)

        resultado = calcular_aposentadoria_pcd(
            sexo=segurado.sexo.name.lower() if hasattr(segurado.sexo, 'name') else str(segurado.sexo).lower(),
            data_nascimento=segurado.dados_pessoais.data_nascimento,
            periodos_pcd=periodos,
            tempo_comum_dias=tempo_comum,
            carencia_meses=len(salarios),
            salarios_contribuicao=salarios,
            data_referencia=der,
        )
        return resultado
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
