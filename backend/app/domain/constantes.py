"""
Constantes legais e datas de corte do sistema previdenciário.
REGRA: Nunca usar literals de data espalhados no código.
       Sempre referenciar estas constantes nomeadas.
"""
from datetime import date
from decimal import Decimal


# ─────────────────────────────────────────────────────────────────────────────
# DATAS DE CORTE LEGISLATIVAS
# ─────────────────────────────────────────────────────────────────────────────
class DatasCorte:
    # Lei 8.213/91 — Lei de Benefícios
    LEI_8213_91 = date(1991, 7, 24)

    # Lei 9.876/99 — Fator Previdenciário + regra dos 80% maiores
    LEI_9876_99 = date(1999, 11, 29)

    # EC 20/98 — Primeira elevação do teto (R$ 1.200,00)
    EC_20_98 = date(1998, 12, 16)
    EC_20_VIGENCIA_TETO = date(1998, 12, 16)

    # EC 41/03 — Segunda elevação do teto (R$ 2.400,00)
    EC_41_03 = date(2003, 12, 31)
    EC_41_VIGENCIA_TETO = date(2004, 1, 1)

    # EC 103/2019 — Reforma da Previdência
    EC_103_2019 = date(2019, 11, 13)

    # Plano Real — marco zero do PBC universal
    PLANO_REAL = date(1994, 7, 1)

    # EC 113/2021 — SELIC como índice de correção judicial
    EC_113_2021 = date(2021, 12, 30)

    # Lei 14.905/2024 — Nova metodologia de correção e juros
    LEI_14905_2024 = date(2024, 7, 24)

    # Limite mínimo de contribuições para cômputo (Decreto 10.410/2020 - Art. 19-E)
    DECRETO_10410_2020 = date(2020, 7, 2)


# ─────────────────────────────────────────────────────────────────────────────
# REGRAS DE TRANSIÇÃO EC 103/2019 — PONTUAÇÃO PROGRESSIVA
# ─────────────────────────────────────────────────────────────────────────────
# Art. 16 da EC 103/2019 — Sistema de Pontos
# Pontos = Idade + Tempo de Contribuição
PONTOS_EC103 = {
    # ano: (homem, mulher)
    2019: (96, 86),
    2020: (97, 87),
    2021: (98, 88),
    2022: (99, 89),
    2023: (100, 90),
    2024: (101, 91),
    2025: (102, 92),
    2026: (103, 93),
    2027: (104, 94),
    2028: (105, 95),
    2029: (105, 96),
    2030: (105, 97),
    2031: (105, 98),
    2032: (105, 99),
    2033: (105, 100),
}
# A partir de 2033, teto fixo
PONTOS_EC103_TETO_HOMEM = Decimal("105")
PONTOS_EC103_TETO_MULHER = Decimal("100")

# Art. 17 — Idade mínima progressiva (aposentadoria por idade com TC mínimo)
IDADE_PROG_EC103 = {
    # ano: (homem_anos, mulher_anos) — em anos inteiros; interpolar para meses
    2020: (61, 56),
    2021: (62, 57),
    2022: (63, 58),
    2023: (64, 59),
    2024: (65, 60),
    2025: (65, 61),
    2026: (65, 62),
}
# A partir de 2027 (H) e 2031 (M), idades definitivas
IDADE_DEFINITIVA_HOMEM = Decimal("65")
IDADE_DEFINITIVA_MULHER = Decimal("62")

# Art. 19-E EC 103 — Tempo mínimo de contribuição (regra permanente)
TC_MINIMO_HOMEM_ANOS = Decimal("20")    # 20 anos = 240 meses
TC_MINIMO_MULHER_ANOS = Decimal("15")   # 15 anos = 180 meses

# TC mínimo para a regra antiga (pré EC 103)
TC_MINIMO_HOMEM_PRE_EC103 = Decimal("35")
TC_MINIMO_MULHER_PRE_EC103 = Decimal("30")


# ─────────────────────────────────────────────────────────────────────────────
# CARÊNCIA (em competências/meses)
# ─────────────────────────────────────────────────────────────────────────────
class Carencia:
    APOSENTADORIA = 180             # Lei 8.213/91 Art. 25 II
    AUXILIO_DOENCA = 12             # Lei 8.213/91 Art. 25 I
    APOSENTADORIA_INVALIDEZ = 12    # Lei 8.213/91 Art. 25 I
    SALARIO_MATERNIDADE_CI = 10     # Lei 8.213/91 Art. 25 III (CI/facultativa)
    SALARIO_MATERNIDADE_EMPREGADA = 0  # Empregada CLT — sem carência
    PENSAO_MORTE = 0                # Lei 8.213/91 Art. 26 I — sem carência
    AUXILIO_RECLUSAO = 0
    BPC_LOAS = 0
    # Sem carência: acidente de qualquer natureza ou doença do Art. 151
    SEM_CARENCIA = 0


# ─────────────────────────────────────────────────────────────────────────────
# PERÍODO DE GRAÇA (em meses após perda do emprego/recolhimento)
# ─────────────────────────────────────────────────────────────────────────────
class PeriodoGraca:
    EMPREGADO_BASE = 12             # Lei 8.213/91 Art. 15 II
    EMPREGADO_EXTENSAO = 24         # Quando ≥ 120 contribuições sem interrupção
    EMPREGADO_DESEMPREGADO = 36     # Desemprego involuntário comprovado (com ≥ 120 contrib.)
    CI_FACULTATIVO = 6              # Lei 8.213/91 Art. 15 V
    AVULSO = 12                     # Lei 8.213/91 Art. 15 III


