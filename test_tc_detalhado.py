"""
Teste detalhado: verificar períodos contados para Dona Rosa.
"""
import sys
sys.path.insert(0, r"C:\Users\Administrador\Documents\Documents\previdenciario")

from datetime import date
from backend.app.parsers.cnis.parser import parsear_cnis_pdf
from backend.app.domain.tempo.contagem import (
    calcular_tempo_contribuicao,
    _periodos_auxilio_doenca_intercalados
)

# Parse CNIS
resultado = parsear_cnis_pdf(r"C:\Users\Administrador\Documents\DOCUMENTOS_ORGANIZADOS\Maria Rosa de Toledo\cnis rosa.pdf")

seg = resultado.segurado
der = date(2024, 9, 12)

print(f"Segurado: {seg.dados_pessoais.nome}")
print(f"Sexo: {seg.dados_pessoais.sexo}")
print(f"DER: {der}")
print(f"Vinculos: {len(seg.vinculos)}")
print(f"Beneficios anteriores: {len(seg.beneficios_anteriores)}")

# Listar todos os vinculos
print("\n=== VINCULOS ===")
for i, v in enumerate(seg.vinculos):
    n_contrib = len(v.contribuicoes)
    print(f"  {i+1}. {v.tipo_vinculo.name} - {v.empregador_nome or 'N/A'}")
    print(f"     {v.data_inicio} a {v.data_fim or 'atual'} ({n_contrib} contribs)")

# Listar beneficios
print("\n=== BENEFICIOS ANTERIORES ===")
for b in seg.beneficios_anteriores:
    dcb_str = b.dcb.strftime('%d/%m/%Y') if b.dcb else 'ATIVO'
    dias = (b.dcb - b.dib).days if b.dcb else 'N/A'
    print(f"  {b.especie.value} DIB={b.dib.strftime('%d/%m/%Y')} DCB={dcb_str} ({dias} dias)")

# Calcular periodos de auxilio intercalados
print("\n=== PERIODOS B31 INTERCALADOS ===")
periodos_b31 = _periodos_auxilio_doenca_intercalados(
    seg.beneficios_anteriores, seg.vinculos, der
)
total_b31_dias = 0
for p in periodos_b31:
    print(f"  {p.data_inicio} a {p.data_fim} = {p.dias} dias | {p.observacao}")
    total_b31_dias += p.dias
print(f"  TOTAL B31: {total_b31_dias} dias = {total_b31_dias/365.25:.1f} anos")

# Calcular TC completo
print("\n=== TC COMPLETO ===")
tc = calcular_tempo_contribuicao(
    seg.vinculos, der, seg.dados_pessoais.sexo,
    beneficios_anteriores=seg.beneficios_anteriores,
)
print(f"TC: {tc.anos}a {tc.meses_restantes}m {tc.dias_restantes}d")
print(f"TC total dias: {tc.dias_total}")
print(f"TC anos decimal: {tc.anos_decimal}")

# Comparar com Previus
print("\n=== COMPARACAO PREVIUS (14a 2m 14d = 5189 dias) ===")
previus_dias = 14*365 + 2*30 + 14  # ~5184 dias
print(f"Previus aprox: {previus_dias} dias")
print(f"SistPrev: {tc.dias_total} dias")
print(f"Diferenca: {previus_dias - tc.dias_total} dias = {(previus_dias - tc.dias_total)/30:.1f} meses")
