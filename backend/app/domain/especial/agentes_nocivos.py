"""
Modulo de Atividade Especial - Direito Previdenciario Brasileiro

Mapeamento de atividades especiais (insalubridade, periculosidade, penosidade)
conforme legislacao previdenciaria brasileira.

Fundamentacao Legal:
- Decreto 53.831/1964 - Quadro Anexo (vigente ate 05/03/1997)
- Decreto 83.080/1979 - Anexos I e II (vigente ate 05/03/1997)
- Decreto 2.172/1997 - Anexo IV (vigente de 06/03/1997 a 06/05/1999)
- Decreto 3.048/1999 - Anexo IV (vigente a partir de 07/05/1999)
- Lei 8.213/1991, art. 57 e 58
- IN INSS/PRES 77/2015 e IN INSS/PRES 128/2022

Conversao de tempo especial para comum:
- Atividade especial de 25 anos: fator 1.4 (homem) / 1.2 (mulher)
- Atividade especial de 20 anos: fator 1.5 (homem) / 1.33 (mulher) [mineracao subsolo]
- Atividade especial de 15 anos: fator 2.33 (homem) / 2.0 (mulher) [amianto, mineracao subsolo]

Importante: Ate 28/04/1995 (Lei 9.032/95), o enquadramento podia ser feito
por categoria profissional. Apos essa data, exige-se comprovacao de exposicao
efetiva a agentes nocivos (PPP, LTCAT).
"""

import re
from typing import Optional

# =============================================================================
# FATORES DE CONVERSAO DE TEMPO ESPECIAL PARA COMUM
# =============================================================================

FATORES_CONVERSAO = {
    25: {"masculino": 1.40, "feminino": 1.20},
    20: {"masculino": 1.50, "feminino": 1.33},
    15: {"masculino": 2.33, "feminino": 2.00},
}

# =============================================================================
# AGENTES NOCIVOS - Conforme Decreto 3.048/99, Anexo IV
# =============================================================================

AGENTES_FISICOS = {
    "RUIDO": {
        "descricao": "Ruido acima dos limites de tolerancia",
        "limites": {
            "ate_05031997": "Acima de 80 dB(A) - Decreto 53.831/64",
            "de_06031997_a_18112003": "Acima de 90 dB(A) - Decreto 2.172/97",
            "apos_19112003": "Acima de 85 dB(A) - Decreto 4.882/03",
        },
        "codigo_anexo_iv": "2.0.1",
        "aposentadoria_especial_anos": 25,
    },
    "CALOR": {
        "descricao": "Temperaturas anormais - exposicao ao calor acima dos limites",
        "codigo_anexo_iv": "2.0.2",
        "aposentadoria_especial_anos": 25,
    },
    "FRIO": {
        "descricao": "Temperaturas anormais - exposicao ao frio intenso",
        "codigo_anexo_iv": "2.0.2",
        "aposentadoria_especial_anos": 25,
    },
    "VIBRACOES": {
        "descricao": "Vibracoes localizadas ou de corpo inteiro",
        "codigo_anexo_iv": "2.0.3",
        "aposentadoria_especial_anos": 25,
    },
    "RADIACOES_IONIZANTES": {
        "descricao": "Radiacoes ionizantes (raios X, gama, alfa, beta, neutrons)",
        "codigo_anexo_iv": "2.0.4",
        "aposentadoria_especial_anos": 25,
    },
    "RADIACOES_NAO_IONIZANTES": {
        "descricao": "Radiacoes nao ionizantes (micro-ondas, ultravioleta, laser)",
        "observacao": "Reconhecimento ate 05/03/1997 por enquadramento",
        "aposentadoria_especial_anos": 25,
    },
    "PRESSAO_ATMOSFERICA": {
        "descricao": "Pressao atmosferica anormal (trabalhos submersos, tubuloes, caixoes)",
        "codigo_anexo_iv": "2.0.5",
        "aposentadoria_especial_anos": 25,
    },
    "UMIDADE": {
        "descricao": "Umidade excessiva",
        "observacao": "Reconhecimento ate 05/03/1997 por enquadramento",
        "aposentadoria_especial_anos": 25,
    },
    "ELETRICIDADE": {
        "descricao": "Eletricidade em condicoes de periculosidade (alta tensao)",
        "observacao": "Reconhecimento por periculosidade - equiparacao jurisprudencial",
        "aposentadoria_especial_anos": 25,
    },
}

AGENTES_QUIMICOS = {
    "AMIANTO_ASBESTO": {
        "descricao": "Amianto (asbesto) - todas as formas",
        "codigo_anexo_iv": "1.0.3",
        "aposentadoria_especial_anos": 20,
    },
    "ARSENIO": {
        "descricao": "Arsenio e seus compostos",
        "codigo_anexo_iv": "1.0.1",
        "aposentadoria_especial_anos": 25,
    },
    "BENZENO": {
        "descricao": "Benzeno e homologos toxicos (tolueno, xileno)",
        "codigo_anexo_iv": "1.0.7",
        "aposentadoria_especial_anos": 25,
    },
    "CHUMBO": {
        "descricao": "Chumbo e seus compostos",
        "codigo_anexo_iv": "1.0.2",
        "aposentadoria_especial_anos": 25,
    },
    "CROMO": {
        "descricao": "Cromo e seus compostos toxicos",
        "codigo_anexo_iv": "1.0.4",
        "aposentadoria_especial_anos": 25,
    },
    "FOSFORO": {
        "descricao": "Fosforo e seus compostos (fosfina, fosfatos organicos)",
        "codigo_anexo_iv": "1.0.5",
        "aposentadoria_especial_anos": 25,
    },
    "MANGANES": {
        "descricao": "Manganes e seus compostos",
        "codigo_anexo_iv": "1.0.8",
        "aposentadoria_especial_anos": 25,
    },
    "MERCURIO": {
        "descricao": "Mercurio e seus compostos",
        "codigo_anexo_iv": "1.0.6",
        "aposentadoria_especial_anos": 25,
    },
    "SILICA_LIVRE": {
        "descricao": "Silica livre cristalizada (quartzo, cristobalita, tridimita)",
        "codigo_anexo_iv": "1.0.18",
        "aposentadoria_especial_anos": 25,
    },
    "HIDROCARBONETOS": {
        "descricao": "Hidrocarbonetos aromaticos e derivados halogenados",
        "codigo_anexo_iv": "1.0.7",
        "aposentadoria_especial_anos": 25,
    },
    "POEIRAS_MINERAIS": {
        "descricao": "Poeiras minerais (ite,ite de algodao,ite de cana)",
        "codigo_anexo_iv": "1.0.12",
        "aposentadoria_especial_anos": 25,
    },
    "SOLVENTES_ORGANICOS": {
        "descricao": "Solventes organicos (thinner, acetona, etc)",
        "codigo_anexo_iv": "1.0.19",
        "aposentadoria_especial_anos": 25,
    },
    "ACIDO_SULFURICO": {
        "descricao": "Acidos inorganicos e seus anidridos",
        "codigo_anexo_iv": "1.0.9",
        "aposentadoria_especial_anos": 25,
    },
    "CLORO": {
        "descricao": "Cloro e compostos clorados",
        "codigo_anexo_iv": "1.0.10",
        "aposentadoria_especial_anos": 25,
    },
    "AGROTOXICOS": {
        "descricao": "Agrotoxicos (organofosforados, carbamatos, organoclorados, piretroides)",
        "codigo_anexo_iv": "1.0.11",
        "aposentadoria_especial_anos": 25,
    },
    "TINTAS_VERNIZES": {
        "descricao": "Tintas, vernizes, esmaltes e lacas (com solventes organicos)",
        "codigo_anexo_iv": "1.0.19",
        "aposentadoria_especial_anos": 25,
    },
    "FUMOS_METALICOS": {
        "descricao": "Fumos metalicos (soldagem, fundicao)",
        "codigo_anexo_iv": "1.0.17",
        "aposentadoria_especial_anos": 25,
    },
    "ALCALIS_CAUSTICOS": {
        "descricao": "Alcalis causticos (soda caustica, potassa caustica)",
        "codigo_anexo_iv": "1.0.15",
        "aposentadoria_especial_anos": 25,
    },
    "NIQUEL": {
        "descricao": "Niquel e seus compostos",
        "codigo_anexo_iv": "1.0.16",
        "aposentadoria_especial_anos": 25,
    },
    "CADMIO": {
        "descricao": "Cadmio e seus compostos",
        "codigo_anexo_iv": "1.0.13",
        "aposentadoria_especial_anos": 25,
    },
    "ISOCIANATOS": {
        "descricao": "Isocianatos (TDI, MDI - industria de poliuretano)",
        "codigo_anexo_iv": "1.0.19",
        "aposentadoria_especial_anos": 25,
    },
    "CIMENTO": {
        "descricao": "Cimento Portland (ite alcalina e silica)",
        "codigo_anexo_iv": "1.0.18",
        "aposentadoria_especial_anos": 25,
    },
}

