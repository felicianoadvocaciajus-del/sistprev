"""Teste diagnóstico: carência da Dona Rosa."""
import sys
sys.path.insert(0, r"C:\Users\Administrador\Documents\Documents\previdenciario")

from datetime import date
from backend.app.parsers.cnis.parser import parsear_cnis_pdf
from backend.app.domain.tempo.contagem import calcular_carencia, calcular_tempo_contribuicao

# Tentar novo CNIS primeiro, senão usar o antigo
import os
novo = r"C:\Users\Administrador\Documents\DOCUMENTOS_ORGANIZADOS\Maria Rosa de Toledo\cnis rosa.pdf"
resultado = parsear_cnis_pdf(novo)
seg = resultado.segurado

der = date(2026, 4, 5)  # DER da screenshot

print(f"=== DIAGNÓSTICO CARÊNCIA - DER {der} ===")
print(f"Segurado: {seg.dados_pessoais.nome}")
print(f"Vínculos: {len(seg.vinculos)}")
print(f"Benefícios anteriores: {len(seg.beneficios_anteriores)}")

# Carência total
carencia = calcular_carencia(seg.vinculos, der)
print(f"\nCarência total: {carencia} meses (precisa 180)")
print(f"Faltam: {max(0, 180 - carencia)} meses = {max(0, 180 - carencia) / 12:.1f} anos")

# TC total
tc = calcular_tempo_contribuicao(seg.vinculos, der, seg.dados_pessoais.sexo,
                                  beneficios_anteriores=seg.beneficios_anteriores)
print(f"\nTC: {tc.anos}a {tc.meses_restantes}m {tc.dias_restantes}d")

# Detalhar carência por vínculo
print(f"\n=== CARÊNCIA POR VÍNCULO ===")
from backend.app.domain.enums import TipoVinculo, RegimePrevidenciario
EMPREGADO_TIPOS = {TipoVinculo.EMPREGADO, TipoVinculo.EMPREGADO_DOMESTICO, TipoVinculo.TRABALHADOR_AVULSO}

total_check = 0
for i, v in enumerate(seg.vinculos):
    if v.tipo_vinculo in EMPREGADO_TIPOS:
        # Conta meses do período
        inicio = v.data_inicio
        fim = min(v.data_fim or der, der)
        comp = date(inicio.year, inicio.month, 1)
        fim_comp = date(fim.year, fim.month, 1)
        meses = 0
        while comp <= fim_comp:
            meses += 1
            if comp.month == 12:
                comp = date(comp.year + 1, 1, 1)
            else:
                comp = date(comp.year, comp.month + 1, 1)
        print(f"  {i+1}. {v.tipo_vinculo.name} - {v.empregador_nome}: {meses} meses (período {v.data_inicio} a {v.data_fim})")
        total_check += meses
    else:
        # Conta contribuições válidas
        validas = [c for c in v.contribuicoes if c.competencia <= der and c.valida_carencia]
        invalidas = [c for c in v.contribuicoes if c.competencia <= der and not c.valida_carencia]
        print(f"  {i+1}. {v.tipo_vinculo.name} - {v.empregador_nome}: {len(validas)} válidas, {len(invalidas)} inválidas")
        if invalidas:
            for c in invalidas:
                print(f"      INVÁLIDA: {c.competencia.strftime('%m/%Y')} - {c.observacao}")
        total_check += len(validas)

print(f"\nTotal verificação manual: {total_check} meses")
print(f"Carência calculada: {carencia} meses")
if total_check != carencia:
    print(f"⚠️ DIVERGÊNCIA: manual={total_check} vs sistema={carencia}")
