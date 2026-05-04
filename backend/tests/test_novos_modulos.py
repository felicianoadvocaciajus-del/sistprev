"""
Testes de Regressão — Módulos Novos (Fase 2/3 da Reestruturação).

Cobre:
  1. Acordo Internacional (totalização, pro-rata)
  2. Retroativos (correção monetária, juros, prescrição)
  3. Classificação FATO/PROJEÇÃO/TESE
  4. Classificação de Evidências Especiais (5 níveis)
  5. Motor de Roteamento (REVISÃO vs NOVO_BENEFÍCIO)
"""
import pytest
from datetime import date
from decimal import Decimal


# ═══════════════════════════════════════════════════════════════════════════════
# ACORDO INTERNACIONAL
# ═══════════════════════════════════════════════════════════════════════════════

class TestAcordoInternacional:
    def test_verificar_acordo_espanha(self):
        from app.domain.acordo_internacional import verificar_acordo
        acordo = verificar_acordo("Espanha")
        assert acordo is not None
        assert "1.689" in acordo.decreto or "1689" in acordo.decreto
        assert acordo.permite_totalizacao is True

    def test_verificar_acordo_portugal(self):
        from app.domain.acordo_internacional import verificar_acordo
        acordo = verificar_acordo("Portugal")
        assert acordo is not None
        assert acordo.permite_totalizacao is True

    def test_verificar_acordo_inexistente(self):
        from app.domain.acordo_internacional import verificar_acordo
        acordo = verificar_acordo("Marte")
        assert acordo is None

    def test_documentos_necessarios_espanha(self):
        from app.domain.acordo_internacional import documentos_necessarios
        docs = documentos_necessarios("Espanha")
        assert isinstance(docs, list)
        assert len(docs) > 0

    def test_listar_acordos(self):
        from app.domain.acordo_internacional import listar_acordos
        acordos = listar_acordos()
        assert isinstance(acordos, dict)
        assert len(acordos) >= 7  # pelo menos 7 acordos

    def test_totalizacao_basica(self):
        from app.domain.acordo_internacional import (
            calcular_totalizacao, PeriodoExterior
        )
        from app.domain.models.segurado import Segurado, DadosPessoais
        from app.domain.models.vinculo import Vinculo
        from app.domain.models.contribuicao import Contribuicao
        from app.domain.enums import Sexo, TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado

        # Criar segurado com vínculos no Brasil
        contribs = []
        for ano in range(2010, 2026):
            for m in range(1, 13):
                contribs.append(Contribuicao(
                    competencia=date(ano, m, 1),
                    salario_contribuicao=Decimal("3000"),
                ))

        vinculo = Vinculo(
            tipo_vinculo=TipoVinculo.EMPREGADO,
            regime=RegimePrevidenciario.RGPS,
            tipo_atividade=TipoAtividade.NORMAL,
            empregador_nome="EMPRESA BR",
            data_inicio=date(2010, 1, 1),
            contribuicoes=contribs,
            origem=OrigemDado.CNIS,
        )

        dados = DadosPessoais(
            nome="TESTE ACORDO",
            data_nascimento=date(1965, 1, 1),
            sexo=Sexo.MASCULINO,
        )

        segurado = Segurado(dados_pessoais=dados, vinculos=[vinculo])

        periodos = [
            PeriodoExterior(
                pais="Espanha",
                data_inicio=date(2000, 1, 1),
                data_fim=date(2010, 12, 31),
                dias_contribuicao=4018,
                orgao_previdenciario="INSS España",
                comprovante="Formulário ESP-BRA/3",
            )
        ]

        resultado = calcular_totalizacao(segurado, date(2026, 4, 7), periodos)
        assert resultado.tc_exterior_dias == 4018
        assert resultado.tc_total_dias > resultado.tc_brasil_dias
        assert resultado.pro_rata > Decimal("0")
        assert resultado.pro_rata <= Decimal("1")


