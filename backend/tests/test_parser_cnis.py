"""
Testes do parser do CNIS.
Usa texto simulado (sem PDF real) para verificar extração de campos.
"""
import pytest
from app.parsers.cnis.parser import parsear_cnis_texto


CNIS_SIMULADO = """
MINISTÉRIO DA PREVIDÊNCIA SOCIAL
CADASTRO NACIONAL DE INFORMAÇÕES SOCIAIS — CNIS

Nome: MARIA DE FATIMA SOUZA
CPF: 123.456.789-09
Data de Nascimento: 15/07/1968
Sexo: Feminino

Seq. 1
Empresa: COMERCIO VAREJISTA LTDA
CNPJ: 12.345.678/0001-90
Início: 01/03/1995
Fim: 28/02/2005

Comp.     Remuneração
03/1995   800,00
04/1995   800,00
05/1995   850,00
06/1995   850,00

Seq. 2
Empresa: INDUSTRIA TEXTIL SA
CNPJ: 98.765.432/0001-11
Início: 01/06/2006
Fim: 31/12/2019

Comp.     Remuneração
06/2006   1.200,00
07/2006   1.200,00
08/2006   1.300,00
"""


class TestParserCNIS:
    def test_extrai_nome(self):
        r = parsear_cnis_texto(CNIS_SIMULADO)
        assert r.segurado is not None
        assert "MARIA" in r.segurado.dados_pessoais.nome.upper()

    def test_extrai_data_nascimento(self):
        r = parsear_cnis_texto(CNIS_SIMULADO)
        from datetime import date
        assert r.segurado.dados_pessoais.data_nascimento == date(1968, 7, 15)

    def test_extrai_sexo_feminino(self):
        r = parsear_cnis_texto(CNIS_SIMULADO)
        from app.domain.enums import Sexo
        assert r.segurado.dados_pessoais.sexo == Sexo.FEMININO

    def test_extrai_cpf(self):
        r = parsear_cnis_texto(CNIS_SIMULADO)
        assert r.segurado.dados_pessoais.cpf == "12345678909"

    def test_sucesso_true(self):
        r = parsear_cnis_texto(CNIS_SIMULADO)
        assert r.sucesso is True

    def test_extrai_vinculos(self):
        r = parsear_cnis_texto(CNIS_SIMULADO)
        assert len(r.vinculos) >= 1

    def test_extrai_contribuicoes(self):
        r = parsear_cnis_texto(CNIS_SIMULADO)
        total_contribs = sum(len(v.contribuicoes) for v in r.vinculos)
        assert total_contribs >= 3


CNIS_SEM_NOME = """
CPF: 111.222.333-44
Data de Nascimento: 01/01/1980
"""


class TestParserCNISFalhas:
    def test_sem_nome_retorna_aviso(self):
        r = parsear_cnis_texto(CNIS_SEM_NOME)
        assert r.sucesso is False
        assert len(r.avisos) > 0

    def test_texto_vazio_retorna_erro_ou_falha(self):
        r = parsear_cnis_texto("")
        assert r.sucesso is False
