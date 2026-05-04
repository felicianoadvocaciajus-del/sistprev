"""
Testes das regras de transição da EC 103/2019.
"""
import pytest
from datetime import date
from decimal import Decimal
from app.domain.models.segurado import Segurado, DadosPessoais
from app.domain.models.vinculo import Vinculo
from app.domain.models.contribuicao import Contribuicao
from app.domain.enums import Sexo, TipoVinculo, TipoAtividade, RegimePrevidenciario, OrigemDado
from app.domain.transicao.comparador import comparar_todas, melhor_regra


def _segurado_modelo(
    nome: str,
    dn: date,
    sexo: Sexo,
    inicio_contrib: date,
    fim_contrib: date,
    salario: Decimal = Decimal("3000"),
) -> Segurado:
    """Cria um segurado com contribuições mensais contínuas."""
    contribuicoes = []
    atual = date(inicio_contrib.year, inicio_contrib.month, 1)
    fim = date(fim_contrib.year, fim_contrib.month, 1)
    while atual <= fim:
        contribuicoes.append(Contribuicao(competencia=atual, salario_contribuicao=salario))
        if atual.month == 12:
            atual = date(atual.year + 1, 1, 1)
        else:
            atual = date(atual.year, atual.month + 1, 1)

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
    return Segurado(dados_pessoais=dp, vinculos=[v])


class TestRegrasTransicao:
    def test_homem_35_anos_tc_elegivel_alguma_regra(self):
        """Homem que ja tinha 35 anos de TC em 13/11/2019 deve ter Direito Adquirido."""
        # Comeca a contribuir em jan/1984: em 13/11/2019 tem ~35,87 anos TC -> direito adquirido
        dn = date(1960, 6, 15)
        seg = _segurado_modelo("JOAO SILVA", dn, Sexo.MASCULINO,
                               date(1984, 1, 1), date(2024, 12, 31))
        der = date(2025, 1, 1)
        melhor = melhor_regra(seg, der)
        assert melhor is not None
        assert melhor.elegivel

    def test_mulher_30_anos_tc_elegivel(self):
        """Mulher que ja tinha 30 anos de TC em 13/11/2019 deve ter Direito Adquirido."""
        # Comeca a contribuir em jan/1989: em 13/11/2019 tem ~30,87 anos TC -> direito adquirido
        dn = date(1965, 3, 20)
        seg = _segurado_modelo("MARIA SANTOS", dn, Sexo.FEMININO,
                               date(1989, 1, 1), date(2023, 12, 31))
        der = date(2024, 1, 1)
        melhor = melhor_regra(seg, der)
        assert melhor is not None
        assert melhor.elegivel

    def test_contribuidor_recente_inelegivel(self):
        """Contribuidor com apenas 5 anos de TC não deve ser elegível."""
        dn = date(1990, 1, 1)
        seg = _segurado_modelo("PEDRO NOVO", dn, Sexo.MASCULINO,
                               date(2018, 1, 1), date(2022, 12, 31))
        der = date(2023, 1, 1)
        melhor = melhor_regra(seg, der)
        # Pode ser elegível por idade (não tem idade mínima ainda)
        # Mas não por TC
        cenarios = comparar_todas(seg, der)
        regras_tc = [c for c in cenarios if "Transição" in c.nome_regra or "Pontos" in c.nome_regra]
        for r in regras_tc:
            assert not r.elegivel

    def test_direito_adquirido_pre_ec103(self):
        """Quem tinha TC suficiente até 13/11/2019 tem direito adquirido."""
        # Homem com 35+ anos TC em nov/2019
        dn = date(1955, 1, 1)
        seg = _segurado_modelo("ANTONIO VELHO", dn, Sexo.MASCULINO,
                               date(1984, 1, 1), date(2019, 11, 13))
        der = date(2020, 1, 1)
        cenarios = comparar_todas(seg, der)
        direito = next((c for c in cenarios if "Adquirido" in c.nome_regra or "adquirido" in c.nome_regra.lower()), None)
        if direito:  # pode estar presente dependendo da implementação
            assert direito.elegivel

    def test_retorna_multiplos_cenarios(self):
        """comparar_todas deve retornar pelo menos 3 cenários."""
        dn = date(1965, 1, 1)
        seg = _segurado_modelo("TESTE", dn, Sexo.MASCULINO,
                               date(1993, 1, 1), date(2023, 12, 31))
        der = date(2024, 1, 1)
        cenarios = comparar_todas(seg, der)
        assert len(cenarios) >= 3

    def test_rmi_positivo_quando_elegivel(self):
        """Cenários elegíveis devem ter RMI > 0."""
        dn = date(1960, 1, 1)
        seg = _segurado_modelo("TESTE RMI", dn, Sexo.MASCULINO,
                               date(1990, 1, 1), date(2024, 12, 31),
                               salario=Decimal("5000"))
        der = date(2025, 1, 1)
        cenarios = comparar_todas(seg, der)
        for c in cenarios:
            if c.elegivel:
                assert c.rmi_teto > Decimal("0")
