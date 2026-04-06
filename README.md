# Sistema Previdenciário — SistPrev

Sistema completo de cálculos previdenciários conforme:
- **Lei 8.213/91** (benefícios do RGPS)
- **EC 103/2019** (reforma da previdência)
- **Manual de Cálculos da Justiça Federal — CJF Resolução 963/2025**

---

## Como instalar e iniciar

### 1. Instalar dependências

```bash
cd previdenciario/backend
pip install -r requirements.txt
```

### 2. Iniciar o servidor

```bash
cd previdenciario/backend
uvicorn app.main:app --reload --port 8000
```

### 3. Abrir no navegador

```
http://localhost:8000
```

A documentação interativa da API está em:
```
http://localhost:8000/docs
```

---

## Como usar

### Via interface web (recomendado)

1. **Importar Documentos** — faça upload do CNIS em PDF. O sistema extrai automaticamente nome, CPF, data de nascimento e todos os vínculos com contribuições mensais.

2. **Dados do Segurado** — revise ou complete os dados extraídos. Adicione ou edite vínculos manualmente se necessário.

3. **Calcular Benefício** — selecione o tipo (aposentadoria, auxílio-doença, invalidez, pensão por morte) e a DER. O sistema compara automaticamente **todas as regras de transição** e mostra a mais vantajosa.

4. **Revisões** — analise se há direito à Revisão da Vida Toda (Tema 1.102 STF) ou Revisão do Teto (EC 20/98 e EC 41/03).

5. **Parcelas Atrasadas** — calcule a liquidação de sentença com correção pelo INPC e juros de mora (SELIC após jan/2022).

6. **Relatório Pericial** — gere o relatório técnico em PDF com memória completa de cálculo.

---

## Executar os testes

```bash
cd previdenciario/backend
pytest -v
```

---

## Estrutura do projeto

```
previdenciario/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app
│   │   ├── domain/
│   │   │   ├── constantes.py          # DatasCorte, PONTOS_EC103, etc.
│   │   │   ├── models/                # Segurado, Vinculo, Contribuicao, Resultado
│   │   │   ├── enums/                 # TipoVinculo, Sexo, TipoBeneficio, etc.
│   │   │   ├── indices/               # INPC, teto, salário mínimo, sobrevida
│   │   │   ├── tempo/                 # Contagem de TC e carência
│   │   │   ├── salario/               # PBC — cálculo do salário de benefício
│   │   │   ├── fator_previdenciario.py
│   │   │   ├── beneficios/            # Calculadoras por espécie (B31, B32, B21, etc.)
│   │   │   └── transicao/             # 5 regras EC 103/2019 + comparador
│   │   ├── parsers/
│   │   │   ├── cnis/                  # Parser CNIS PDF
│   │   │   ├── carta_concessao/       # Parser Carta de Concessão PDF
│   │   │   └── ctps/                  # Parser CTPS Digital PDF
│   │   ├── revisoes/
│   │   │   ├── vida_toda.py           # Tema 1.102 STF
│   │   │   ├── revisao_teto.py        # EC 20/98 e EC 41/03
│   │   │   └── liquidacao_sentenca.py # Parcelas atrasadas
│   │   ├── services/                  # Orquestração (CalculoService, UploadService)
│   │   ├── api/
│   │   │   ├── schemas.py             # Pydantic schemas
│   │   │   ├── converters.py          # Domain ↔ Schema
│   │   │   └── routers/               # calculo, upload, indices, relatorio
│   │   └── relatorio/                 # Gerador de relatório HTML/PDF
│   ├── tests/                         # Testes automatizados
│   └── requirements.txt
└── frontend/
    ├── index.html                     # SPA principal
    └── static/
        ├── css/style.css
        └── js/app.js
```

---

## Benefícios calculados

| Código | Benefício | Base Legal |
|--------|-----------|------------|
| B42 | Aposentadoria por Tempo de Contribuição — Transição | EC 103/2019 Art. 15–20 |
| B41 | Aposentadoria por Idade | EC 103/2019 Art. 18 |
| B46 | Aposentadoria Especial (15/20/25 anos) | Lei 8.213/91 Art. 57 |
| B31 | Auxílio por Incapacidade Temporária | Lei 8.213/91 Art. 59 |
| B91 | Auxílio por Incapacidade — Acidentário | Lei 8.213/91 Art. 59 |
| B32 | Aposentadoria por Incapacidade Permanente | Lei 8.213/91 Art. 42 |
| B92 | Aposentadoria por Incapacidade — Acidentária | Lei 8.213/91 Art. 42 |
| B21 | Pensão por Morte | EC 103/2019 Art. 23 |

---

## Regras de Transição EC 103/2019

1. **Art. 15 — Pontos Progressivos**: TC + Idade ≥ pontos crescentes até 2033 (105H/100M)
2. **Art. 16 — Idade Progressiva**: Idade mínima crescente (65H/62M até 2031)
3. **Art. 17 — Pedágio 50%**: Para quem faltava até 2 anos em nov/2019
4. **Art. 20 — Pedágio 100%**: Para quem faltava mais de 2 anos + idade mínima 60H/57M
5. **Direito Adquirido**: Quem já tinha TC suficiente em 13/11/2019

---

## Revisões disponíveis

- **Revisão da Vida Toda** (Tema 1.102 STF): compara método pós-jul/1994 vs. todos os salários
- **Revisão do Teto**: EC 20/98 (R$ 1.200) e EC 41/03 (R$ 2.400) para benefícios antigos
- **Liquidação de Sentença**: parcelas atrasadas com INPC + juros (SELIC após EC 113/2021)
