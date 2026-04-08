"""
Testes de REGRESSAO CRITICA — Previdenciario.

Estes testes garantem que bugs graves ja corrigidos NUNCA voltem.
Cada teste mapeia para um bug real que foi encontrado e corrigido.

Bugs cobertos:
  - Regras EC 103/2019 aplicadas antes de 13/11/2019 (temporal)
  - Regras pre-reforma aplicadas apos 13/11/2019
  - Direito Adquirido sem comparar ambos os regimes de SB
  - Qualidade de segurado ignorando beneficio ativo
  - Qualidade de segurado falso-positivo sem beneficio
  - Score cosmetico com alertas FATAIS
  - Regra 85/95 com calculo incorreto
  - ROI sem disclaimer
  - Validador antialucinacao nao detectando impossibilidade temporal
  - Campo regime_aplicado incorreto
"""
import pytest
from datetime import date
from decimal import Decimal
from typing import List

from app.domain.models.segurado import Segurado, DadosPessoais, BeneficioAnterior
from app.domain.models.vinculo import Vinculo
from app.domain.models.contribuicao import Contribuicao
from app.domain.enums import (
    Sexo, TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado,
    TipoBeneficio,
)
from app.domain.transicao.comparador import comparar_todas
from app.domain.transicao.regras import RegraDireitoAdquirido
from app.domain.transicao.regras_pre_reforma import Regra85_95
from app.domain.validacao.antialucinacao import ValidadorAntiAlucinacao
from app.domain.constantes import DatasCorte


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS: criacao de segurados para testes
# ─────────────────────────────────────────────────────────────────────────────

def _criar_contribuicoes(inicio: date, fim: date, salario: Decimal = Decimal("3000")) -> List[Contribuicao]:
    """Cria contribuicoes mensais continuas de inicio ate fim."""
    contribs = []
    atual = date(inicio.year, inicio.month, 1)
    fim_norm = date(fim.year, fim.month, 1)
    while atual <= fim_norm:
        contribs.append(Contribuicao(competencia=atual, salario_contribuicao=salario))
        if atual.month == 12:
            atual = date(atual.year + 1, 1, 1)
        else:
            atual = date(atual.year, atual.month + 1, 1)
    return contribs


def _criar_segurado(
    nome: str,
    dn: date,
    sexo: Sexo,
    inicio_contrib: date,
    fim_contrib: date,
    salario: Decimal = Decimal("3000"),
    beneficios_anteriores: list = None,
) -> Segurado:
    """Cria um segurado com um vinculo CLT e contribuicoes mensais continuas."""
    contribuicoes = _criar_contribuicoes(inicio_contrib, fim_contrib, salario)
    v = Vinculo(
        tipo_vinculo=TipoVinculo.EMPREGADO,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        data_inicio=inicio_contrib,
        data_fim=fim_contrib,
        contribuicoes=contribuicoes,
        origem=OrigemDado.MANUAL,
    )
    dp = DadosPessoais(nome=nome, data_nascimento=dn, sexo=sexo)
    return Segurado(
        dados_pessoais=dp,
        vinculos=[v],
        beneficios_anteriores=beneficios_anteriores or [],
    )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 1: EC 103/2019 NAO pode ser aplicada antes de 13/11/2019
