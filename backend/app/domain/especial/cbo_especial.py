"""
Análise de CBO (Classificação Brasileira de Ocupações) para atividade especial.

Cruza o código CBO com:
- Funções historicamente reconhecidas como especiais
- NRs (Normas Regulamentadoras) aplicáveis
- Decretos 53.831/64 e 83.080/79 (enquadramento por categoria até 28/04/1995)
- Decreto 3.048/99 Anexo IV (agentes nocivos)
"""
from __future__ import annotations
from typing import Optional


# CBO → dados de atividade especial
# Formato: "família CBO" (4 dígitos) ou CBO completo (6 dígitos)
CBO_ESPECIAL = {
    # ── SAÚDE ─────────────────────────────────────────────────────────────────
    "2251": {
        "descricao": "Médicos clínicos",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["MICROORGANISMOS_SAUDE"],
        "nrs": ["NR-32 (Segurança em Serviços de Saúde)"],
        "fundamentacao": "Decreto 53.831/64 cod 1.3.2; Decreto 3.048/99 Anexo IV cod 3.0.1",
    },
    "2252": {
        "descricao": "Médicos em especialidades cirúrgicas",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["MICROORGANISMOS_SAUDE", "RADIACAO_IONIZANTE"],
        "nrs": ["NR-32"],
        "fundamentacao": "Decreto 53.831/64 cod 1.3.2; Decreto 3.048/99 Anexo IV cod 3.0.1",
    },
    "2232": {
        "descricao": "Cirurgiões-dentistas",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["MICROORGANISMOS_SAUDE"],
        "nrs": ["NR-32"],
        "fundamentacao": "Decreto 53.831/64 cod 1.3.2; Decreto 3.048/99 Anexo IV cod 3.0.1",
    },
    "2235": {
        "descricao": "Enfermeiros",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["MICROORGANISMOS_SAUDE"],
        "nrs": ["NR-32"],
        "fundamentacao": "Decreto 53.831/64 cod 1.3.2; Decreto 3.048/99 Anexo IV cod 3.0.1",
    },
    "3222": {
        "descricao": "Técnicos e auxiliares de enfermagem",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["MICROORGANISMOS_SAUDE"],
        "nrs": ["NR-32"],
        "fundamentacao": "Decreto 53.831/64 cod 1.3.2; Decreto 3.048/99 Anexo IV cod 3.0.1",
    },
    "3242": {
        "descricao": "Tecnólogos em radiologia",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["RADIACAO_IONIZANTE"],
        "nrs": ["NR-32"],
        "fundamentacao": "Decreto 53.831/64 cod 1.1.4; Decreto 3.048/99 Anexo IV cod 2.0.3",
    },
    # ── METALURGIA / SOLDAGEM ────────────────────────────────────────────────
    "7243": {
        "descricao": "Soldadores e oxicortadores",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["RUIDO", "FUMOS_METALICOS", "RADIACAO_NAO_IONIZANTE"],
        "nrs": ["NR-18 (Construção)", "NR-12 (Máquinas)", "NR-15 (Insalubridade)"],
        "fundamentacao": "Decreto 53.831/64 cod 2.5.3; Decreto 3.048/99 Anexo IV cod 1.0.17 e 2.0.1",
    },
    "7244": {
        "descricao": "Trabalhadores de caldeiraria e serralheria",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["RUIDO", "FUMOS_METALICOS", "CALOR"],
        "nrs": ["NR-15", "NR-12"],
        "fundamentacao": "Decreto 53.831/64 cod 1.1.6; Decreto 3.048/99 Anexo IV",
    },
    "7211": {
        "descricao": "Ferramenteiros e operadores de máquinas-ferramenta",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["RUIDO", "VIBRACOES", "OLEO_MINERAL"],
        "nrs": ["NR-12", "NR-15"],
        "fundamentacao": "Decreto 53.831/64 cod 1.1.6; Decreto 3.048/99 Anexo IV cod 2.0.1",
    },
    "7214": {
        "descricao": "Operadores de máquinas de usinagem de metais",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["RUIDO", "VIBRACOES", "OLEO_MINERAL"],
        "nrs": ["NR-12", "NR-15"],
        "fundamentacao": "Decreto 53.831/64; Decreto 3.048/99 Anexo IV - torneiros, fresadores",
    },
    "7241": {
        "descricao": "Trabalhadores de fundicão de metais puros e ligas",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["CALOR", "RUIDO", "FUMOS_METALICOS", "SILICA_LIVRE"],
        "nrs": ["NR-15", "NR-14 (Fornos)"],
        "fundamentacao": "Decreto 53.831/64 cod 1.1.6; Decreto 3.048/99 Anexo IV",
    },
    # ── ELETRICIDADE ─────────────────────────────────────────────────────────
    "7321": {
        "descricao": "Eletricistas de manutenção eletroeletrônica",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": [],
        "nrs": ["NR-10 (Segurança em Eletricidade)", "NR-16 (Periculosidade)"],
        "fundamentacao": "Decreto 53.831/64 cod 1.1.8; Lei 7.369/85; Decreto 3.048/99 Anexo IV cod 2.0.3",
    },
    "7311": {
        "descricao": "Montadores e instaladores de equipamentos eletroeletrônicos",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": [],
        "nrs": ["NR-10"],
        "fundamentacao": "Depende de exposição a alta tensão; Lei 7.369/85",
    },
    # ── CONSTRUÇÃO CIVIL ─────────────────────────────────────────────────────
    "7152": {
        "descricao": "Trabalhadores em alvenaria (pedreiros)",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["RUIDO", "SILICA_LIVRE"],
        "nrs": ["NR-18 (Construção)", "NR-15"],
        "fundamentacao": "Decreto 3.048/99 Anexo IV cod 1.0.17 (poeiras); depende do ambiente",
    },
    "7166": {
        "descricao": "Pintores de obras e revestidores de interiores",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["HIDROCARBONETOS", "CHUMBO"],
        "nrs": ["NR-15", "NR-18"],
        "fundamentacao": "Decreto 53.831/64 cod 1.2.11; Decreto 3.048/99 Anexo IV cod 1.0.7 e 1.0.19",
    },
    # ── MINERAÇÃO ────────────────────────────────────────────────────────────
    "7111": {
        "descricao": "Trabalhadores da extração mineral (mineiros)",
        "especial": True, "probabilidade": "ALTA", "anos": 15,
        "agentes": ["RUIDO", "VIBRACOES", "SILICA_LIVRE", "POEIRAS_MINERAIS"],
        "nrs": ["NR-22 (Mineração)"],
        "fundamentacao": "Decreto 53.831/64 cod 2.3.3; Decreto 3.048/99 Anexo IV; aposentadoria especial 15 ou 20 anos",
    },
    # ── MOTORISTAS ───────────────────────────────────────────────────────────
    "7823": {
        "descricao": "Motoristas de ônibus",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["RUIDO", "VIBRACOES"],
        "nrs": ["NR-15"],
        "fundamentacao": "Decreto 53.831/64 cod 2.4.4; enquadramento por categoria até 28/04/1995",
    },
    "7825": {
        "descricao": "Motoristas de caminhão",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["RUIDO", "VIBRACOES"],
        "nrs": ["NR-15", "NR-16 (se transporte de inflamáveis)"],
        "fundamentacao": "STJ REsp 1.306.113/SC; Decreto 53.831/64; periculosidade se inflamáveis",
    },
    # ── QUÍMICA / COMBUSTÍVEIS ───────────────────────────────────────────────
    "5211": {
        "descricao": "Frentistas",
        "especial": True, "probabilidade": "ALTA", "anos": 25,
        "agentes": ["BENZENO", "HIDROCARBONETOS"],
        "nrs": ["NR-16 (Periculosidade)", "NR-20 (Inflamáveis)"],
        "fundamentacao": "Decreto 3.048/99 Anexo IV cod 1.0.3 (benzeno); NR-16 periculosidade",
    },
    # ── SEGURANÇA ────────────────────────────────────────────────────────────
    "5173": {
        "descricao": "Vigilantes e guardas de segurança",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": [],
        "nrs": ["NR-16 (Periculosidade)"],
        "fundamentacao": "Lei 12.740/2012; periculosidade por arma de fogo; Decreto 53.831/64",
    },
    # ── OPERADORES DE MÁQUINAS ───────────────────────────────────────────────
    "7151": {
        "descricao": "Operadores de máquinas de terraplanagem e fundação",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["RUIDO", "VIBRACOES"],
        "nrs": ["NR-11 (Transporte de Materiais)", "NR-12"],
        "fundamentacao": "Decreto 3.048/99 Anexo IV cod 2.0.1 e 2.0.5",
    },
    "7842": {
        "descricao": "Operadores de empilhadeira",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["RUIDO", "VIBRACOES"],
        "nrs": ["NR-11", "NR-12"],
        "fundamentacao": "Decreto 3.048/99 Anexo IV cod 2.0.1 e 2.0.5",
    },
    # ── MECÂNICA ─────────────────────────────────────────────────────────────
    "9131": {
        "descricao": "Mecânicos de manutenção de veículos automotores",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["RUIDO", "OLEO_MINERAL", "HIDROCARBONETOS"],
        "nrs": ["NR-15"],
        "fundamentacao": "Decreto 53.831/64; Decreto 3.048/99 Anexo IV cod 1.0.19",
    },
    "9112": {
        "descricao": "Mecânicos de manutenção de máquinas industriais",
        "especial": True, "probabilidade": "MEDIA", "anos": 25,
        "agentes": ["RUIDO", "OLEO_MINERAL"],
        "nrs": ["NR-12", "NR-15"],
        "fundamentacao": "Decreto 3.048/99 Anexo IV; depende do setor industrial",
    },
}


