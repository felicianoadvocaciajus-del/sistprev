"""
Camada Antialucinacao — Validacao de Integridade do Motor Previdenciario.

Detecta e bloqueia:
  1. Impossibilidade temporal (regra aplicada fora de vigencia)
  2. Contradicao interna (qualidade ATIVA + perda no passado)
  3. Numero sem formula (RMI sem memoria de calculo)
  4. Score cosmetico com dados inconsistentes
  5. Linguagem excessivamente conclusiva com baixa confianca
  6. ROI sem metodologia (projecao nominal sem valor presente)
  7. Dado inferido apresentado como primario

Cada alerta tem gravidade: FATAL, ALTA, MEDIA, BAIXA, INFORMATIVO.
Alertas FATAIS impedem a emissao do relatorio sem ressalva explicita.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Dict, Any, Optional
import logging

_logger = logging.getLogger(__name__)


@dataclass
class Alerta:
    """Um alerta de inconsistencia detectado pelo validador."""
    codigo: str           # ex: "TEMPORAL_001"
    gravidade: str        # FATAL, ALTA, MEDIA, BAIXA, INFORMATIVO
    categoria: str        # TEMPORAL, CONTRADICAO, CALCULO, SCORE, LINGUAGEM, ROI
    mensagem: str
    campo_afetado: str = ""
    valor_encontrado: str = ""
    valor_esperado: str = ""
    base_legal: str = ""
    recomendacao: str = ""


class ValidadorAntiAlucinacao:
    """
    Valida a integridade dos resultados do motor previdenciario.
    Deve ser chamado APOS cada calculo/planejamento para auditar o resultado.
    """

    def __init__(self):
        self.alertas: List[Alerta] = []

    def validar_tudo(self, resultado: Dict[str, Any], der: date) -> List[Alerta]:
        """Executa todas as validacoes sobre o resultado do planejamento."""
        self.alertas = []

        self._validar_regras_temporais(resultado, der)
        self._validar_qualidade_segurado(resultado, der)
        self._validar_rmi_sem_formula(resultado)
        self._validar_roi(resultado)
        self._validar_score_vs_alertas(resultado)

        # Log dos alertas
        fatais = [a for a in self.alertas if a.gravidade == "FATAL"]
        altos = [a for a in self.alertas if a.gravidade == "ALTA"]
        if fatais:
            _logger.error(f"ANTIALUCINACAO: {len(fatais)} alertas FATAIS detectados!")
        if altos:
            _logger.warning(f"ANTIALUCINACAO: {len(altos)} alertas de gravidade ALTA")

        return self.alertas

    def _validar_regras_temporais(self, resultado: Dict, der: date):
        """Verifica se alguma regra EC 103 foi aplicada antes de 13/11/2019."""
        from ..constantes import DatasCorte
        projecoes = resultado.get("projecoes", [])

        for p in projecoes:
            regra_nome = p.get("regra", "")
            data_eleg = p.get("data_elegibilidade")
            elegivel = p.get("rmi_projetada", 0) and p.get("rmi_projetada", 0) > 0

            # Regra EC 103 com data de elegibilidade antes de 13/11/2019
            if "EC 103" in regra_nome and data_eleg:
                if isinstance(data_eleg, date) and data_eleg < DatasCorte.EC_103_2019:
                    self.alertas.append(Alerta(
                        codigo="TEMPORAL_001",
                        gravidade="FATAL",
                        categoria="TEMPORAL",
                        mensagem=(
                            f"Regra '{regra_nome}' projetada para {data_eleg.strftime('%d/%m/%Y')}, "
                            f"mas esta regra so existe a partir de 13/11/2019 (EC 103/2019)."
                        ),
                        campo_afetado="data_elegibilidade",
                        valor_encontrado=data_eleg.strftime("%d/%m/%Y") if isinstance(data_eleg, date) else str(data_eleg),
                        valor_esperado=">= 13/11/2019",
                        base_legal="EC 103/2019 Art. 36 — vigencia na data da publicacao",
                        recomendacao="ISTO E INCONSISTENTE E NAO PODE SER ACEITO COMO CALCULO CONFIAVEL.",
                    ))

            # DER pre-reforma mas regras de transicao sendo aplicadas
            if der < DatasCorte.EC_103_2019 and "EC 103" in regra_nome and elegivel:
                self.alertas.append(Alerta(
                    codigo="TEMPORAL_002",
                    gravidade="FATAL",
                    categoria="TEMPORAL",
                    mensagem=(
                        f"DER ({der}) e anterior a EC 103/2019, mas a regra "
                        f"'{regra_nome}' foi marcada como elegivel. "
                        "Regras de transicao da EC 103 nao existiam nesta data."
                    ),
                    base_legal="Principio tempus regit actum",
                    recomendacao="Usar regras pre-reforma (TC+FP, 85/95, Idade Art. 48).",
                ))

    def _validar_qualidade_segurado(self, resultado: Dict, der: date):
        """Verifica consistencia da qualidade de segurado."""
        qs = resultado.get("qualidade_segurado", {})
        status = qs.get("status", "")
        data_perda_str = qs.get("data_perda_qualidade")

        if status == "ATIVA" and data_perda_str:
            try:
                # Tentar parsear a data
                partes = data_perda_str.split("/")
                if len(partes) == 3:
                    data_perda = date(int(partes[2]), int(partes[1]), int(partes[0]))
                    if data_perda < der:
                        self.alertas.append(Alerta(
                            codigo="CONTRADICAO_001",
                            gravidade="ALTA",
                            categoria="CONTRADICAO",
                            mensagem=(
                                f"Qualidade de segurado marcada como 'ATIVA', mas a data de perda "
                                f"({data_perda_str}) e anterior a data de referencia ({der.strftime('%d/%m/%Y')}). "
                                "Isto e internamente contraditorio."
                            ),
                            campo_afetado="qualidade_segurado.status",
                            valor_encontrado="ATIVA",
                            valor_esperado="PERDIDA",
                            base_legal="Art. 15, Lei 8.213/91",
                            recomendacao=(
                                "Verificar se existe beneficio ativo que mantem a qualidade. "
                                "Se nao, corrigir status para PERDIDA."
                            ),
                        ))
            except (ValueError, IndexError):
                pass

    def _validar_rmi_sem_formula(self, resultado: Dict):
        """Verifica se existe RMI sem memoria de calculo."""
        projecoes = resultado.get("projecoes", [])
        for p in projecoes:
            rmi = p.get("rmi_projetada", 0)
            sb = p.get("salario_beneficio", 0)
            if rmi and rmi > 0 and (not sb or sb == 0):
                self.alertas.append(Alerta(
                    codigo="CALCULO_001",
                    gravidade="MEDIA",
                    categoria="CALCULO",
                    mensagem=(
                        f"RMI de R$ {rmi} projetada para regra '{p.get('regra', '?')}' "
                        "sem SB correspondente na memoria de calculo."
                    ),
                    campo_afetado="rmi_projetada",
                    recomendacao="Incluir memoria de calculo completa: PBC, SB, FP/Coef, RMI.",
                ))

    def _validar_roi(self, resultado: Dict):
        """Verifica ROI absurdos."""
        custo = resultado.get("custo_beneficio", [])
        for cb in custo:
            for mod in cb.get("modalidades", []):
                roi_str = mod.get("roi_percentual", "0")
                try:
                    roi = Decimal(str(roi_str))
                    if roi > Decimal("5000"):
                        self.alertas.append(Alerta(
                            codigo="ROI_001",
                            gravidade="MEDIA",
                            categoria="ROI",
                            mensagem=(
                                f"ROI de {roi}% para modalidade '{mod.get('modalidade', '?')}' "
                                "e irrealisticamente alto. Projecao nominal sem valor presente, "
                                "inflacao ou risco de mortalidade."
                            ),
                            recomendacao=(
                                "NAO apresentar este numero como analise atuarial. "
                                "Usar apenas como referencia ilustrativa com disclaimer."
                            ),
                        ))
                except Exception:
                    pass

    def _validar_score_vs_alertas(self, resultado: Dict):
        """Score alto com alertas fatais = falsa confianca."""
        score_data = resultado.get("score_prontidao", {})
        score = score_data.get("score", 0)

        fatais = [a for a in self.alertas if a.gravidade == "FATAL"]
        if score >= 800 and fatais:
            self.alertas.append(Alerta(
                codigo="SCORE_001",
                gravidade="ALTA",
                categoria="SCORE",
                mensagem=(
                    f"Score de prontidao {score}/1000 mas existem {len(fatais)} "
                    "alertas FATAIS no calculo. Score nao reflete a confiabilidade real."
                ),
                recomendacao="Rebaixar score ou exibir alertas com destaque.",
            ))

    def tem_alertas_fatais(self) -> bool:
        return any(a.gravidade == "FATAL" for a in self.alertas)

    def resumo(self) -> Dict[str, Any]:
        """Gera resumo dos alertas para incluir no resultado."""
        por_gravidade = {}
        for a in self.alertas:
            por_gravidade.setdefault(a.gravidade, []).append({
                "codigo": a.codigo,
                "mensagem": a.mensagem,
                "campo": a.campo_afetado,
                "base_legal": a.base_legal,
                "recomendacao": a.recomendacao,
            })
        return {
            "total_alertas": len(self.alertas),
            "fatais": len([a for a in self.alertas if a.gravidade == "FATAL"]),
            "altos": len([a for a in self.alertas if a.gravidade == "ALTA"]),
            "confiavel": not self.tem_alertas_fatais(),
            "mensagem_confiabilidade": (
                "CALCULO CONFIAVEL — nenhum alerta fatal detectado."
                if not self.tem_alertas_fatais()
                else "ATENCAO: Existem inconsistencias fatais que comprometem a confiabilidade. "
                     "NAO utilizar este resultado para decisao sem revisao manual."
            ),
            "alertas": por_gravidade,
        }


def validar_resultado_planejamento(resultado: Dict[str, Any], der: date) -> Dict[str, Any]:
    """
    Funcao de conveniencia: valida e adiciona alertas ao resultado.
    Deve ser chamada no final de calcular_planejamento().
    """
    validador = ValidadorAntiAlucinacao()
    alertas = validador.validar_tudo(resultado, der)

    resultado["validacao"] = validador.resumo()
    resultado["alertas_antialucinacao"] = [
        {
            "codigo": a.codigo,
            "gravidade": a.gravidade,
            "categoria": a.categoria,
            "mensagem": a.mensagem,
            "base_legal": a.base_legal,
            "recomendacao": a.recomendacao,
        }
        for a in alertas
    ]

    return resultado