# Bug: motor aplicava regras de transicao da EC 103 para DER pre-reforma
# ═════════════════════════════════════════════════════════════════════════════
class TestEC103NaoAplicadaAntesReforma:
    """
    Se DER < 13/11/2019, NENHUMA regra com 'EC 103' no nome pode aparecer.
    O comparador deve retornar APENAS regras pre-reforma (TC+FP, 85/95, Idade).
    """

    def test_der_2017_nao_contem_ec103(self):
        seg = _criar_segurado(
            "REGRESSAO EC103 PRE", date(1960, 1, 1), Sexo.MASCULINO,
            date(1982, 1, 1), date(2017, 6, 1),
        )
        der = date(2017, 6, 2)
        resultados = comparar_todas(seg, der)

        nomes = [r.nome_regra for r in resultados]
        for nome in nomes:
            assert "EC 103" not in nome, (
                f"Regra EC 103 encontrada para DER pre-reforma ({der}): {nome}"
            )

    def test_der_2017_contem_regras_pre_reforma(self):
        seg = _criar_segurado(
            "REGRESSAO PRE REFORMA", date(1960, 1, 1), Sexo.MASCULINO,
            date(1982, 1, 1), date(2017, 6, 1),
        )
        der = date(2017, 6, 2)
        resultados = comparar_todas(seg, der)

        nomes = [r.nome_regra for r in resultados]
        nomes_lower = [n.lower() for n in nomes]
        # Deve conter regra de TC + FP
        assert any("fator" in n or "tc" in n.lower() for n in nomes), (
            f"Nenhuma regra TC+FP encontrada para DER pre-reforma. Nomes: {nomes}"
        )
        # Deve conter regra 85/95
        assert any("85/95" in n for n in nomes), (
            f"Regra 85/95 nao encontrada para DER 2017. Nomes: {nomes}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 2: Regras pre-reforma NAO podem ser aplicadas apos 13/11/2019
# Bug: motor retornava regra de idade Art. 48 pre-reforma para DER pos-reforma
# ═════════════════════════════════════════════════════════════════════════════
class TestPreReformaNaoAplicadaAposReforma:
    """
    Se DER >= 13/11/2019, NAO pode haver regra 'Lei 8.213/91 Art. 48' (idade pre-reforma).
    Deve conter regras de transicao EC 103.
    """

    def test_der_2026_nao_contem_idade_pre_reforma(self):
        seg = _criar_segurado(
            "REGRESSAO POS REFORMA", date(1960, 1, 1), Sexo.MASCULINO,
            date(1990, 1, 1), date(2026, 4, 1),
        )
        der = date(2026, 4, 7)
        resultados = comparar_todas(seg, der)

        for r in resultados:
            assert "Lei 8.213/91 Art. 48" not in r.nome_regra, (
                f"Regra pre-reforma de idade encontrada para DER pos-reforma: {r.nome_regra}"
            )

    def test_der_2026_contem_ec103(self):
        seg = _criar_segurado(
            "REGRESSAO POS REFORMA EC103", date(1960, 1, 1), Sexo.MASCULINO,
            date(1990, 1, 1), date(2026, 4, 1),
        )
        der = date(2026, 4, 7)
        resultados = comparar_todas(seg, der)

        nomes = [r.nome_regra for r in resultados]
        assert any("EC 103" in n for n in nomes), (
            f"Nenhuma regra EC 103 para DER pos-reforma ({der}). Nomes: {nomes}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 3: Direito Adquirido deve comparar AMBOS os regimes de SB
# Bug: calculava SB apenas com regime EC 103, ignorando 80% maiores
# ═════════════════════════════════════════════════════════════════════════════
class TestDireitoAdquiridoAmbosRegimes:
    """
    RegraDireitoAdquirido deve calcular com regime pre-reforma (80% maiores)
    E com regime EC 103 (100%), escolhendo o melhor (STF Tema 334).
    """

    def test_memoria_contem_ambos_regimes(self):
        # 36 anos de TC (completou antes da EC 103)
        seg = _criar_segurado(
            "DIREITO ADQUIRIDO", date(1960, 1, 1), Sexo.MASCULINO,
            date(1983, 1, 1), date(2019, 11, 12),  # TC completo ANTES da EC 103
            salario=Decimal("4000"),
        )
        # Adicionar contribuicoes apos a EC 103 tambem (simulando que continua)
        contribs_pos = _criar_contribuicoes(date(2019, 12, 1), date(2026, 3, 1), Decimal("4000"))
        v_pos = Vinculo(
            tipo_vinculo=TipoVinculo.EMPREGADO,
            regime=RegimePrevidenciario.RGPS,
            tipo_atividade=TipoAtividade.NORMAL,
            data_inicio=date(2019, 12, 1),
            data_fim=date(2026, 3, 31),
            contribuicoes=contribs_pos,
            origem=OrigemDado.MANUAL,
        )
        seg.vinculos.append(v_pos)

        der = date(2026, 4, 1)
        regra = RegraDireitoAdquirido()
        resultado = regra.calcular(seg, der)

        # Deve ser elegivel (36+ anos TC antes da EC 103)
        assert resultado.elegivel, "Direito adquirido deveria ser elegivel com 36+ anos TC"

        # A memoria deve mencionar AMBOS os regimes
        textos_memoria = [item.descricao for item in resultado.memoria.itens]
        texto_completo = " ".join(textos_memoria)

        assert "pre-reforma" in texto_completo.lower() or "80%" in texto_completo, (
            f"Memoria nao menciona regime pre-reforma (80% maiores). "
            f"Textos: {textos_memoria}"
        )
        assert "EC 103" in texto_completo or "100%" in texto_completo, (
            f"Memoria nao menciona regime EC 103 (100%). "
            f"Textos: {textos_memoria}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 4: Qualidade de segurado com beneficio ativo = ATIVA
# Bug: ignorava beneficio ativo e marcava PERDIDA por contribuicao antiga
# ═════════════════════════════════════════════════════════════════════════════
class TestQualidadeSeguradoBeneficioAtivo:
    """
    Se o segurado tem beneficio ativo (DIB definida, sem DCB),
    a qualidade de segurado e ATIVA independentemente da ultima contribuicao.
    """

    def test_qualidade_ativa_com_beneficio_sem_dcb(self):
        from app.domain.planejamento.projecao import _analisar_qualidade_segurado

        # Ultima contribuicao em 2016 (muito antiga)
        seg = _criar_segurado(
            "QUALIDADE BENEFICIO ATIVO", date(1960, 1, 1), Sexo.MASCULINO,
            date(1990, 1, 1), date(2016, 12, 1),
        )
        # Beneficio ativo (DIB definida, sem DCB = em curso)
        seg.beneficios_anteriores = [
            BeneficioAnterior(
                numero_beneficio="1234567890",
                especie=TipoBeneficio.APOSENTADORIA_IDADE,
                dib=date(2017, 1, 1),
                dcb=None,  # ← ATIVO (sem cessacao)
                rmi=Decimal("2500"),
            )
        ]

        der = date(2026, 4, 7)
        qualidade = _analisar_qualidade_segurado(seg, der)

        assert qualidade["status"] == "APOSENTADO", (
            f"Qualidade deveria ser APOSENTADO com beneficio ativo, mas foi: {qualidade['status']}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 5: Qualidade de segurado sem beneficio e contribuicao antiga = PERDIDA
# Bug: marcava ATIVA quando nao deveria (falso positivo)
# ═════════════════════════════════════════════════════════════════════════════
class TestQualidadeSeguradoPerdida:
    """
    Sem beneficio ativo e com ultima contribuicao em 2016,
    a qualidade em 2026 deve ser PERDIDA (periodo de graca esgotado ha anos).
    """

    def test_qualidade_perdida_sem_beneficio(self):
        from app.domain.planejamento.projecao import _analisar_qualidade_segurado

        seg = _criar_segurado(
            "QUALIDADE PERDIDA", date(1960, 1, 1), Sexo.MASCULINO,
            date(1990, 1, 1), date(2016, 12, 1),
        )
        # SEM beneficios anteriores
        seg.beneficios_anteriores = []

        der = date(2026, 4, 7)
        qualidade = _analisar_qualidade_segurado(seg, der)

        assert qualidade["status"] == "PERDIDA", (
            f"Qualidade deveria ser PERDIDA sem beneficio e contrib antiga, "
            f"mas foi: {qualidade['status']}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 6: Score deve cair quando ha alertas FATAIS
# Bug: score alto (930) mesmo com impossibilidade temporal
# ═════════════════════════════════════════════════════════════════════════════
class TestScoreComAlertasFatais:
    """
    Se existem alertas FATAIS (ex: impossibilidade temporal), o validador
    deve gerar alerta SCORE_001 indicando que o score nao reflete a realidade.
    """

    def test_score_alto_com_fatal_gera_alerta(self):
        validador = ValidadorAntiAlucinacao()

        resultado_fake = {
            "projecoes": [
                {
                    "regra": "Transicao — Pontos (Art. 15 EC 103/2019)",
                    "data_elegibilidade": date(2017, 3, 1),  # Antes da EC 103!
                    "rmi_projetada": 3500,
                    "salario_beneficio": 4000,
                }
            ],
            "qualidade_segurado": {},
            "custo_beneficio": [],
            "score_prontidao": {"score": 930},  # Score alto
        }

        der = date(2026, 4, 7)
        alertas = validador.validar_tudo(resultado_fake, der)

        # Deve ter alertas FATAIS (por impossibilidade temporal)
        fatais = [a for a in alertas if a.gravidade == "FATAL"]
        assert len(fatais) > 0, "Deveria haver alertas FATAIS para regra EC 103 com data 2017"

        # Deve haver alerta de score inconsistente (SCORE_001)
        codigos = [a.codigo for a in alertas]
        assert "SCORE_001" in codigos, (
            f"Alerta SCORE_001 nao gerado com score 930 e alertas FATAIS. Codigos: {codigos}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 7: Regra 85/95 calcula corretamente para DER em 2017
# Bug: calculo errado dos pontos, dava elegivel quando nao deveria
# ═════════════════════════════════════════════════════════════════════════════
class TestRegra8595:
    """
    Para DER em 2017, a regra 85/95 exige 95 pontos (homem).
    Homem nascido em 1960 com 35 anos TC: 57 + 35 = 92 < 95 → NAO elegivel.
    Homem nascido em 1955 com 35 anos TC: 62 + 35 = 97 >= 95 → ELEGIVEL.
    """

    def test_8595_nao_elegivel_pontos_insuficientes(self):
        # Homem nascido 1960, 35 anos TC na DER 02/06/2017
        # Idade em 02/06/2017: 57 anos → 57 + 35 = 92 < 95
        seg = _criar_segurado(
            "85/95 INSUFICIENTE", date(1960, 6, 15), Sexo.MASCULINO,
            date(1982, 6, 1), date(2017, 5, 31),
        )
        der = date(2017, 6, 2)
        regra = Regra85_95()
        resultado = regra.calcular(seg, der)

        assert not resultado.elegivel, (
            "Homem 57 anos + 35 TC = 92 pontos nao deveria ser elegivel (exigido: 95)"
        )

    def test_8595_elegivel_pontos_suficientes(self):
        # Homem nascido 1955, 35 anos TC na DER 02/06/2017
        # Idade em 02/06/2017: 62 anos → 62 + 35 = 97 >= 95
        seg = _criar_segurado(
            "85/95 SUFICIENTE", date(1955, 1, 15), Sexo.MASCULINO,
            date(1982, 1, 1), date(2017, 5, 31),
        )
        der = date(2017, 6, 2)
        regra = Regra85_95()
        resultado = regra.calcular(seg, der)

        assert resultado.elegivel, (
            "Homem 62 anos + 35 TC = 97 pontos deveria ser elegivel (exigido: 95)"
        )
        # RMI = 100% SB (sem FP) — verificar que nao aplicou fator
        assert resultado.fator_previdenciario is None or resultado.coeficiente == Decimal("1.0"), (
            "Regra 85/95 deve afastar FP: RMI = 100% do SB"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 8: ROI disclaimer sempre presente
# Bug: custo_beneficio era apresentado sem disclaimer, sugerindo garantia
# ═════════════════════════════════════════════════════════════════════════════
class TestROIDisclaimer:
    """
    Toda entrada em custo_beneficio deve ter campo 'disclaimer'
    contendo 'NAO constitui analise atuarial'.
    """

    def test_disclaimer_presente_no_custo_beneficio(self):
        from app.domain.planejamento.projecao import calcular_planejamento

        seg = _criar_segurado(
            "DISCLAIMER TEST", date(1965, 1, 1), Sexo.MASCULINO,
            date(1990, 1, 1), date(2026, 3, 1),
            salario=Decimal("4000"),
        )
        resultado = calcular_planejamento(seg, date(2026, 4, 7))

        custo_beneficio = resultado.get("custo_beneficio", [])
        # Se existem entradas de custo-beneficio, TODAS devem ter disclaimer
        for entry in custo_beneficio:
            assert "disclaimer" in entry, (
                f"Entrada de custo_beneficio sem campo 'disclaimer': {list(entry.keys())}"
            )
            assert "NAO constitui analise atuarial" in entry["disclaimer"], (
                f"Disclaimer nao contem texto obrigatorio. Texto: {entry['disclaimer']}"
            )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 9: Validador antialucinacao detecta impossibilidade temporal
# Bug: resultado com EC 103 elegivel em 2017 passava sem alerta
# ═════════════════════════════════════════════════════════════════════════════
class TestAntiAlucinacaoTemporal:
    """
    Se uma regra EC 103 tem data_elegibilidade antes de 13/11/2019,
    o validador deve gerar alerta TEMPORAL_001 com gravidade FATAL.
    """

    def test_temporal_001_detectado(self):
        validador = ValidadorAntiAlucinacao()

        resultado_fake = {
            "projecoes": [
                {
                    "regra": "Transicao — Pontos (Art. 15 EC 103/2019)",
                    "data_elegibilidade": date(2017, 6, 1),  # IMPOSSIVEL!
                    "rmi_projetada": 3000,
                    "salario_beneficio": 3500,
                }
            ],
            "qualidade_segurado": {},
            "custo_beneficio": [],
            "score_prontidao": {"score": 500},
        }

        der = date(2026, 4, 7)
        alertas = validador.validar_tudo(resultado_fake, der)

        temporal = [a for a in alertas if a.codigo == "TEMPORAL_001"]
        assert len(temporal) > 0, (
            "Validador nao detectou impossibilidade temporal (TEMPORAL_001) "
            "para regra EC 103 com data 2017"
        )
        assert temporal[0].gravidade == "FATAL", (
            f"Alerta TEMPORAL_001 deveria ser FATAL, mas foi: {temporal[0].gravidade}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# TESTE 10: Campo regime_aplicado correto conforme DER
# Bug: campo regime_aplicado retornava POS_REFORMA para DER pre-reforma
# ═════════════════════════════════════════════════════════════════════════════
class TestRegimeAplicado:
    """
    DER < 13/11/2019 → regime_aplicado == 'PRE_REFORMA'
    DER >= 13/11/2019 → regime_aplicado == 'POS_REFORMA_EC103'
    """

    def test_regime_pre_reforma(self):
        from app.domain.planejamento.projecao import calcular_planejamento

        seg = _criar_segurado(
            "REGIME PRE", date(1960, 1, 1), Sexo.MASCULINO,
            date(1982, 1, 1), date(2017, 5, 31),
            salario=Decimal("3000"),
        )
        resultado = calcular_planejamento(seg, date(2017, 6, 2))

        assert resultado["regime_aplicado"] == "PRE_REFORMA", (
            f"DER 2017 deveria ser PRE_REFORMA, mas foi: {resultado['regime_aplicado']}"
        )

    def test_regime_pos_reforma(self):
        from app.domain.planejamento.projecao import calcular_planejamento

        seg = _criar_segurado(
            "REGIME POS", date(1965, 1, 1), Sexo.MASCULINO,
            date(1990, 1, 1), date(2026, 3, 1),
            salario=Decimal("4000"),
        )
        resultado = calcular_planejamento(seg, date(2026, 4, 7))

        assert resultado["regime_aplicado"] == "POS_REFORMA_EC103", (
            f"DER 2026 deveria ser POS_REFORMA_EC103, mas foi: {resultado['regime_aplicado']}"
        )
