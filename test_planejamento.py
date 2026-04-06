"""Teste do planejamento com analise TC vs Carencia."""
import requests, json

BASE = "http://localhost:8000/api/v1"

# Upload CNIS
with open(r"C:\Users\Administrador\Documents\DOCUMENTOS_ORGANIZADOS\Maria Rosa de Toledo\cnis rosa.pdf", "rb") as f:
    resp = requests.post(f"{BASE}/upload/cnis", files={"arquivo": ("cnis.pdf", f, "application/pdf")})
data = resp.json()
seg = data["segurado"]
print(f"Upload: {data['sucesso']}, Vinculos: {len(seg['vinculos'])}, B31: {len(seg.get('beneficios_anteriores', []))}")

# Planejamento
plan_resp = requests.post(f"{BASE}/planejamento/projecao", json={
    "segurado": seg,
    "der": "05/04/2026",
    "salario_projetado": "1518.00",
})

if plan_resp.status_code == 200:
    p = plan_resp.json()
    print(f"\n=== PLANEJAMENTO ===")
    print(f"TC atual: {p['tc_atual']}")
    print(f"Carencia: {p.get('carencia_meses', 'N/A')}")

    atc = p.get("analise_tc_carencia")
    if atc:
        print(f"\n=== ANALISE TC vs CARENCIA ===")
        print(f"TC total: {atc['tc_total_texto']}")
        print(f"TC sem B31: {atc['tc_sem_b31_texto']}")
        print(f"Dias B31: {atc['dias_b31_intercalado']} ({atc['meses_b31_intercalado']} meses)")
        print(f"Carencia: {atc['carencia_meses']}/{atc['carencia_exigida']}")
        print(f"Faltam: {atc['faltam_carencia']} meses ({atc['faltam_carencia_texto']})")
        print(f"Gargalo: {atc['gargalo']}")
        print(f"B31 periodos: {len(atc.get('beneficios_b31', []))}")
        for b in atc.get("beneficios_b31", []):
            print(f"  {b['dib']} a {b['dcb']} = {b['dias']} dias")
    else:
        print("SEM analise_tc_carencia!")

    # Projecoes
    print(f"\n=== PROJECOES ===")
    for proj in p.get("projecoes", []):
        print(f"  {proj['regra']}: {proj.get('data_elegibilidade', 'N/A')} ({proj.get('texto_faltante', 'N/A')})")
else:
    print(f"ERRO {plan_resp.status_code}: {plan_resp.text[:500]}")