def analisar_cbo(cbo: str, cargo: str = "") -> Optional[dict]:
    """
    Analisa um código CBO para verificar atividade especial.

    Args:
        cbo: Código CBO (4 ou 6 dígitos)
        cargo: Nome do cargo (complementar)

    Returns:
        Dict com análise ou None se CBO não encontrado
    """
    if not cbo:
        return None

    # Limpar CBO
    cbo_limpo = cbo.strip().replace(".", "").replace("-", "").replace(" ", "")

    # Tentar match exato (6 dígitos)
    info = CBO_ESPECIAL.get(cbo_limpo)

    # Tentar match por família (4 primeiros dígitos)
    if not info and len(cbo_limpo) >= 4:
        info = CBO_ESPECIAL.get(cbo_limpo[:4])

    if not info:
        return {
            "possivel_especial": False,
            "probabilidade": "NENHUMA",
            "descricao_cbo": f"CBO {cbo} — sem mapeamento especial direto",
            "nrs_aplicaveis": [],
            "recomendacao": (
                f"CBO {cbo} não possui mapeamento direto para atividade especial. "
                "Isso NÃO descarta a possibilidade — verificar PPP e condições reais de trabalho."
            ),
        }

    return {
        "possivel_especial": info["especial"],
        "probabilidade": info["probabilidade"],
        "descricao_cbo": f"CBO {cbo} — {info['descricao']}",
        "agentes_provaveis": [{"codigo": a, "descricao": a} for a in info.get("agentes", [])],
        "nrs_aplicaveis": info.get("nrs", []),
        "fundamentacao": info.get("fundamentacao", ""),
        "anos_especial": info.get("anos", 25),
        "fatores_conversao": {},
        "recomendacao": (
            f"CBO {cbo} ({info['descricao']}) — {info['probabilidade']} probabilidade de especialidade. "
            f"NRs aplicáveis: {', '.join(info.get('nrs', []))}. "
            f"Solicitar PPP para confirmar exposição."
        ),
    }