# ─────────────────────────────────────────────────────────────────────────────
# COEFICIENTE RMI — EC 103/2019 Art. 26
# ─────────────────────────────────────────────────────────────────────────────
COEFICIENTE_BASE = Decimal("0.60")          # 60% do salário de benefício
COEFICIENTE_INCREMENTO = Decimal("0.02")    # +2% por ano excedente ao mínimo

# Limite máximo do coeficiente
COEFICIENTE_MAXIMO = Decimal("1.00")        # 100%

# Limiar de anos de contribuição para o coeficiente (regra permanente EC 103)
COEFICIENTE_LIMIAR_HOMEM = Decimal("20")    # acima de 20 anos, +2%/ano
COEFICIENTE_LIMIAR_MULHER = Decimal("15")   # acima de 15 anos, +2%/ano

# Coeficiente aposentadoria por invalidez previdenciária
COEFICIENTE_INVALIDEZ_PREV = Decimal("0.60")  # aplica-se o coeficiente normal
# Coeficiente aposentadoria por invalidez acidentária
COEFICIENTE_INVALIDEZ_ACID = Decimal("1.00")  # 100% do SB
# Acréscimo de 25% por necessidade de assistência permanente (Art. 45)
ACRESCIMO_GRANDE_INVALIDO = Decimal("0.25")


# ─────────────────────────────────────────────────────────────────────────────
# FATORES DE CONVERSÃO TEMPO ESPECIAL → COMUM
# ─────────────────────────────────────────────────────────────────────────────
# Decreto 3.048/99 Art. 70 — Tabela de conversão
# fator = TC_normal_exigido / TC_especial_exigido
from decimal import Decimal as D

FATORES_CONVERSAO = {
    # (tipo_especial, sexo): fator
    # Especial 15 anos → 35 anos comuns (H) = 35/15 = 7/3
    ("ESPECIAL_15", "M"): D("7") / D("3"),   # ≈ 2.333...
    # Especial 15 anos → 30 anos comuns (F) = 30/15 = 2
    ("ESPECIAL_15", "F"): D("2"),
    # Especial 20 anos → 35 anos comuns (H) = 35/20 = 7/4
    ("ESPECIAL_20", "M"): D("7") / D("4"),   # = 1.75
    # Especial 20 anos → 30 anos comuns (F) = 30/20 = 3/2
    ("ESPECIAL_20", "F"): D("3") / D("2"),   # = 1.5
    # Especial 25 anos → 35 anos comuns (H) = 35/25 = 7/5
    ("ESPECIAL_25", "M"): D("7") / D("5"),   # = 1.4
    # Especial 25 anos → 30 anos comuns (F) = 30/25 = 6/5
    ("ESPECIAL_25", "F"): D("6") / D("5"),   # = 1.2
}

# Data limite para conversão de tempo especial em comum
# EC 103/2019 (Art. 25, §2º) proibiu a conversão para períodos APÓS 13/11/2019.
# O STJ (Tema 422, REsp 1.310.034) pacificou que a conversão é possível
# para QUALQUER período especial trabalhado ANTES de 13/11/2019,
# independentemente de quando o requerimento foi feito.
DATA_LIMITE_CONVERSAO_ESPECIAL = date(2019, 11, 13)  # EC 103/2019


# ─────────────────────────────────────────────────────────────────────────────
# PENSÃO POR MORTE — EC 103/2019
# ─────────────────────────────────────────────────────────────────────────────
PENSAO_COTA_FAMILIAR = Decimal("0.50")       # 50% base
PENSAO_COTA_DEPENDENTE = Decimal("0.10")     # +10% por dependente
PENSAO_MAXIMO = Decimal("1.00")              # teto de 100%

# Prazo mínimo de casamento/união para dependente cônjuge (Art. 23 §1º EC 103)
PENSAO_PRAZO_MINIMO_CASAMENTO_MESES = 18

# Duração variável da pensão por idade do cônjuge (Art. 23 §2º EC 103)
PENSAO_DURACAO_MENOS_21 = 3          # anos
PENSAO_DURACAO_21_26 = 6
PENSAO_DURACAO_27_29 = 10
PENSAO_DURACAO_30_40 = 15
PENSAO_DURACAO_41_43 = 20
PENSAO_DURACAO_44_MAIS = 9999        # vitalícia (representado como 9999)


# ─────────────────────────────────────────────────────────────────────────────
# TETO DO RGPS (valores fixos, tabela dinâmica em indices/teto_previdenciario.py)
# ─────────────────────────────────────────────────────────────────────────────
# Teto no momento da EC 20/98 (dez/1998)
TETO_EC20_98 = D("1200.00")
# Teto no momento da EC 41/03 (jan/2004)
TETO_EC41_03 = D("2400.00")


# ─────────────────────────────────────────────────────────────────────────────
# ALÍQUOTA DE CONTRIBUIÇÃO — FÓRMULA DO FATOR PREVIDENCIÁRIO
# ─────────────────────────────────────────────────────────────────────────────
# Constante atuarial "a" usada na fórmula do FP (Lei 9.876/99 Art. 29-B)
ALIQUOTA_ATUARIAL = D("0.31")


# ─────────────────────────────────────────────────────────────────────────────
# DIVISOR MÍNIMO — Lei 9.876/99 Art. 29 §§ 5 e 6
# ─────────────────────────────────────────────────────────────────────────────
DIVISOR_MINIMO_PERCENTUAL = D("0.60")  # 60% do total de meses no PBC


# ─────────────────────────────────────────────────────────────────────────────
# BPC/LOAS
# ─────────────────────────────────────────────────────────────────────────────
BPC_RENDA_PER_CAPITA_MAXIMA_FRACAO = D("0.25")  # 1/4 do salário mínimo
BPC_IDADE_MINIMA = 65
