"""
Script de teste: Upload CNIS Dona Rosa e calcular TC.
"""
import requests
import json

BASE = "http://localhost:8000/api/v1"

# 1) Upload CNIS
print("=== UPLOAD CNIS ===")
with open(r"C:\Users\Administrador\Documents\DOCUMENTOS_ORGANIZADOS\Maria Rosa de Toledo\cnis rosa.pdf", "rb") as f:
    resp = requests.post(f"{BASE}/upload/cnis", files={"arquivo": ("cnis rosa.pdf", f, "application/pdf")})

data = resp.json()
print(f"Sucesso: {data['sucesso']}")
print(f"Vinculos: {len(data['segurado']['vinculos'])}")
print(f"Beneficios anteriores: {len(data['segurado'].get('beneficios_anteriores', []))}")

for b in data['segurado'].get('beneficios_anteriores', []):
    print(f"  {b['especie']} DIB={b['dib']} DCB={b.get('dcb', 'ATIVO')}")

# 2) Calcular resumo com DER = 12/09/2024
print("\n=== CALCULO TC (DER 12/09/2024) ===")
calc_body = {
    "segurado": data["segurado"],
    "der": "12/09/2024",
    "tipo": "idade",
}

resp2 = requests.post(f"{BASE}/calculo/resumo", json=calc_body)
if resp2.status_code == 200:
    r = resp2.json()
    tc = r["tempo_contribuicao"]
    print(f"TC: {tc['anos']}a {tc['meses']}m {tc['dias']}d")
    print(f"TC total dias: {tc['total_dias']}")
    print(f"TC anos decimal: {tc['anos_decimal']}")
    print(f"Carencia: {r['carencia_meses']} meses")
    print(f"Idade na DER: {r['idade_na_der']}")
    print(f"Num vinculos: {r['num_vinculos']}")
    print(f"SB: {r.get('salario_beneficio')}")
else:
    print(f"ERRO {resp2.status_code}: {resp2.text}")

# 3) Calcular com DER = 17/03/2026 (Prévius)
print("\n=== CALCULO TC (DER 17/03/2026 - comparar Previus) ===")
calc_body["der"] = "17/03/2026"
resp3 = requests.post(f"{BASE}/calculo/resumo", json=calc_body)
if resp3.status_code == 200:
    r = resp3.json()
    tc = r["tempo_contribuicao"]
    print(f"TC: {tc['anos']}a {tc['meses']}m {tc['dias']}d")
    print(f"TC total dias: {tc['total_dias']}")
    print(f"Carencia: {r['carencia_meses']} meses")
    print(f"Idade na DER: {r['idade_na_der']}")
    print(f"Previus diz: 14a 2m 14d (sem projecao)")
else:
    print(f"ERRO {resp3.status_code}: {resp3.text}")
