"""Substitui INDICES_INPC no correcao_monetaria.py com valores oficiais SIDRA."""
import re

ARQUIVO = r'C:\Users\Administrador\OneDrive\Documentos\Documents\previdenciario\backend\app\domain\indices\correcao_monetaria.py'
NOVOS = r'C:\Users\Administrador\OneDrive\Documentos\Documents\previdenciario\backend\_inpc_oficial.txt'

with open(ARQUIVO, 'r', encoding='utf-8') as f:
    conteudo = f.read()

with open(NOVOS, 'r', encoding='utf-8') as f:
    novos_valores = f.read()

# Encontrar o bloco INDICES_INPC e substituir
# Padrao: "INDICES_INPC: ...= {\n" ... "\n}\n"
inicio_marker = "INDICES_INPC: Dict[Tuple[int, int], Decimal] = {"
fim_marker = "\n}\n\n\n# ─────────────────────────────────────────────────────────────────────────────\n# CADEIA UNIFICADA"

pos_ini = conteudo.find(inicio_marker)
pos_fim = conteudo.find(fim_marker, pos_ini)

if pos_ini == -1 or pos_fim == -1:
    print("ERRO: nao encontrei os marcadores")
    print(f"  inicio: {pos_ini}, fim: {pos_fim}")
else:
    novo_conteudo = (
        conteudo[:pos_ini]
        + inicio_marker + "\n"
        + "    # ATUALIZADO 2026-04-27 com valores OFICIAIS IBGE/SIDRA Tabela 1736\n"
        + "    # Fonte: API publica https://servicodados.ibge.gov.br/api/v3/agregados/1736\n"
        + "    # Periodo: jul/1994 a mar/2026 (381 valores oficiais)\n"
        + novos_valores + "\n"
        + conteudo[pos_fim:]
    )
    with open(ARQUIVO, 'w', encoding='utf-8') as f:
        f.write(novo_conteudo)
    print(f"OK: substituido. Bloco INPC tinha {pos_fim - pos_ini} chars, agora {len(novos_valores) + len(inicio_marker)} chars")