# ═══════════════════════════════════════════════════════════════════════════════
# RETROATIVOS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetroativos:
    def test_calculo_basico_retroativos(self):
        from app.domain.retroativos import calcular_retroativos
        resultado = calcular_retroativos(
            rmi_corrigida=Decimal("2000.00"),
            rmi_original=Decimal("1500.00"),
            dib=date(2023, 1, 1),
            dip=date(2023, 6, 1),
            data_calculo=date(2026, 4, 7),
        )
        assert resultado.diferenca_mensal == Decimal("500.00")
        assert resultado.total_bruto > Decimal("0")
        assert resultado.total_liquido > Decimal("0")
        assert len(resultado.parcelas) > 0

    def test_prescricao_quinquenal(self):
        from app.domain.retroativos import calcular_retroativos
        resultado = calcular_retroativos(
            rmi_corrigida=Decimal("2000.00"),
            rmi_original=Decimal("1500.00"),
            dib=date(2015, 1, 1),
            dip=date(2015, 6, 1),
            data_calculo=date(2026, 4, 7),
            data_ajuizamento=date(2026, 1, 1),
        )
        # Deve haver parcelas prescritas (antes de 5 anos do ajuizamento)
        prescritas = [p for p in resultado.parcelas if p.prescrita]
        assert len(prescritas) > 0, "Deve haver parcelas prescritas"
        # O valor prescrito deve ser positivo
        assert resultado.valor_prescrito > Decimal("0") or resultado.parcelas_prescritas > 0

    def test_correcao_monetaria_positiva(self):
        from app.domain.retroativos import calcular_correcao_monetaria
        valor_corrigido, indice = calcular_correcao_monetaria(
            Decimal("1000.00"), date(2020, 1, 1), date(2026, 4, 1)
        )
        assert valor_corrigido > Decimal("1000.00"), "Valor corrigido deve ser maior que o original"
        assert indice > Decimal("1"), "Índice deve ser > 1"

    def test_juros_mora(self):
        from app.domain.retroativos import calcular_juros_mora
        valor_juros, taxa = calcular_juros_mora(
            Decimal("1000.00"), date(2022, 1, 1), date(2026, 4, 1)
        )
        assert valor_juros > Decimal("0"), "Juros deve ser positivo"

    def test_beneficio_negado_rmi_original_zero(self):
        from app.domain.retroativos import calcular_retroativos
        resultado = calcular_retroativos(
            rmi_corrigida=Decimal("1500.00"),
            rmi_original=Decimal("0"),
            dib=date(2024, 1, 1),
            dip=None,
            data_calculo=date(2026, 4, 7),
        )
        assert resultado.diferenca_mensal == Decimal("1500.00")
        assert resultado.total_bruto > Decimal("0")

    def test_disclaimer_presente(self):
        from app.domain.retroativos import calcular_retroativos
        resultado = calcular_retroativos(
            rmi_corrigida=Decimal("2000.00"),
            rmi_original=Decimal("1500.00"),
            dib=date(2024, 1, 1),
            dip=date(2024, 6, 1),
            data_calculo=date(2026, 4, 7),
        )
        assert resultado.disclaimer, "Resultado deve conter disclaimer"


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFICAÇÃO FATO/PROJEÇÃO/TESE
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassificacaoDados:
    def _criar_segurado_basico(self):
        from app.domain.models.segurado import Segurado, DadosPessoais
        from app.domain.models.vinculo import Vinculo
        from app.domain.models.contribuicao import Contribuicao
        from app.domain.enums import Sexo, TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado

        contribs = []
        for ano in range(2010, 2026):
            for m in range(1, 13):
                contribs.append(Contribuicao(
                    competencia=date(ano, m, 1),
                    salario_contribuicao=Decimal("3000"),
                ))

        vinculo = Vinculo(
            tipo_vinculo=TipoVinculo.EMPREGADO,
            regime=RegimePrevidenciario.RGPS,
            tipo_atividade=TipoAtividade.NORMAL,
            empregador_nome="EMPRESA TEST",
            data_inicio=date(2010, 1, 1),
            contribuicoes=contribs,
            origem=OrigemDado.CNIS,
        )

        dados = DadosPessoais(
            nome="TESTE CLASSIFICACAO",
            data_nascimento=date(1970, 5, 15),
            sexo=Sexo.MASCULINO,
        )

        return Segurado(dados_pessoais=dados, vinculos=[vinculo])

    def test_classificacao_presente_no_planejamento(self):
        from app.domain.planejamento.projecao import calcular_planejamento
        segurado = self._criar_segurado_basico()
        resultado = calcular_planejamento(segurado, date(2026, 4, 7))
        assert "classificacao_dados" in resultado
        cd = resultado["classificacao_dados"]
        assert "fatos" in cd
        assert "projecoes" in cd
        assert "teses" in cd
        assert "disclaimer_geral" in cd

    def test_fatos_tem_tc_carencia_idade(self):
        from app.domain.planejamento.projecao import calcular_planejamento
        segurado = self._criar_segurado_basico()
        resultado = calcular_planejamento(segurado, date(2026, 4, 7))
        cd = resultado["classificacao_dados"]
        descricoes_fatos = [f["descricao"] for f in cd["fatos"]]
        assert any("Tempo de Contribuição" in d for d in descricoes_fatos)
        assert any("Carência" in d for d in descricoes_fatos)
        assert any("Idade" in d for d in descricoes_fatos)

    def test_projecoes_tem_disclaimer(self):
        from app.domain.planejamento.projecao import calcular_planejamento
        segurado = self._criar_segurado_basico()
        resultado = calcular_planejamento(segurado, date(2026, 4, 7))
        cd = resultado["classificacao_dados"]
        for p in cd["projecoes"]:
            assert p.get("disclaimer"), f"Projeção '{p['descricao']}' sem disclaimer"
            assert p.get("confianca") in ("ALTA", "MEDIA", "BAIXA")

    def test_cada_item_tem_confianca(self):
        from app.domain.planejamento.projecao import calcular_planejamento
        segurado = self._criar_segurado_basico()
        resultado = calcular_planejamento(segurado, date(2026, 4, 7))
        cd = resultado["classificacao_dados"]
        for categoria in ["fatos", "projecoes", "teses"]:
            for item in cd[categoria]:
                assert item.get("confianca") in ("ALTA", "MEDIA", "BAIXA"), \
                    f"Item '{item['descricao']}' em {categoria} sem confiança válida"


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFICAÇÃO DE EVIDÊNCIAS ESPECIAIS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvidenciasEspeciais:
    def test_ppp_ltcat_nivel_forte(self):
        from app.domain.especial.classificacao_evidencias import classificar_evidencias
        resultado = classificar_evidencias(
            analise_empregador={"encontrado": True, "probabilidade": "ALTA"},
            analise_cargo={"encontrado": True, "probabilidade": "ALTA"},
            analise_cbo=None,
            jurisprudencias=[],
            tem_ppp=True,
            ppp_confirma_agente=True,
            ppp_empresa_match=True,
            ppp_periodo_match=True,
            tem_ltcat=True,
            ltcat_confirma_exposicao=True,
        )
        assert resultado.tier_label == "PROVA_FORTE"
        assert resultado.pode_reconhecer_automatico is True

    def test_nome_empresa_sozinho_nao_e_forte(self):
        from app.domain.especial.classificacao_evidencias import classificar_evidencias
        resultado = classificar_evidencias(
            analise_empregador={"encontrado": True, "probabilidade": "MEDIA"},
            analise_cargo={"encontrado": False, "probabilidade": "NENHUMA"},
            analise_cbo=None,
            jurisprudencias=[],
            tem_ppp=False,
            empregador_nome="METALURGICA SAO JOSE",
        )
        assert resultado.tier_label != "PROVA_FORTE"
        assert resultado.pode_reconhecer_automatico is False

    def test_sem_nada_nivel_sem_lastro(self):
        from app.domain.especial.classificacao_evidencias import classificar_evidencias
        resultado = classificar_evidencias(
            analise_empregador={"encontrado": False, "probabilidade": "NENHUMA"},
            analise_cargo={"encontrado": False, "probabilidade": "NENHUMA"},
            analise_cbo=None,
            jurisprudencias=[],
            tem_ppp=False,
            tem_ltcat=False,
        )
        assert resultado.tier_label == "SEM_LASTRO"
        assert resultado.pode_reconhecer_automatico is False


