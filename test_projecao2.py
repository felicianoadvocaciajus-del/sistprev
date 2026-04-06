"""Teste: simular projecao EXATAMENTE como o sistema faz."""
import sys
sys.path.insert(0, r"C:\Users\Administrador\Documents\Documents\previdenciario")

from datetime import date
from decimal import Decimal
from copy import deepcopy
from backend.app.parsers.cnis.parser import parsear_cnis_pdf
from backend.app.domain.tempo.contagem import calcular_carencia
from backend.app.domain.transicao.comparador import comparar_todas
from backend.app.domain.models.vinculo import Vinculo
from backend.app.domain.models.contribuicao import Contribuicao
from backend.app.domain.enums import TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado

resultado = parsear_cnis_pdf(r"C:\Users\Administrador\Documents\DOCUMENTOS_ORGANIZADOS\Maria Rosa de Toledo\cnis rosa.pdf")
seg = resultado.segurado
der_base = date(2026, 4, 5)
sal = Decimal("1518.00")

def avancar_mes(d):
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)

print("=== PROJECAO COM comparar_todas ===")
for n_meses in [72, 74, 75, 76, 77, 78, 80, 85]:
    seg_sim = deepcopy(seg)
    contribuicoes = []
    d = date(2026, 5, 1)
    for i in range(n_meses):
        contribuicoes.append(Contribuicao(
            competencia=date(d.year, d.month, 1),
            salario_contribuicao=sal,
        ))
        d = avancar_mes(d)

    v = Vinculo(
        tipo_vinculo=TipoVinculo.CONTRIBUINTE_INDIVIDUAL,
        regime=RegimePrevidenciario.RGPS,
        tipo_atividade=TipoAtividade.NORMAL,
        empregador_nome="Projecao Futura",
        data_inicio=date(2026, 5, 1),
        data_fim=None,
        contribuicoes=contribuicoes,
        origem=OrigemDado.MANUAL,
    )
    seg_sim.vinculos.append(v)
    der_sim = d

    car = calcular_carencia(seg_sim.vinculos, der_sim)
    cenarios = comparar_todas(seg_sim, der_sim)

    idade_regra = next((c for c in cenarios if "Idade" in c.nome_regra), None)
    if idade_regra:
        anos, meses_r = divmod(n_meses, 12)
        print(f"  +{n_meses:3d}m ({anos}a{meses_r}m) DER={der_sim} Car={car}/180 Elegivel={idade_regra.elegivel}")
    else:
        print(f"  +{n_meses:3d}m -> Regra Idade nao encontrada")
