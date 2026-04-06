"""Teste: simular projeção como o sistema faz."""
import sys
sys.path.insert(0, r"C:\Users\Administrador\Documents\Documents\previdenciario")

from datetime import date
from decimal import Decimal
from copy import deepcopy
from backend.app.parsers.cnis.parser import parsear_cnis_pdf
from backend.app.domain.tempo.contagem import calcular_carencia, calcular_tempo_contribuicao
from backend.app.domain.models.vinculo import Vinculo
from backend.app.domain.models.contribuicao import Contribuicao
from backend.app.domain.enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado

resultado = parsear_cnis_pdf(r"C:\Users\Administrador\Documents\DOCUMENTOS_ORGANIZADOS\Maria Rosa de Toledo\cnis rosa.pdf")
seg = resultado.segurado
der_base = date(2026, 4, 5)
sal = Decimal("1518.00")  # salário mínimo 2025

print("=== SIMULAÇÃO PROJEÇÃO ===")
print(f"Carência atual: {calcular_carencia(seg.vinculos, der_base)}")

# Simular adicionando contribuições futuras mês a mês
for n_meses in [76, 85, 90, 95, 98, 100]:
    seg_sim = deepcopy(seg)

    # Criar contribuições futuras
    contribuicoes = []
    d = date(2026, 5, 1)  # próximo mês após DER
    for i in range(n_meses):
        contribuicoes.append(Contribuicao(
            competencia=date(d.year, d.month, 1),
            salario_contribuicao=sal,
        ))
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)

    v = Vinculo(
        tipo_vinculo=TipoVinculo.CONTRIBUINTE_INDIVIDUAL,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        empregador_nome="Projeção Futura",
        data_inicio=date(2026, 5, 1),
        data_fim=None,
        contribuicoes=contribuicoes,
        origem=OrigemDado.MANUAL,
    )
    seg_sim.vinculos.append(v)

    der_sim = d  # DER na data final
    car = calcular_carencia(seg_sim.vinculos, der_sim)
    tc = calcular_tempo_contribuicao(seg_sim.vinculos, der_sim, seg_sim.dados_pessoais.sexo,
                                      beneficios_anteriores=seg_sim.beneficios_anteriores)

    anos, meses_r = divmod(n_meses, 12)
    elegivel_carencia = car >= 180
    elegivel_tc = tc.anos >= 15 or (tc.anos == 14 and tc.meses_restantes >= 12)

    status_car = "OK" if elegivel_carencia else "NAO"
    print(f"  +{n_meses:3d} meses ({anos}a {meses_r}m) -> DER {der_sim} | Carencia={car:3d}/180 [{status_car}] | TC={tc.anos}a{tc.meses_restantes}m")