AGENTES_BIOLOGICOS = {
    "MICRO_ORGANISMOS_SAUDE": {
        "descricao": "Micro-organismos e parasitas infecciosos vivos e suas toxinas - trabalho em saude",
        "codigo_anexo_iv": "3.0.1",
        "aposentadoria_especial_anos": 25,
    },
    "MICRO_ORGANISMOS_ESGOTO": {
        "descricao": "Micro-organismos e parasitas - contato com esgotos e lixo urbano",
        "codigo_anexo_iv": "3.0.1",
        "aposentadoria_especial_anos": 25,
    },
    "MICRO_ORGANISMOS_ANIMAIS": {
        "descricao": "Micro-organismos - trabalho com animais infectados ou material biologico animal",
        "codigo_anexo_iv": "3.0.1",
        "aposentadoria_especial_anos": 25,
    },
}

# =============================================================================
# CNAE - GRUPOS DE ATIVIDADES ECONOMICAS COM RISCO ELEVADO
# Mapeamento de grupos/divisoes CNAE para agentes nocivos provaveis
# =============================================================================

CNAE_ATIVIDADES_ESPECIAIS = {
    # ---- MINERACAO ----
    "05": {
        "descricao": "Extracao de carvao mineral",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "VIBRACOES", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 15,
    },
    "07": {
        "descricao": "Extracao de minerais metalicos",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "SILICA_LIVRE", "VIBRACOES", "MANGANES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "08": {
        "descricao": "Extracao de minerais nao-metalicos",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "SILICA_LIVRE", "VIBRACOES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "0810": {
        "descricao": "Extracao de pedra, areia e argila",
        "agentes_provaveis": ["RUIDO", "SILICA_LIVRE", "POEIRAS_MINERAIS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "09": {
        "descricao": "Atividades de apoio a extracao mineral",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- INDUSTRIA ALIMENTICIA / FRIGORIFICOS ----
    "10.1": {
        "descricao": "Abate e fabricacao de produtos de carne (frigorifico)",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS", "UMIDADE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "1011": {
        "descricao": "Abate de reses, exceto suinos",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "1012": {
        "descricao": "Abate de suinos, aves e outros pequenos animais",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- INDUSTRIA TEXTIL ----
    "13": {
        "descricao": "Fabricacao de produtos texteis",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- INDUSTRIA DE MADEIRA ----
    "16": {
        "descricao": "Fabricacao de produtos de madeira (serraria, compensados)",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "VIBRACOES", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "1610": {
        "descricao": "Desdobramento de madeira (serraria)",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- INDUSTRIA DE PAPEL E CELULOSE ----
    "17": {
        "descricao": "Fabricacao de celulose, papel e produtos de papel",
        "agentes_provaveis": ["RUIDO", "CLORO", "ALCALIS_CAUSTICOS", "ACIDO_SULFURICO"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- IMPRESSAO / GRAFICA ----
    "18": {
        "descricao": "Impressao e reproducao de gravacoes (grafica)",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "HIDROCARBONETOS", "TINTAS_VERNIZES", "RUIDO"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- DERIVADOS DE PETROLEO ----
    "19": {
        "descricao": "Fabricacao de coque, derivados de petroleo e biocombustiveis",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS", "RUIDO", "CALOR"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- INDUSTRIA QUIMICA ----
    "20": {
        "descricao": "Fabricacao de produtos quimicos",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "CLORO", "ACIDO_SULFURICO", "BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2011": {
        "descricao": "Fabricacao de cloro e alcalis",
        "agentes_provaveis": ["CLORO", "ALCALIS_CAUSTICOS", "MERCURIO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2012": {
        "descricao": "Fabricacao de intermediarios para fertilizantes",
        "agentes_provaveis": ["ACIDO_SULFURICO", "FOSFORO", "AMONIA"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2013": {
        "descricao": "Fabricacao de adubos e fertilizantes",
        "agentes_provaveis": ["FOSFORO", "ACIDO_SULFURICO", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2021": {
        "descricao": "Fabricacao de produtos petroquimicos basicos",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2029": {
        "descricao": "Fabricacao de produtos quimicos organicos nao especificados",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2051": {
        "descricao": "Fabricacao de defensivos agricolas (agrotoxicos)",
        "agentes_provaveis": ["AGROTOXICOS", "SOLVENTES_ORGANICOS", "FOSFORO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2052": {
        "descricao": "Fabricacao de desinfetantes domissanitarios",
        "agentes_provaveis": ["CLORO", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "2061": {
        "descricao": "Fabricacao de saboes e detergentes sinteticos",
        "agentes_provaveis": ["ALCALIS_CAUSTICOS", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "2071": {
        "descricao": "Fabricacao de tintas, vernizes, esmaltes e lacas",
        "agentes_provaveis": ["TINTAS_VERNIZES", "SOLVENTES_ORGANICOS", "HIDROCARBONETOS", "CHUMBO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- FARMACEUTICA ----
    "21": {
        "descricao": "Fabricacao de produtos farmoquimicos e farmaceuticos",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- BORRACHA E PLASTICO ----
    "22": {
        "descricao": "Fabricacao de produtos de borracha e material plastico",
        "agentes_provaveis": ["HIDROCARBONETOS", "RUIDO", "CALOR", "ISOCIANATOS", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2211": {
        "descricao": "Fabricacao de pneumaticos e camaras-de-ar",
        "agentes_provaveis": ["HIDROCARBONETOS", "BENZENO", "CALOR", "RUIDO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- MINERAIS NAO-METALICOS (CERAMICA, VIDRO, CIMENTO) ----
    "23": {
        "descricao": "Fabricacao de produtos de minerais nao-metalicos (ceramica, vidro, cimento)",
        "agentes_provaveis": ["SILICA_LIVRE", "CALOR", "RUIDO", "POEIRAS_MINERAIS", "CIMENTO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2320": {
        "descricao": "Fabricacao de cimento",
        "agentes_provaveis": ["SILICA_LIVRE", "CIMENTO", "POEIRAS_MINERAIS", "CALOR", "RUIDO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- METALURGIA / SIDERURGIA ----
    "24": {
        "descricao": "Metalurgia (producao de ferro, aco, metais nao-ferrosos)",
        "agentes_provaveis": ["RUIDO", "CALOR", "FUMOS_METALICOS", "SILICA_LIVRE", "MANGANES", "CROMO", "NIQUEL"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2411": {
        "descricao": "Producao de ferro-gusa",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "MANGANES", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2412": {
        "descricao": "Producao de ferroligas",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "CROMO", "MANGANES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2421": {
        "descricao": "Producao de semi-acabados de aco (siderurgia)",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2441": {
        "descricao": "Metalurgia do aluminio e suas ligas",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "FLUORETOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2443": {
        "descricao": "Metalurgia do cobre",
        "agentes_provaveis": ["CALOR", "FUMOS_METALICOS", "RUIDO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- PRODUTOS DE METAL / FUNDICAO ----
    "25": {
        "descricao": "Fabricacao de produtos de metal, exceto maquinas e equipamentos",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS", "SOLVENTES_ORGANICOS", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "2451": {
        "descricao": "Fundicao de ferro e aco",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "SILICA_LIVRE", "VIBRACOES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2452": {
        "descricao": "Fundicao de metais nao-ferrosos e suas ligas",
        "agentes_provaveis": ["CALOR", "FUMOS_METALICOS", "CHUMBO", "RUIDO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "2511": {
        "descricao": "Fabricacao de estruturas metalicas",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "2539": {
        "descricao": "Servicos de usinagem, solda, tratamento e revestimento em metais",
        "agentes_provaveis": ["FUMOS_METALICOS", "RUIDO", "CROMO", "NIQUEL", "CADMIO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- ELETRICIDADE, GAS ----
    "35": {
        "descricao": "Eletricidade, gas e outras utilidades",
        "agentes_provaveis": ["ELETRICIDADE", "RUIDO"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "3511": {
        "descricao": "Geracao de energia eletrica",
        "agentes_provaveis": ["ELETRICIDADE", "RUIDO", "VIBRACOES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "3512": {
        "descricao": "Transmissao de energia eletrica",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "3513": {
        "descricao": "Comercio atacadista de energia eletrica",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "3514": {
        "descricao": "Distribuicao de energia eletrica",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- AGUA E ESGOTO ----
    "37": {
        "descricao": "Esgoto e atividades relacionadas",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO", "UMIDADE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "38": {
        "descricao": "Coleta, tratamento e disposicao de residuos; recuperacao de materiais",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO", "RUIDO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- CONSTRUCAO CIVIL ----
    "41": {
        "descricao": "Construcao de edificios",
        "agentes_provaveis": ["RUIDO", "CIMENTO", "SILICA_LIVRE", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "42": {
        "descricao": "Obras de infraestrutura",
        "agentes_provaveis": ["RUIDO", "SILICA_LIVRE", "VIBRACOES", "POEIRAS_MINERAIS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "43": {
        "descricao": "Servicos especializados para construcao",
        "agentes_provaveis": ["RUIDO", "CIMENTO", "TINTAS_VERNIZES", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- COMERCIO DE COMBUSTIVEIS ----
    "4731": {
        "descricao": "Comercio varejista de combustiveis para veiculos automotores (posto de gasolina)",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "4681": {
        "descricao": "Comercio atacadista de combustiveis solidos, liquidos e gasosos",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- TRANSPORTE ----
    "4930": {
        "descricao": "Transporte rodoviario de carga (incluindo inflamaveis)",
        "agentes_provaveis": ["HIDROCARBONETOS", "VIBRACOES", "RUIDO"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "4950": {
        "descricao": "Trens e ferrovias - transporte de carga",
        "agentes_provaveis": ["RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- SAUDE ----
    "86": {
        "descricao": "Atividades de atencao a saude humana",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "RADIACOES_IONIZANTES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "8610": {
        "descricao": "Atividades de atendimento hospitalar",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "RADIACOES_IONIZANTES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "8621": {
        "descricao": "Servicos moveis de atencao a saude (SAMU, ambulancia)",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "8630": {
        "descricao": "Atividades de atencao ambulatorial",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "8640": {
        "descricao": "Servicos de complementacao diagnostica e terapeutica (laboratorio/radiologia)",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "RADIACOES_IONIZANTES"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "8690": {
        "descricao": "Atividades de atencao a saude humana nao especificadas",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- SERVICOS VETERINARIOS ----
    "75": {
        "descricao": "Atividades veterinarias",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ANIMAIS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- AGRICULTURA / PECUARIA ----
    "01": {
        "descricao": "Agricultura, pecuaria e servicos relacionados",
        "agentes_provaveis": ["AGROTOXICOS", "RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    "0161": {
        "descricao": "Atividades de apoio a agricultura (aplicacao de defensivos)",
        "agentes_provaveis": ["AGROTOXICOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- FABRICACAO DE MAQUINAS E EQUIPAMENTOS ----
    "28": {
        "descricao": "Fabricacao de maquinas e equipamentos",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS", "SOLVENTES_ORGANICOS", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- FABRICACAO DE VEICULOS ----
    "29": {
        "descricao": "Fabricacao de veiculos automotores, reboques e carrocerias",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS", "TINTAS_VERNIZES", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- COURO / CURTUME ----
    "15": {
        "descricao": "Preparacao de couros e fabricacao de artefatos de couro (curtume)",
        "agentes_provaveis": ["CROMO", "SOLVENTES_ORGANICOS", "ACIDO_SULFURICO", "RUIDO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    "1510": {
        "descricao": "Curtimento e outras preparacoes de couro",
        "agentes_provaveis": ["CROMO", "ACIDO_SULFURICO", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- FABRICACAO DE MOVEIS ----
    "31": {
        "descricao": "Fabricacao de moveis",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "TINTAS_VERNIZES", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- FABRICACAO DE PRODUTOS DIVERSOS ----
    "2592": {
        "descricao": "Fabricacao de cal e gesso",
        "agentes_provaveis": ["POEIRAS_MINERAIS", "CALOR", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
    # ---- FABRICACAO DE BATERIAS / ACUMULADORES ----
    "2722": {
        "descricao": "Fabricacao de baterias e acumuladores para veiculos automotores",
        "agentes_provaveis": ["CHUMBO", "ACIDO_SULFURICO"],
        "probabilidade": "ALTA",
        "aposentadoria_especial_anos": 25,
    },
}

# =============================================================================
# PADROES DE NOMES DE EMPREGADORES - INDUSTRIAS COM ATIVIDADE ESPECIAL
# Mapeamento de termos comuns em razoes sociais para categorias de risco
# =============================================================================

PADROES_EMPREGADOR = {
    # ---- METALURGIA / SIDERURGIA / FUNDICAO ----
    "METALURGICA": {
        "categoria": "Metalurgia",
        "agentes_provaveis": ["RUIDO", "CALOR", "FUMOS_METALICOS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.6; Decreto 3.048/99 Anexo IV - codigo 1.0.17 (fumos metalicos), 2.0.1 (ruido)",
    },
    "SIDERURGICA": {
        "categoria": "Siderurgia",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "MANGANES", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.6; Decreto 3.048/99 Anexo IV - codigos 1.0.8 (manganes), 1.0.17 (fumos metalicos), 2.0.1 (ruido), 2.0.2 (calor)",
    },
    "FUNDICAO": {
        "categoria": "Fundicao",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.6; Decreto 83.080/79 Anexo II - fundicao de metais; Decreto 3.048/99 Anexo IV",
    },
    "FUNDIDOS": {
        "categoria": "Fundicao",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.6; Decreto 3.048/99 Anexo IV",
    },
    "ACOS": {
        "categoria": "Siderurgia/Metalurgia",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - metalurgia",
    },
    "FERRO": {
        "categoria": "Siderurgia/Metalurgia",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS", "SILICA_LIVRE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - producao de ferro-gusa e similares",
    },
    "ALUMINIO": {
        "categoria": "Metalurgia do Aluminio",
        "agentes_provaveis": ["CALOR", "RUIDO", "FUMOS_METALICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - metalurgia do aluminio",
    },
    "GALVANOPLASTIA": {
        "categoria": "Tratamento de superficie metalica",
        "agentes_provaveis": ["CROMO", "NIQUEL", "CADMIO", "ACIDO_SULFURICO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigos 1.0.4 (cromo), 1.0.16 (niquel), 1.0.13 (cadmio)",
    },
    "CROMAGEM": {
        "categoria": "Tratamento de superficie metalica",
        "agentes_provaveis": ["CROMO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.4 (cromo)",
    },
    "SOLDAS": {
        "categoria": "Soldagem",
        "agentes_provaveis": ["FUMOS_METALICOS", "RADIACOES_NAO_IONIZANTES", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.17 (fumos metalicos)",
    },
    "CALDEIRARIA": {
        "categoria": "Metalurgia/Caldeiraria",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64; Decreto 3.048/99 Anexo IV",
    },
    "USINAGEM": {
        "categoria": "Usinagem de metais",
        "agentes_provaveis": ["RUIDO", "HIDROCARBONETOS", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - oleos minerais, ruido",
    },
    "TORNEARIA": {
        "categoria": "Usinagem de metais",
        "agentes_provaveis": ["RUIDO", "HIDROCARBONETOS", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - oleos minerais, ruido",
    },
    "ESTAMPARIA": {
        "categoria": "Estamparia metalica",
        "agentes_provaveis": ["RUIDO", "VIBRACOES", "HIDROCARBONETOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - ruido",
    },
    # ---- QUIMICA / PETROQUIMICA ----
    "QUIMICA": {
        "categoria": "Industria Quimica",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "HIDROCARBONETOS", "BENZENO", "ACIDO_SULFURICO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigos 1.2.9 a 1.2.11; Decreto 3.048/99 Anexo IV - agentes quimicos diversos",
    },
    "PETROQUIMICA": {
        "categoria": "Industria Petroquimica",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.11; Decreto 3.048/99 Anexo IV - codigo 1.0.7 (benzeno e homologos)",
    },
    "PETROBRAS": {
        "categoria": "Industria Petrolifera",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS", "RUIDO", "CALOR"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.7 (benzeno); periculosidade por inflamaveis",
    },
    "PETROLEO": {
        "categoria": "Industria Petrolifera",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS", "CALOR"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.7 (benzeno e homologos)",
    },
    "REFINARIA": {
        "categoria": "Refinaria de Petroleo",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS", "CALOR", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.11; Decreto 3.048/99 Anexo IV",
    },
    # ---- MINERACAO ----
    "MINERACAO": {
        "categoria": "Mineracao",
        "agentes_provaveis": ["SILICA_LIVRE", "POEIRAS_MINERAIS", "RUIDO", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.1; Decreto 3.048/99 Anexo IV - codigo 1.0.18 (silica); mineracao subterranea: 15 ou 20 anos",
    },
    "MINERADORA": {
        "categoria": "Mineracao",
        "agentes_provaveis": ["SILICA_LIVRE", "POEIRAS_MINERAIS", "RUIDO", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.1; Decreto 3.048/99 Anexo IV",
    },
    "PEDREIRA": {
        "categoria": "Mineracao/Extracao de pedra",
        "agentes_provaveis": ["SILICA_LIVRE", "RUIDO", "VIBRACOES", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.1; Decreto 3.048/99 Anexo IV - codigo 1.0.18",
    },
    "BRITAGEM": {
        "categoria": "Mineracao/Britagem",
        "agentes_provaveis": ["SILICA_LIVRE", "RUIDO", "POEIRAS_MINERAIS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.18 (silica livre), 2.0.1 (ruido)",
    },
    "MARMORE": {
        "categoria": "Extracao/Beneficiamento de marmore",
        "agentes_provaveis": ["SILICA_LIVRE", "RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.18 (silica)",
    },
    "GRANITO": {
        "categoria": "Extracao/Beneficiamento de granito",
        "agentes_provaveis": ["SILICA_LIVRE", "RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.18 (silica)",
    },
    # ---- CONSTRUCAO CIVIL ----
    "CONSTRUTORA": {
        "categoria": "Construcao Civil",
        "agentes_provaveis": ["RUIDO", "CIMENTO", "SILICA_LIVRE", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - depende da funcao exercida (pedreiro, pintor, eletricista, etc.)",
    },
    "CONSTRUCAO": {
        "categoria": "Construcao Civil",
        "agentes_provaveis": ["RUIDO", "CIMENTO", "SILICA_LIVRE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - depende da funcao exercida",
    },
    "ENGENHARIA": {
        "categoria": "Engenharia/Construcao",
        "agentes_provaveis": ["RUIDO", "CIMENTO", "VIBRACOES"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - depende da funcao exercida e tipo de obra",
    },
    "TERRAPLENAGEM": {
        "categoria": "Terraplenagem/Construcao",
        "agentes_provaveis": ["RUIDO", "VIBRACOES", "POEIRAS_MINERAIS", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - operadores de maquinas pesadas",
    },
    # ---- SAUDE / HOSPITAIS / LABORATORIOS ----
    "HOSPITAL": {
        "categoria": "Saude - Atendimento Hospitalar",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "RADIACOES_IONIZANTES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1 (agentes biologicos)",
    },
    "HOSPITALAR": {
        "categoria": "Saude - Atendimento Hospitalar",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "LABORATORIO": {
        "categoria": "Laboratorio de Analises",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "CLINICA": {
        "categoria": "Saude - Atendimento Clinico",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1 (depende da especialidade e contato com pacientes)",
    },
    "ODONTOLOGICA": {
        "categoria": "Saude - Odontologia",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "MERCURIO", "RADIACOES_IONIZANTES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1 (agentes biologicos)",
    },
    "RADIOLOGIA": {
        "categoria": "Saude - Radiologia",
        "agentes_provaveis": ["RADIACOES_IONIZANTES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.3; Decreto 3.048/99 Anexo IV - codigo 2.0.4",
    },
    "DIAGNOSTICO": {
        "categoria": "Saude - Diagnostico",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "RADIACOES_IONIZANTES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigos 2.0.4 e 3.0.1",
    },
    "HEMOTERAPIA": {
        "categoria": "Saude - Hemoterapia",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1 (contato com sangue e derivados)",
    },
    "FARMACIA": {
        "categoria": "Farmacia",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Geralmente nao se enquadra, salvo manipulacao de quimioterapicos ou contato direto com pacientes",
    },
    "PRONTO SOCORRO": {
        "categoria": "Saude - Pronto Socorro",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "UPA": {
        "categoria": "Saude - Unidade de Pronto Atendimento",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "SANTA CASA": {
        "categoria": "Saude - Hospital Filantrópico",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "RADIACOES_IONIZANTES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    # ---- ELETRICIDADE ----
    "ELETRICA": {
        "categoria": "Setor Eletrico",
        "agentes_provaveis": ["ELETRICIDADE", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8 (eletricidade acima de 250V); Lei 7.369/85; jurisprudencia consolidada (STJ)",
    },
    "ELETRONICA": {
        "categoria": "Eletronica",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "CHUMBO"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Depende da funcao - soldagem com chumbo/estanho em placas eletronicas",
    },
    "PHILIPS": {
        "categoria": "Industria Eletronica / Eletrodomesticos",
        "agentes_provaveis": ["RUIDO", "SOLVENTES_ORGANICOS", "CHUMBO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Industria de grande porte - possivel exposicao a ruido industrial, solventes e metais pesados em linha de producao. Verificar funcao exercida e solicitar PPP.",
    },
    "SAMSUNG": {
        "categoria": "Industria Eletronica",
        "agentes_provaveis": ["RUIDO", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Industria de grande porte - verificar funcao e exposicao",
    },
    "WHIRLPOOL": {
        "categoria": "Industria Eletrodomesticos",
        "agentes_provaveis": ["RUIDO", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Industria de grande porte (Brastemp/Consul) - verificar funcao e exposicao",
    },
    "BRASTEMP": {
        "categoria": "Industria Eletrodomesticos",
        "agentes_provaveis": ["RUIDO", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Industria de grande porte - verificar funcao e exposicao",
    },
    "ENERGIA": {
        "categoria": "Setor Energetico",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8; depende se ha contato com alta tensao",
    },
    "ELETROPAULO": {
        "categoria": "Distribuidora de Energia",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8; periculosidade por eletricidade",
    },
    "CPFL": {
        "categoria": "Distribuidora de Energia",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8",
    },
    "CEMIG": {
        "categoria": "Distribuidora de Energia",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8",
    },
    "LIGHT": {
        "categoria": "Distribuidora de Energia",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8 (verificar funcao exercida)",
    },
    "COPEL": {
        "categoria": "Distribuidora de Energia",
        "agentes_provaveis": ["ELETRICIDADE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8",
    },
    # ---- BORRACHA / PLASTICO ----
    "BORRACHA": {
        "categoria": "Industria da Borracha",
        "agentes_provaveis": ["HIDROCARBONETOS", "BENZENO", "CALOR", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.10; Decreto 3.048/99 Anexo IV - codigo 1.0.7",
    },
    "PLASTICO": {
        "categoria": "Industria de Plastico",
        "agentes_provaveis": ["HIDROCARBONETOS", "ISOCIANATOS", "CALOR", "RUIDO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - depende do tipo de plastico e processo",
    },
    "EMBALAGENS": {
        "categoria": "Fabricacao de Embalagens",
        "agentes_provaveis": ["RUIDO", "SOLVENTES_ORGANICOS"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - depende do material (plastico, papel, metal)",
    },
    # ---- MADEIRA / SERRARIA ----
    "MADEIREIRA": {
        "categoria": "Industria Madeireira",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.5 (madeira); Decreto 3.048/99 Anexo IV - ruido e poeiras",
    },
    "SERRARIA": {
        "categoria": "Serraria",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.5; Decreto 3.048/99 Anexo IV",
    },
    "MOVELEIRA": {
        "categoria": "Industria Moveleira",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "TINTAS_VERNIZES", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - ruido, poeiras, solventes",
    },
    "COMPENSADOS": {
        "categoria": "Fabricacao de Compensados",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - colas com formaldeido, poeiras de madeira",
    },
    "MARCENARIA": {
        "categoria": "Marcenaria",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS", "TINTAS_VERNIZES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - ruido, poeiras, solventes",
    },
    # ---- FRIGORIFICO ----
    "FRIGORIFICO": {
        "categoria": "Frigorifico",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS", "UMIDADE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.2 (frio); Decreto 3.048/99 Anexo IV - codigo 2.0.2 (temperaturas anormais)",
    },
    "FRIGORIFICA": {
        "categoria": "Frigorifico",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 2.0.2",
    },
    "FRIGORFICO": {
        "categoria": "Frigorifico",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS", "UMIDADE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.2 (frio); Decreto 3.048/99 Anexo IV - codigo 2.0.2",
    },
    "ABATEDOURO": {
        "categoria": "Abatedouro/Frigorifico",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 2.0.2 (frio), 3.0.1 (biologico)",
    },
    "AVICOLA": {
        "categoria": "Avicultura/Frigorifico de Aves",
        "agentes_provaveis": ["FRIO", "RUIDO", "MICRO_ORGANISMOS_ANIMAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigos 2.0.2 e 3.0.1",
    },
    "ALIMENTOS": {
        "categoria": "Industria Alimenticia",
        "agentes_provaveis": ["FRIO", "RUIDO"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Depende do setor - frigorifica sim; padaria/biscoitos geralmente nao",
    },
    # ---- COMBUSTIVEIS / POSTOS ----
    "COMBUSTIVEL": {
        "categoria": "Comercio de Combustiveis",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.7 (benzeno); periculosidade por inflamaveis",
    },
    "COMBUSTIVEIS": {
        "categoria": "Comercio de Combustiveis",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.7 (benzeno)",
    },
    "POSTO": {
        "categoria": "Posto de Combustivel",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.7 (benzeno); frentistas - exposicao a hidrocarbonetos",
    },
    "GASOLINA": {
        "categoria": "Comercio de Combustiveis",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.7",
    },
    "DISTRIBUIDORA DE GAS": {
        "categoria": "Distribuicao de Gas",
        "agentes_provaveis": ["HIDROCARBONETOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Periculosidade por inflamaveis - NR 16",
    },
    # ---- TEXTIL ----
    "TEXTIL": {
        "categoria": "Industria Textil",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.5 (texteis); Decreto 3.048/99 Anexo IV - ruido e poeira de algodao (bissinose)",
    },
    "TECELAGEM": {
        "categoria": "Tecelagem",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.5; ruido frequentemente acima de 85 dB(A)",
    },
    "FIACAO": {
        "categoria": "Fiacao",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.5; poeira de algodao - bissinose",
    },
    "ALGODAO": {
        "categoria": "Industria de Algodao",
        "agentes_provaveis": ["RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - poeira de algodao",
    },
    "TINTURARIA": {
        "categoria": "Tinturaria/Textil",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "CALOR", "UMIDADE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - produtos quimicos de tingimento",
    },
    # ---- GRAFICA ----
    "GRAFICA": {
        "categoria": "Industria Grafica",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "HIDROCARBONETOS", "TINTAS_VERNIZES", "RUIDO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.11; Decreto 3.048/99 Anexo IV - solventes organicos e tintas",
    },
    "EDITORA": {
        "categoria": "Industria Grafica/Editorial",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "HIDROCARBONETOS"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Depende da funcao - operadores de impressao podem ter exposicao a solventes",
    },
    # ---- CURTUME / COURO ----
    "CURTUME": {
        "categoria": "Curtume/Preparacao de Couros",
        "agentes_provaveis": ["CROMO", "ACIDO_SULFURICO", "SOLVENTES_ORGANICOS", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.9 (cromo); Decreto 3.048/99 Anexo IV - codigo 1.0.4",
    },
    "COURO": {
        "categoria": "Industria do Couro",
        "agentes_provaveis": ["CROMO", "SOLVENTES_ORGANICOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.4 (cromo) para etapa de curtimento",
    },
    "CALCADOS": {
        "categoria": "Fabricacao de Calcados",
        "agentes_provaveis": ["SOLVENTES_ORGANICOS", "BENZENO", "RUIDO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - colas com solventes aromaticos (benzeno, tolueno, xileno)",
    },
    # ---- PINTURA INDUSTRIAL ----
    "PINTURA": {
        "categoria": "Pintura Industrial",
        "agentes_provaveis": ["TINTAS_VERNIZES", "SOLVENTES_ORGANICOS", "HIDROCARBONETOS", "CHUMBO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.11; Decreto 3.048/99 Anexo IV - codigo 1.0.19 (solventes) e 1.0.2 (chumbo em tintas antigas)",
    },
    "TINTA": {
        "categoria": "Fabricacao/Aplicacao de Tintas",
        "agentes_provaveis": ["TINTAS_VERNIZES", "SOLVENTES_ORGANICOS", "CHUMBO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.19",
    },
    "VERNIZ": {
        "categoria": "Fabricacao de Vernizes",
        "agentes_provaveis": ["TINTAS_VERNIZES", "SOLVENTES_ORGANICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.19",
    },
    # ---- AGROTOXICOS / DEFENSIVOS ----
    "AGROTOXICO": {
        "categoria": "Fabricacao/Aplicacao de Agrotoxicos",
        "agentes_provaveis": ["AGROTOXICOS", "FOSFORO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.11 (fosforo e compostos); NR 31",
    },
    "DEFENSIVO": {
        "categoria": "Defensivos Agricolas",
        "agentes_provaveis": ["AGROTOXICOS", "FOSFORO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.11",
    },
    "AGROPECUARIA": {
        "categoria": "Agropecuaria",
        "agentes_provaveis": ["AGROTOXICOS", "RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - depende se ha aplicacao de defensivos agricolas",
    },
    "USINA DE ACUCAR": {
        "categoria": "Usina de Acucar e Alcool",
        "agentes_provaveis": ["RUIDO", "CALOR", "POEIRAS_MINERAIS", "HIDROCARBONETOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - ruido e calor na producao de acucar e etanol",
    },
    "USINA": {
        "categoria": "Usina (acucar/energia/siderurgia)",
        "agentes_provaveis": ["RUIDO", "CALOR"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Depende do tipo de usina - verificar atividade principal",
    },
    # ---- TRANSPORTE DE INFLAMAVEIS ----
    "TRANSPORTADORA": {
        "categoria": "Transporte de Cargas",
        "agentes_provaveis": ["VIBRACOES", "RUIDO"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Atividade especial se transporte de inflamaveis ou produtos quimicos perigosos",
    },
    "TRANSPORTE DE INFLAMAVEIS": {
        "categoria": "Transporte de Inflamaveis",
        "agentes_provaveis": ["HIDROCARBONETOS", "BENZENO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Periculosidade por inflamaveis - NR 16; Decreto 53.831/64",
    },
    # ---- CIMENTO / CERAMICA / VIDRO ----
    "CIMENTO": {
        "categoria": "Industria do Cimento",
        "agentes_provaveis": ["SILICA_LIVRE", "CIMENTO", "POEIRAS_MINERAIS", "CALOR", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.12; Decreto 3.048/99 Anexo IV - codigo 1.0.18",
    },
    "CERAMICA": {
        "categoria": "Industria Ceramica",
        "agentes_provaveis": ["SILICA_LIVRE", "CALOR", "RUIDO", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.18 (silica); fornos ceramicos - calor",
    },
    "VIDRO": {
        "categoria": "Industria do Vidro",
        "agentes_provaveis": ["SILICA_LIVRE", "CALOR", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.12; Decreto 3.048/99 Anexo IV - codigo 1.0.18",
    },
    "REFRATARIO": {
        "categoria": "Fabricacao de Materiais Refratarios",
        "agentes_provaveis": ["SILICA_LIVRE", "CALOR", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.18 (silica)",
    },
    # ---- AMIANTO ----
    "AMIANTO": {
        "categoria": "Industria do Amianto",
        "agentes_provaveis": ["AMIANTO_ASBESTO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.3 - aposentadoria especial em 20 anos",
    },
    "ETERNIT": {
        "categoria": "Fabricacao de Produtos de Fibrocimento",
        "agentes_provaveis": ["AMIANTO_ASBESTO", "CIMENTO", "SILICA_LIVRE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.3 (amianto) - 20 anos",
    },
    "BRASILIT": {
        "categoria": "Fabricacao de Produtos de Fibrocimento",
        "agentes_provaveis": ["AMIANTO_ASBESTO", "CIMENTO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.3 (amianto) - 20 anos",
    },
    # ---- LIMPEZA URBANA / COLETA DE LIXO ----
    "LIMPEZA URBANA": {
        "categoria": "Limpeza Urbana/Coleta de Lixo",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1 (agentes biologicos em lixo urbano)",
    },
    "COLETA DE LIXO": {
        "categoria": "Coleta de Residuos",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "SANEAMENTO": {
        "categoria": "Saneamento Basico",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO", "CLORO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1 (contato com esgoto)",
    },
    "SABESP": {
        "categoria": "Saneamento Basico",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO", "CLORO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1 (contato com esgoto)",
    },
    "SAAE": {
        "categoria": "Saneamento Basico (SAAE)",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO", "CLORO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1 (contato com esgoto). Depende da funcao exercida.",
    },
    "AGUA E ESGOTO": {
        "categoria": "Saneamento Basico",
        "agentes_provaveis": ["MICRO_ORGANISMOS_ESGOTO", "CLORO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    # ---- BATERIA / ACUMULADORES ----
    "BATERIA": {
        "categoria": "Fabricacao/Recondicionamento de Baterias",
        "agentes_provaveis": ["CHUMBO", "ACIDO_SULFURICO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.1 (chumbo); Decreto 3.048/99 Anexo IV - codigo 1.0.2",
    },
    "ACUMULADORES": {
        "categoria": "Fabricacao de Acumuladores Eletricos",
        "agentes_provaveis": ["CHUMBO", "ACIDO_SULFURICO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.2 (chumbo)",
    },
    # ---- OUTROS ----
    "LAVANDERIA": {
        "categoria": "Lavanderia Industrial/Hospitalar",
        "agentes_provaveis": ["MICRO_ORGANISMOS_SAUDE", "SOLVENTES_ORGANICOS", "CALOR", "UMIDADE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Lavanderia hospitalar: agentes biologicos (Decreto 3.048/99 Anexo IV - 3.0.1); lavanderia comum: geralmente nao",
    },
    "VIGILANCIA": {
        "categoria": "Vigilancia/Seguranca Patrimonial",
        "agentes_provaveis": [],
        "probabilidade": "MEDIA",
        "fundamentacao": "Periculosidade por uso de arma de fogo - Lei 12.740/2012; divergencia sobre contagem especial apos EC 103/2019",
    },
    "SEGURANCA": {
        "categoria": "Seguranca Privada",
        "agentes_provaveis": [],
        "probabilidade": "MEDIA",
        "fundamentacao": "Periculosidade por uso de arma de fogo; Lei 12.740/2012; depende de porte de arma",
    },
    # ---- CARGOS / FUNCOES ESPECIAIS (para analise via CTPS) ----
    "SOLDADOR": {
        "categoria": "Soldador",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS", "RADIACAO_NAO_IONIZANTE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 2.5.3; Decreto 83.080/79 Anexo II; Decreto 3.048/99 Anexo IV - fumos metalicos (1.0.17) e ruido (2.0.1)",
    },
    "TORNEIRO": {
        "categoria": "Torneiro Mecanico",
        "agentes_provaveis": ["RUIDO", "VIBRACOES", "OLEO_MINERAL"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.6; Decreto 3.048/99 Anexo IV - ruido (2.0.1), oleos minerais (1.0.19)",
    },
    "ELETRICISTA": {
        "categoria": "Eletricista",
        "agentes_provaveis": [],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8; Lei 7.369/85 - periculosidade por eletricidade; Decreto 3.048/99 Anexo IV - codigo 2.0.3 (eletricidade)",
    },
    "ELETROTECNICO": {
        "categoria": "Eletricista/Eletrotecnico",
        "agentes_provaveis": [],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.8; Lei 7.369/85 - periculosidade; Decreto 3.048/99 Anexo IV",
    },
    "MOTORISTA": {
        "categoria": "Motorista",
        "agentes_provaveis": ["RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 2.4.4 (motorista de onibus); Decreto 83.080/79 Anexo II; STJ REsp 1.306.113/SC - motorista de caminhao com periculosidade por inflamaveis",
    },
    "COBRADOR": {
        "categoria": "Cobrador de Onibus",
        "agentes_provaveis": ["RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 2.4.4; analogia com motorista de onibus",
    },
    "ENFERMEIRO": {
        "categoria": "Enfermagem",
        "agentes_provaveis": ["MICROORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1 (trabalhos em estabelecimentos de saude)",
    },
    "ENFERMEIRA": {
        "categoria": "Enfermagem",
        "agentes_provaveis": ["MICROORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "TECNICO DE ENFERMAGEM": {
        "categoria": "Enfermagem",
        "agentes_provaveis": ["MICROORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "AUXILIAR DE ENFERMAGEM": {
        "categoria": "Enfermagem",
        "agentes_provaveis": ["MICROORGANISMOS_SAUDE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "MEDICO": {
        "categoria": "Medicina",
        "agentes_provaveis": ["MICROORGANISMOS_SAUDE", "RADIACAO_IONIZANTE"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "DENTISTA": {
        "categoria": "Odontologia",
        "agentes_provaveis": ["MICROORGANISMOS_SAUDE", "RUIDO"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.3.2; Decreto 3.048/99 Anexo IV - codigo 3.0.1",
    },
    "FRENTISTA": {
        "categoria": "Frentista/Posto de Combustivel",
        "agentes_provaveis": ["BENZENO", "HIDROCARBONETOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.3 (benzeno); periculosidade por inflamaveis - NR-16",
    },
    "BOMBEIRO": {
        "categoria": "Bombeiro",
        "agentes_provaveis": [],
        "probabilidade": "ALTA",
        "fundamentacao": "Periculosidade inerente; exposicao a agentes quimicos em incendios; Decreto 53.831/64",
    },
    "PEDREIRO": {
        "categoria": "Construcao Civil",
        "agentes_provaveis": ["RUIDO", "CIMENTO", "SILICA_LIVRE"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 1.0.17 (poeiras minerais); codigo 2.0.1 (ruido); depende das condicoes do ambiente",
    },
    "PINTOR": {
        "categoria": "Pintor Industrial/Predial",
        "agentes_provaveis": ["HIDROCARBONETOS", "CHUMBO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.2.11; Decreto 3.048/99 Anexo IV - codigo 1.0.7 (chumbo), 1.0.19 (hidrocarbonetos)",
    },
    "OPERADOR DE MAQUINA": {
        "categoria": "Operador de Maquinas",
        "agentes_provaveis": ["RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - codigo 2.0.1 (ruido), 2.0.5 (vibracoes); depende do tipo de maquina",
    },
    "CALDEIREIRO": {
        "categoria": "Caldeireiro/Caldeiraria",
        "agentes_provaveis": ["RUIDO", "CALOR", "FUMOS_METALICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.5 (caldeiras); Decreto 3.048/99 Anexo IV - ruido (2.0.1), calor (2.0.2)",
    },
    "FUNILEIRO": {
        "categoria": "Funileiro",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.6; Decreto 3.048/99 Anexo IV - fumos metalicos (1.0.17), ruido (2.0.1)",
    },
    "SERRALHEIRO": {
        "categoria": "Serralheiro",
        "agentes_provaveis": ["RUIDO", "FUMOS_METALICOS", "VIBRACOES"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64; Decreto 3.048/99 Anexo IV - ruido (2.0.1), fumos metalicos (1.0.17)",
    },
    "MECANICO": {
        "categoria": "Mecanico",
        "agentes_provaveis": ["RUIDO", "OLEO_MINERAL", "HIDROCARBONETOS"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64; Decreto 3.048/99 Anexo IV - oleos minerais (1.0.19), ruido (2.0.1); depende do tipo de oficina",
    },
    "AJUSTADOR": {
        "categoria": "Ajustador Mecanico",
        "agentes_provaveis": ["RUIDO", "VIBRACOES", "OLEO_MINERAL"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 1.1.6; Decreto 3.048/99 Anexo IV",
    },
    "MINEIRO": {
        "categoria": "Mineracao",
        "agentes_provaveis": ["RUIDO", "VIBRACOES", "SILICA_LIVRE", "POEIRAS_MINERAIS"],
        "probabilidade": "ALTA",
        "fundamentacao": "Decreto 53.831/64 - codigo 2.3.3 (trabalhos em mineracao subterranea); Decreto 3.048/99 Anexo IV; aposentadoria especial de 15 ou 20 anos",
    },
    "TELEFONISTA": {
        "categoria": "Telefonista",
        "agentes_provaveis": ["RUIDO"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 2.4.5 (telefonista); enquadramento ate 28/04/1995 por categoria profissional",
    },
    "VIGIA": {
        "categoria": "Vigia/Vigilante",
        "agentes_provaveis": [],
        "probabilidade": "MEDIA",
        "fundamentacao": "Periculosidade por uso de arma; Decreto 53.831/64; STJ - equiparacao ao vigilante",
    },
    "TRATORISTA": {
        "categoria": "Tratorista",
        "agentes_provaveis": ["RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 53.831/64 - codigo 2.4.4; Decreto 3.048/99 Anexo IV - vibracoes (2.0.5), ruido (2.0.1)",
    },
    "AUXILIAR DE PRODUCAO": {
        "categoria": "Auxiliar de Producao Industrial",
        "agentes_provaveis": ["RUIDO"],
        "probabilidade": "BAIXA",
        "fundamentacao": "Depende do ramo industrial; se em metalurgia/quimica/siderurgia, verificar exposicao a agentes nocivos via PPP",
    },
    "OPERADOR DE EMPILHADEIRA": {
        "categoria": "Operador de Empilhadeira",
        "agentes_provaveis": ["RUIDO", "VIBRACOES"],
        "probabilidade": "MEDIA",
        "fundamentacao": "Decreto 3.048/99 Anexo IV - ruido (2.0.1), vibracoes (2.0.5); periculosidade por inflamaveis em alguns contextos",
    },
}


# =============================================================================
# FUNCAO PRINCIPAL DE VERIFICACAO
# =============================================================================

def verificar_possivel_especial(
    empregador_nome: str,
    empregador_cnpj: Optional[str] = None,
) -> dict:
    """
    Verifica se o empregador esta associado a atividades que comumente
    geram direito a aposentadoria especial ou conversao de tempo especial.

    Analisa o nome do empregador contra padroes conhecidos de industrias
    com exposicao a agentes nocivos (fisicos, quimicos, biologicos).

    Args:
        empregador_nome: Razao social ou nome fantasia do empregador
        empregador_cnpj: CNPJ do empregador (para futura consulta de CNAE)

    Returns:
        dict com:
            - possivel_especial (bool): se ha indicios de atividade especial
            - probabilidade (str): ALTA, MEDIA ou BAIXA
            - agentes_provaveis (list): agentes nocivos provaveis
            - fundamentacao (str): base legal aplicavel
            - recomendacao (str): proximos passos sugeridos
            - padroes_encontrados (list): padroes que deram match
            - fatores_conversao (dict): fatores para conversao de tempo
    """
    if not empregador_nome:
        return {
            "possivel_especial": False,
            "probabilidade": "BAIXA",
            "agentes_provaveis": [],
            "fundamentacao": "",
            "recomendacao": "Nome do empregador nao informado. Verificar CNIS ou CTPS.",
            "padroes_encontrados": [],
            "fatores_conversao": FATORES_CONVERSAO[25],
        }

    nome_upper = empregador_nome.upper().strip()
    # Normalizar acentos comuns em razoes sociais
    nome_normalizado = (
        nome_upper
        .replace("Á", "A").replace("À", "A").replace("Ã", "A").replace("Â", "A")
        .replace("É", "E").replace("Ê", "E")
        .replace("Í", "I")
        .replace("Ó", "O").replace("Ô", "O").replace("Õ", "O")
        .replace("Ú", "U").replace("Ü", "U")
        .replace("Ç", "C")
    )

    matches = []
    todos_agentes = set()
    todas_fundamentacoes = []
    maior_probabilidade = "BAIXA"

    # Hierarquia de probabilidades para comparacao
    prob_ordem = {"ALTA": 3, "MEDIA": 2, "BAIXA": 1}

    # Verificar cada padrao contra o nome do empregador
    for padrao, info in PADROES_EMPREGADOR.items():
        padrao_normalizado = (
            padrao.upper()
            .replace("Á", "A").replace("À", "A").replace("Ã", "A").replace("Â", "A")
            .replace("É", "E").replace("Ê", "E")
            .replace("Í", "I")
            .replace("Ó", "O").replace("Ô", "O").replace("Õ", "O")
            .replace("Ú", "U").replace("Ü", "U")
            .replace("Ç", "C")
        )

        # Busca por substring ou palavra inteira
        # Usar regex para evitar matches parciais indesejados em palavras curtas
        if len(padrao_normalizado) <= 4:
            # Para padroes curtos, exigir que seja palavra inteira
            pattern = r'\b' + re.escape(padrao_normalizado) + r'\b'
            if re.search(pattern, nome_normalizado):
                matches.append({
                    "padrao": padrao,
                    "categoria": info["categoria"],
                    "probabilidade": info["probabilidade"],
                })
                todos_agentes.update(info["agentes_provaveis"])
                todas_fundamentacoes.append(info["fundamentacao"])
                if prob_ordem.get(info["probabilidade"], 0) > prob_ordem.get(maior_probabilidade, 0):
                    maior_probabilidade = info["probabilidade"]
        else:
            if padrao_normalizado in nome_normalizado:
                matches.append({
                    "padrao": padrao,
                    "categoria": info["categoria"],
                    "probabilidade": info["probabilidade"],
                })
                todos_agentes.update(info["agentes_provaveis"])
                todas_fundamentacoes.append(info["fundamentacao"])
                if prob_ordem.get(info["probabilidade"], 0) > prob_ordem.get(maior_probabilidade, 0):
                    maior_probabilidade = info["probabilidade"]

    possivel_especial = len(matches) > 0

    # Montar lista de agentes provaveis com descricoes
    agentes_detalhados = []
    todos_dicts = {**AGENTES_FISICOS, **AGENTES_QUIMICOS, **AGENTES_BIOLOGICOS}
    for agente_key in sorted(todos_agentes):
        if agente_key in todos_dicts:
            agentes_detalhados.append({
                "codigo": agente_key,
                "descricao": todos_dicts[agente_key]["descricao"],
                "codigo_anexo_iv": todos_dicts[agente_key].get("codigo_anexo_iv", "N/A"),
            })
        else:
            agentes_detalhados.append({
                "codigo": agente_key,
                "descricao": agente_key,
                "codigo_anexo_iv": "N/A",
            })

    # Determinar aposentadoria especial mais favoravel (menor tempo)
    anos_especial = 25  # padrao
    for agente_key in todos_agentes:
        if agente_key in todos_dicts:
            anos = todos_dicts[agente_key].get("aposentadoria_especial_anos", 25)
            if anos < anos_especial:
                anos_especial = anos

    # Montar fundamentacao consolidada
    fundamentacao_unica = "; ".join(list(dict.fromkeys(todas_fundamentacoes)))

    # Montar recomendacao
    if possivel_especial and maior_probabilidade == "ALTA":
        recomendacao = (
            "ALTA probabilidade de atividade especial. "
            "Solicitar PPP (Perfil Profissiografico Previdenciario) ao empregador. "
            "Verificar LTCAT (Laudo Tecnico das Condicoes Ambientais de Trabalho). "
            "Para periodos ate 28/04/1995, possivel enquadramento por categoria profissional "
            "(Decretos 53.831/64 e 83.080/79). "
            "Para periodos apos 28/04/1995, necessaria comprovacao de exposicao efetiva "
            "a agentes nocivos mediante PPP."
        )
    elif possivel_especial and maior_probabilidade == "MEDIA":
        recomendacao = (
            "MEDIA probabilidade de atividade especial. "
            "Depende da funcao efetivamente exercida e do setor de trabalho dentro da empresa. "
            "Solicitar PPP e verificar descricao das atividades. "
            "Nem todos os trabalhadores dessas empresas tem direito - "
            "e necessario comprovar exposicao habitual e permanente."
        )
    elif possivel_especial and maior_probabilidade == "BAIXA":
        recomendacao = (
            "BAIXA probabilidade de atividade especial, mas nao pode ser descartada. "
            "Verificar a funcao exercida e solicitar PPP caso haja indicios "
            "de exposicao a agentes nocivos. "
            "Considerar que algumas funcoes especificas dentro da empresa podem ter exposicao."
        )
    else:
        recomendacao = (
            "Nenhum padrao de atividade especial identificado pelo nome do empregador. "
            "Isso NAO significa que nao ha atividade especial - apenas que o nome da empresa "
            "nao corresponde a padroes conhecidos. "
            "Verificar a funcao exercida, o CNAE da empresa e solicitar PPP se houver "
            "qualquer indicio de exposicao a agentes nocivos (ruido, produtos quimicos, "
            "agentes biologicos, etc.)."
        )

    # Informacao sobre CNPJ (para futura integracao com consulta de CNAE)
    observacao_cnpj = ""
    if empregador_cnpj:
        cnpj_limpo = re.sub(r'[^0-9]', '', empregador_cnpj)
        if len(cnpj_limpo) == 14:
            observacao_cnpj = (
                f"CNPJ {empregador_cnpj} informado. "
                "Para analise mais precisa, consultar CNAE principal na Receita Federal "
                "e cruzar com a tabela de CNAEs de risco."
            )
        else:
            observacao_cnpj = "CNPJ informado com formato invalido."

    return {
        "possivel_especial": possivel_especial,
        "probabilidade": maior_probabilidade if possivel_especial else "BAIXA",
        "agentes_provaveis": agentes_detalhados,
        "fundamentacao": fundamentacao_unica,
        "recomendacao": recomendacao,
        "padroes_encontrados": matches,
        "fatores_conversao": FATORES_CONVERSAO.get(anos_especial, FATORES_CONVERSAO[25]),
        "aposentadoria_especial_anos": anos_especial,
        "observacao_cnpj": observacao_cnpj,
    }


def consultar_cnae_especial(cnae: str) -> Optional[dict]:
    """
    Consulta se um codigo CNAE esta mapeado como atividade de risco.

    Args:
        cnae: Codigo CNAE (divisao, grupo ou classe). Ex: "24", "2411", "08"

    Returns:
        dict com informacoes do CNAE ou None se nao encontrado.
    """
    cnae_limpo = cnae.strip().replace(".", "").replace("-", "").replace("/", "")

    # Tentar match exato primeiro
    if cnae_limpo in CNAE_ATIVIDADES_ESPECIAIS:
        info = CNAE_ATIVIDADES_ESPECIAIS[cnae_limpo].copy()
        info["cnae"] = cnae_limpo

        # Enriquecer com descricao dos agentes
        todos_dicts = {**AGENTES_FISICOS, **AGENTES_QUIMICOS, **AGENTES_BIOLOGICOS}
        agentes_detalhados = []
        for agente_key in info.get("agentes_provaveis", []):
            if agente_key in todos_dicts:
                agentes_detalhados.append({
                    "codigo": agente_key,
                    "descricao": todos_dicts[agente_key]["descricao"],
                })
            else:
                agentes_detalhados.append({"codigo": agente_key, "descricao": agente_key})
        info["agentes_detalhados"] = agentes_detalhados
        info["fatores_conversao"] = FATORES_CONVERSAO.get(
            info.get("aposentadoria_especial_anos", 25),
            FATORES_CONVERSAO[25],
        )
        return info

    # Tentar match por divisao (2 primeiros digitos)
    if len(cnae_limpo) > 2:
        divisao = cnae_limpo[:2]
        if divisao in CNAE_ATIVIDADES_ESPECIAIS:
            info = CNAE_ATIVIDADES_ESPECIAIS[divisao].copy()
            info["cnae"] = cnae_limpo
            info["match_tipo"] = "divisao"
            info["fatores_conversao"] = FATORES_CONVERSAO.get(
                info.get("aposentadoria_especial_anos", 25),
                FATORES_CONVERSAO[25],
            )
            return info

    return None


def converter_tempo_especial(
    dias_especiais: int,
    sexo: str = "masculino",
    anos_especial: int = 25,
) -> dict:
    """
    Converte tempo de atividade especial em tempo de atividade comum.

    Args:
        dias_especiais: Quantidade de dias trabalhados em atividade especial
        sexo: 'masculino' ou 'feminino'
        anos_especial: Tempo para aposentadoria especial (15, 20 ou 25 anos)

    Returns:
        dict com dias originais, fator aplicado, dias convertidos e diferenca
    """
    sexo_norm = sexo.lower().strip()
    if sexo_norm not in ("masculino", "feminino"):
        sexo_norm = "masculino"

    if anos_especial not in FATORES_CONVERSAO:
        anos_especial = 25

    fator = FATORES_CONVERSAO[anos_especial][sexo_norm]
    dias_convertidos = round(dias_especiais * fator)
    diferenca = dias_convertidos - dias_especiais

    return {
        "dias_especiais": dias_especiais,
        "sexo": sexo_norm,
        "anos_especial": anos_especial,
        "fator_conversao": fator,
        "dias_convertidos": dias_convertidos,
        "dias_acrescidos": diferenca,
        "fundamentacao": (
            f"Art. 70 do Decreto 3.048/99 - Fator de conversao {fator} "
            f"({sexo_norm}, {anos_especial} anos especial para tempo comum)"
        ),
    }


def listar_todos_padroes() -> list:
    """Retorna lista de todos os padroes de empregador cadastrados."""
    resultado = []
    for padrao, info in sorted(PADROES_EMPREGADOR.items()):
        resultado.append({
            "padrao": padrao,
            "categoria": info["categoria"],
            "probabilidade": info["probabilidade"],
            "quantidade_agentes": len(info["agentes_provaveis"]),
        })
    return resultado


def listar_todos_cnaes() -> list:
    """Retorna lista de todos os CNAEs mapeados como atividade de risco."""
    resultado = []
    for cnae, info in sorted(CNAE_ATIVIDADES_ESPECIAIS.items()):
        resultado.append({
            "cnae": cnae,
            "descricao": info["descricao"],
            "probabilidade": info["probabilidade"],
            "quantidade_agentes": len(info["agentes_provaveis"]),
            "aposentadoria_especial_anos": info.get("aposentadoria_especial_anos", 25),
        })
    return resultado


# =============================================================================
# EXECUCAO DIRETA PARA TESTE
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("MODULO DE ATIVIDADE ESPECIAL - TESTE")
    print("=" * 70)

    exemplos = [
        "METALURGICA SAO PAULO LTDA",
        "HOSPITAL MUNICIPAL DE GUARULHOS",
        "AUTO POSTO BANDEIRANTES LTDA",
        "FRIGORIFICO BOM BIFE S/A",
        "MINERACAO VALE DO RIO DOCE",
        "CIA SIDERURGICA NACIONAL",
        "LABORATORIO DE ANALISES CLINICAS SANTA LUCIA",
        "CONSTRUCAO E ENGENHARIA BETA LTDA",
        "QUIMICA INDUSTRIAL ALFA S/A",
        "SUPERMERCADO BOM PRECO LTDA",
        "EMPRESA DE SANEAMENTO BASICO DO ESTADO",
        "CURTUME CENTRAL LTDA",
        "ETERNIT S/A",
        "SERRARIA TRES IRMAOS LTDA",
    ]

    for nome in exemplos:
        resultado = verificar_possivel_especial(nome)
        status = "SIM" if resultado["possivel_especial"] else "NAO"
        prob = resultado["probabilidade"]
        n_agentes = len(resultado["agentes_provaveis"])
        padroes = [m["padrao"] for m in resultado["padroes_encontrados"]]

        print(f"\n{'─' * 70}")
        print(f"Empregador: {nome}")
        print(f"Possivel especial: {status} | Probabilidade: {prob} | Agentes: {n_agentes}")
        if padroes:
            print(f"Padroes: {', '.join(padroes)}")

    print(f"\n{'=' * 70}")
    print(f"Total de padroes de empregador: {len(PADROES_EMPREGADOR)}")
    print(f"Total de CNAEs mapeados: {len(CNAE_ATIVIDADES_ESPECIAIS)}")
    print(f"Total de agentes fisicos: {len(AGENTES_FISICOS)}")
    print(f"Total de agentes quimicos: {len(AGENTES_QUIMICOS)}")
    print(f"Total de agentes biologicos: {len(AGENTES_BIOLOGICOS)}")
