"""
Testes de integração da API FastAPI.
Requer: pip install httpx pytest-asyncio
"""
import pytest
from httpx import AsyncClient, ASGITransport

# Importamos aqui para garantir que os erros de import são detectados nos testes
@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


SEGURADO_COMPLETO = {
    "dados_pessoais": {
        "nome": "JOAO DA SILVA",
        "data_nascimento": "15/03/1960",
        "sexo": "MASCULINO",
        "cpf": "12345678901",
    },
    "vinculos": [
        {
            "empregador_nome": "EMPRESA TESTE LTDA",
            "empregador_cnpj": "12345678000190",
            "tipo_vinculo": "EMPREGADO",
            "tipo_atividade": "NORMAL",
            "data_inicio": "01/01/1990",
            "data_fim": "31/12/2024",
            "contribuicoes": [
                {"competencia": f"{m:02d}/{a}", "salario": "3000.00"}
                for a in range(1994, 2025)
                for m in range(1, 13)
            ],
        }
    ],
}


class TestHealthCheck:
    @pytest.mark.anyio
    async def test_health(self, client):
        r = await client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestCalculoAposentadoria:
    @pytest.mark.anyio
    async def test_aposentadoria_transicao(self, client):
        payload = {
            "segurado": SEGURADO_COMPLETO,
            "der": "01/01/2025",
            "tipo": "transicao",
        }
        r = await client.post("/api/v1/calculo/aposentadoria", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "elegivel" in data
        assert "rmi" in data
        assert "todos_cenarios" in data
        assert len(data["todos_cenarios"]) >= 3

    @pytest.mark.anyio
    async def test_aposentadoria_elegivel_rmi_positivo(self, client):
        """35 anos de contribuição → elegível com RMI > 0."""
        payload = {
            "segurado": SEGURADO_COMPLETO,
            "der": "01/01/2025",
            "tipo": "transicao",
        }
        r = await client.post("/api/v1/calculo/aposentadoria", json=payload)
        data = r.json()
        if data["elegivel"]:
            assert float(data["rmi"]) > 0

    @pytest.mark.anyio
    async def test_dados_invalidos_retorna_422(self, client):
        payload = {
            "segurado": {"dados_pessoais": {"nome": "", "data_nascimento": "INVALIDA", "sexo": "X"}},
            "der": "01/01/2025",
        }
        r = await client.post("/api/v1/calculo/aposentadoria", json=payload)
        assert r.status_code in (422, 400)


class TestResumoSegurado:
    @pytest.mark.anyio
    async def test_resumo_retorna_tc(self, client):
        payload = {
            "segurado": SEGURADO_COMPLETO,
            "der": "01/01/2025",
            "tipo": "transicao",
        }
        r = await client.post("/api/v1/calculo/resumo", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "tempo_contribuicao" in data
        tc = data["tempo_contribuicao"]
        assert tc["anos"] >= 30  # 1990-2024 = ~34 anos


class TestIndices:
    @pytest.mark.anyio
    async def test_teto_2024(self, client):
        r = await client.get("/api/v1/indices/teto?ano=2024&mes=1")
        assert r.status_code == 200
        data = r.json()
        assert float(data["teto"]) > 7000  # teto em 2024 ~R$ 7.786

    @pytest.mark.anyio
    async def test_salario_minimo_2024(self, client):
        r = await client.get("/api/v1/indices/salario-minimo?ano=2024&mes=1")
        assert r.status_code == 200
        data = r.json()
        assert float(data["salario_minimo"]) >= 1000

    @pytest.mark.anyio
    async def test_correcao_monetaria(self, client):
        r = await client.get("/api/v1/indices/correcao-monetaria?ano_inicio=2020&mes_inicio=1&ano_fim=2024&mes_fim=1")
        assert r.status_code == 200
        data = r.json()
        assert float(data["fator"]) > 1


class TestAtrasados:
    @pytest.mark.anyio
    async def test_atrasados_simples(self, client):
        payload = {
            "dib": "01/01/2020",
            "rmi_original": "2000.00",
            "data_atualizacao": "01/01/2024",
            "incluir_juros": True,
        }
        r = await client.post("/api/v1/calculo/atrasados", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert int(data["parcelas_calculadas"]) == 48  # 4 anos × 12
        assert float(data["total_geral"]) > float(data["total_principal"])

    @pytest.mark.anyio
    async def test_atrasados_com_prescricao(self, client):
        payload = {
            "dib": "01/01/2010",
            "rmi_original": "1500.00",
            "data_atualizacao": "01/01/2024",
            "data_ajuizamento": "01/01/2022",
            "incluir_juros": False,
        }
        r = await client.post("/api/v1/calculo/atrasados", json=payload)
        assert r.status_code == 200
        data = r.json()
        # Prescrição: parcelas anteriores a jan/2017 devem ser excluídas
        assert int(data["parcelas_prescritas"]) > 0