# ═══════════════════════════════════════════════════════════════════════════════
# MOTOR DE ROTEAMENTO
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoteamento:
    def test_sem_dados_nao_e_revisao(self):
        from app.domain.roteamento.motor_roteamento import rotear_caso
        resultado = rotear_caso(
            segurado_data={"dados_pessoais": {"nome": "TESTE"}, "vinculos": []},
            beneficios=[],
        )
        # Sem benefícios, nunca deve ser REVISAO
        assert resultado["modo_recomendado"] != "REVISAO"

    def test_revisao_com_beneficio_ativo(self):
        from app.domain.roteamento.motor_roteamento import rotear_caso
        resultado = rotear_caso(
            segurado_data={"dados_pessoais": {"nome": "TESTE"}, "vinculos": []},
            beneficios=[{"especie": "B42", "nb": "123", "dib": "01/01/2020", "dcb": None, "situacao": "ATIVA"}],
            carta_concessao={"dib": "01/01/2020", "nb": "123"},
        )
        assert resultado["modo_recomendado"] == "REVISAO"

    def test_revisao_detecta_beneficio_ativo(self):
        from app.domain.roteamento.motor_roteamento import rotear_caso
        resultado = rotear_caso(
            segurado_data={"dados_pessoais": {"nome": "TESTE"}, "vinculos": []},
            beneficios=[{"especie": "B42", "nb": "456", "dib": "01/06/2021", "dcb": None, "situacao": "ATIVA"}],
        )
        # beneficio_ativo pode ser bool or dict — just check it's truthy
        assert resultado["beneficio_ativo"]
