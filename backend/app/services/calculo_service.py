"""
Serviço central de cálculo previdenciário.

Orquestra: parsing de documentos → montagem do Segurado → execução
de todos os cálculos → retorno de resultado unificado para a API.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from ..domain.models.segurado import Segurado, DadosPessoais
from ..domain.models.vinculo import Vinculo
from ..domain.models.contribuicao import Contribuicao, Competencia
from ..domain.models.resultado import ResultadoCalculo, ResultadoRegra
from ..domain.enums import TipoBeneficio, Sexo, TipoVinculo, RegimePrevidenciario, TipoAtividade, OrigemDado
from ..domain.transicao.comparador import comparar_todas, melhor_regra
from ..domain.beneficios.aposentadoria_idade import CalculadoraAposentadoriaIdade
from ..domain.beneficios.aposentadoria_especial import CalculadoraAposentadoriaEspecial
from ..domain.beneficios.auxilio_doenca import CalculadoraAuxilioDoenca
from ..domain.beneficios.invalidez import CalculadoraInvalidez
from ..domain.beneficios.pensao_morte import CalculadoraPensaoMorte
from ..domain.tempo.contagem import calcular_tempo_contribuicao, calcular_carencia
from ..domain.salario.pbc import calcular_salario_beneficio
from ..domain.indices import teto_na_data
from ..domain.indices.salario_minimo import salario_minimo_na_data
from ..revisoes.vida_toda import calcular_revisao_vida_toda
from ..revisoes.revisao_teto import calcular_revisao_teto
from ..revisoes.liquidacao_sentenca import calcular_atrasados


class CalculoService:
    """
    Serviço de cálculo — não guarda estado entre chamadas.
    Todos os métodos são estáticos/de classe.
    """

    @staticmethod
    def calcular_aposentadoria(
        segurado: Segurado,
        der: date,
        tipo: str = "transicao",
    ) -> Dict[str, Any]:
        """
        Calcula aposentadoria por tempo de contribuição ou por idade.

        tipo:
          "transicao"  → compara todas as 5 regras de transição + permanente
          "idade"      → apenas regra de idade (60H/57M permanente)
          "especial_15" / "especial_20" / "especial_25" → atividade especial
        """
        result: Dict[str, Any] = {"der": der, "tipo": tipo, "erros": []}

        if tipo == "transicao":
            cenarios = comparar_todas(segurado, der)
            melhor = melhor_regra(segurado, der)
            result["cenarios"] = cenarios
            result["melhor"] = melhor
            result["elegivel"] = melhor is not None and melhor.elegivel
            result["rmi"] = melhor.rmi_teto if melhor and melhor.elegivel else Decimal("0")

        elif tipo == "idade":
            calc = CalculadoraAposentadoriaIdade()
            rc = calc.calcular(segurado, der)
            regra = rc.cenarios[0] if rc.cenarios else None
            result["cenarios"] = rc.cenarios
            result["melhor"] = regra
            result["elegivel"] = rc.elegivel
            result["rmi"] = regra.rmi_teto if regra and rc.elegivel else Decimal("0")

        elif tipo in ("especial_15", "especial_20", "especial_25"):
            anos = int(tipo.split("_")[1])
            calc = CalculadoraAposentadoriaEspecial(anos_especial=anos)
            rc = calc.calcular(segurado, der)
            regra = rc.cenarios[0] if rc.cenarios else None
            result["cenarios"] = rc.cenarios
            result["melhor"] = regra
            result["elegivel"] = rc.elegivel
            result["rmi"] = regra.rmi_teto if regra and rc.elegivel else Decimal("0")

        else:
            result["erros"].append(f"Tipo de cálculo desconhecido: {tipo}")

        return result

    @staticmethod
    def calcular_auxilio_doenca(
        segurado: Segurado,
        der: date,
        acidentario: bool = False,
    ) -> Dict[str, Any]:
        calc = CalculadoraAuxilioDoenca(acidentario=acidentario)
        rc = calc.calcular(segurado, der)
        regra = rc.cenarios[0] if rc.cenarios else None
        return {
            "der": der,
            "tipo": "B91" if acidentario else "B31",
            "elegivel": rc.elegivel,
            "rmi": regra.rmi_teto if regra and rc.elegivel else Decimal("0"),
            "resultado": regra,
        }

    @staticmethod
    def calcular_invalidez(
        segurado: Segurado,
        der: date,
        acidentaria: bool = False,
        grande_invalido: bool = False,
    ) -> Dict[str, Any]:
        calc = CalculadoraInvalidez(acidentaria=acidentaria, grande_invalido=grande_invalido)
        rc = calc.calcular(segurado, der)
        regra = rc.cenarios[0] if rc.cenarios else None
        return {
            "der": der,
            "tipo": "B92" if acidentaria else "B32",
            "elegivel": rc.elegivel,
            "rmi": regra.rmi_teto if regra and rc.elegivel else Decimal("0"),
            "resultado": regra,
        }

    @staticmethod
    def calcular_pensao_morte(
        segurado: Segurado,
        der: date,
        num_dependentes: int,
        data_obito: date,
        tem_dependente_invalido: bool = False,
        rma_instituidor: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        calc = CalculadoraPensaoMorte(
            num_dependentes=num_dependentes,
            tem_dependente_invalido=tem_dependente_invalido,
            data_obito=data_obito,
            rma_instituidor=rma_instituidor,
        )
        rc = calc.calcular(segurado, der)
        regra = rc.cenarios[0] if rc.cenarios else None
        return {
            "der": der,
            "tipo": "B21",
            "elegivel": rc.elegivel,
            "rmi": regra.rmi_teto if regra and rc.elegivel else Decimal("0"),
            "resultado": regra,
        }

    @staticmethod
    def calcular_revisao_vida_toda(
        segurado: Segurado,
        der: date,
        dib: date,
        rmi_original: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        return calcular_revisao_vida_toda(segurado, der, dib, rmi_original)

    @staticmethod
    def calcular_revisao_teto(
        dib: date,
        rmi_original: Decimal,
        sb_original: Decimal,
        der_revisao: date,
    ) -> Dict[str, Any]:
        return calcular_revisao_teto(dib, rmi_original, sb_original, der_revisao)

    @staticmethod
    def calcular_atrasados(
        dib: date,
        rmi_original: Decimal,
        data_atualizacao: date,
        data_ajuizamento: Optional[date] = None,
        incluir_juros: bool = True,
        rmi_paga: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        return calcular_atrasados(dib, rmi_original, data_atualizacao, data_ajuizamento, incluir_juros, rmi_paga)

    @staticmethod
    def resumo_segurado(segurado: Segurado, der: date) -> Dict[str, Any]:
        """Dados básicos calculados do segurado para exibição no dashboard."""
        tc = calcular_tempo_contribuicao(
            segurado.vinculos, der, segurado.sexo,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        carencia = calcular_carencia(segurado.vinculos, der)
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)

        # Tentar calcular SB para preview
        sb_info: Dict[str, Any] = {}
        try:
            sb_info = calcular_salario_beneficio(
                segurado.vinculos, der,
                usar_regra_ec103=True,
                usar_vida_toda=False,
            )
        except Exception:
            pass

        return {
            "nome": segurado.dados_pessoais.nome,
            "cpf": segurado.dados_pessoais.cpf,
            "data_nascimento": segurado.dados_pessoais.data_nascimento,
            "sexo": segurado.dados_pessoais.sexo.value,
            "idade_na_der": float(segurado.idade_na(der)),
            "tempo_contribuicao": {
                "anos": tc.anos,
                "meses": tc.meses_restantes,
                "dias": tc.dias_restantes,
                "total_dias": tc.dias_total,
                "anos_decimal": float(tc.anos_decimal),
            },
            "carencia_meses": carencia,
            "teto_vigente": teto,
            "piso_vigente": piso,
            "num_vinculos": len(segurado.vinculos),
            "salario_beneficio": sb_info.get("salario_beneficio"),
            "media_salarios": sb_info.get("media"),
        }

    @staticmethod
    def montar_segurado_de_dados(dados: Dict[str, Any]) -> Segurado:
        """
        Constrói um objeto Segurado a partir de um dict (vindo da API).
        Usado quando os dados são inseridos manualmente ou editados.
        """
        from datetime import date as d
        dp = DadosPessoais(
            nome=dados["nome"],
            data_nascimento=_parse_date(dados["data_nascimento"]),
            sexo=Sexo[dados["sexo"].upper()],
            cpf=dados.get("cpf", ""),
            nit=dados.get("nit", ""),
        )

        vinculos = []
        for v_dict in dados.get("vinculos", []):
            contribuicoes = []
            for c_dict in v_dict.get("contribuicoes", []):
                comp_str = c_dict["competencia"]  # "MM/AAAA"
                comp = Competencia.criar(
                    int(comp_str[3:7]), int(comp_str[:2])
                )
                contribuicoes.append(Contribuicao(
                    competencia=comp,
                    salario_contribuicao=Decimal(str(c_dict["salario"])),
                ))

            v = Vinculo(
                tipo_vinculo=TipoVinculo[v_dict.get("tipo_vinculo", "EMPREGADO").upper()],
                regime=RegimePrevidenciario.RGPS,
                tipo_atividade=TipoAtividade[v_dict.get("tipo_atividade", "NORMAL").upper()],
                empregador_cnpj=v_dict.get("empregador_cnpj"),
                empregador_nome=v_dict.get("empregador_nome"),
                data_inicio=_parse_date(v_dict["data_inicio"]),
                data_fim=_parse_date(v_dict["data_fim"]) if v_dict.get("data_fim") else None,
                contribuicoes=contribuicoes,
                origem=OrigemDado.MANUAL,
            )
            vinculos.append(v)

        return Segurado(dados_pessoais=dp, vinculos=vinculos)


def _parse_date(s) -> date:
    if isinstance(s, date):
        return s
    if isinstance(s, str):
        if "/" in s:
            p = s.split("/")
            if len(p) == 3:
                return date(int(p[2]), int(p[1]), int(p[0]))
        return date.fromisoformat(s)
    raise ValueError(f"Data inválida: {s!r}")
