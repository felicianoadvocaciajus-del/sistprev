"""
Gerador de Relatório Pericial Previdenciário — HTML profissional.
Compatível com impressão via window.print() e salvamento em PDF pelo navegador.
"""
from __future__ import annotations
import html as html_module
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional


def gerar_pdf(segurado: Dict, calculo: Dict, titulo: str = "Relatório Pericial Previdenciário") -> bytes:
    """Gera PDF via WeasyPrint (requer GTK no Windows)."""
    try:
        from weasyprint import HTML as WH
    except ImportError:
        raise ImportError("WeasyPrint não instalado. Execute: pip install weasyprint")
    html_content = gerar_html(segurado, calculo, titulo)
    return WH(string=html_content).write_pdf()


def gerar_html(segurado: Dict, calculo: Dict, titulo: str = "Relatório Pericial Previdenciário") -> str:
    """Gera HTML completo do relatório pericial."""
    dp = segurado.get("dados_pessoais", {})
    vinculos = segurado.get("vinculos", [])
    hoje = date.today().strftime("%d/%m/%Y")

    cenarios = calculo.get("todos_cenarios", [])
    melhor = calculo.get("melhor_cenario")
    elegivel = calculo.get("elegivel", False)
    der = calculo.get("der", "—")
    tipo_raw = calculo.get("tipo", "—")
    rmi_str = calculo.get("rmi", "0")

    # ── Classificação temporal correta ──────────────────────────────────
    tipo = _traduzir_tipo(tipo_raw, der)

    # ── Modo revisão e alertas ──────────────────────────────────────────
    modo_revisao = calculo.get("modo_revisao", False)
    nb_ativo = calculo.get("nb_ativo")
    alertas = calculo.get("alertas_consistencia", [])

    html = _css_e_cabecalho(titulo, hoje, dp, elegivel, rmi_str, melhor)
    html += _secao_identificacao(dp, der, tipo, hoje, modo_revisao, nb_ativo)
    if alertas:
        html += _secao_alertas_consistencia(alertas)
    html += _secao_vinculos(vinculos)
    html += _secao_resultado(elegivel, rmi_str, melhor, cenarios, modo_revisao)
    if modo_revisao and nb_ativo:
        html += _secao_explicacao_revisao_cliente(dp, der, melhor, nb_ativo, elegivel)
    html += _secao_cenarios_detalhado(cenarios)
    html += _secao_fundamentacao()
    html += _secao_conclusao(elegivel, melhor, dp, modo_revisao, nb_ativo, alertas)
    html += _secao_assinatura(hoje)
    html += "</body></html>"
    return html


def _secao_assinatura(hoje: str) -> str:
    """Bloco de assinatura final — marca Feliciano Advocacia."""
    return f"""
<div style="margin-top:60pt;text-align:center;">
  <hr style="border:none;border-top:1px solid #4F81BD;width:40%;margin:0 auto 10pt auto;"/>
  <div style="font-size:12pt;font-weight:700;color:#1a3c6e;">Advogado(a) / Consultor(a) Previdenciário(a)</div>
  <div style="font-size:10pt;color:#6b7280;margin-top:4pt;">{hoje}</div>
  <div style="font-size:9pt;color:#6b7280;margin-top:30pt;font-style:italic;">
    FELICIANO ADVOCACIA — Assessoria Jurídica Previdenciária<br/>
    Documento gerado pelo SistPrev — Cálculos conforme Lei 8.213/91, EC 103/2019 e CJF Res. 963/2025
  </div>
</div>
"""


def _traduzir_tipo(tipo_raw: str, der) -> str:
    """Traduz o tipo interno para rótulo correto conforme marco temporal."""
    LABELS = {
        "pre_reforma": "Aposentadoria por TC — Regras Pré-Reforma (Lei 8.213/91)",
        "transicao_ec103": "Aposentadoria por TC — Regras de Transição (EC 103/2019)",
        "transicao": None,  # será resolvido pela DER
        "idade": "Aposentadoria por Idade",
        "especial_15": "Aposentadoria Especial — 15 anos",
        "especial_20": "Aposentadoria Especial — 20 anos",
        "especial_25": "Aposentadoria Especial — 25 anos",
    }
    label = LABELS.get(tipo_raw)
    if label:
        return label
    # Fallback: resolver pelo valor da DER
    try:
        if isinstance(der, str) and "/" in der:
            p = der.split("/")
            der_date = date(int(p[2]), int(p[1]), int(p[0]))
        elif isinstance(der, date):
            der_date = der
        else:
            der_date = date.fromisoformat(str(der))
        if der_date < date(2019, 11, 13):
            return "Aposentadoria por TC — Regras Pré-Reforma (Lei 8.213/91)"
        else:
            return "Aposentadoria por TC — Regras de Transição (EC 103/2019)"
    except Exception:
        return str(tipo_raw)


def _secao_alertas_consistencia(alertas: list) -> str:
    """Seção de alertas de consistência — aparece antes dos vínculos."""
    html = '<h2 style="color:#991b1b;">⚠ Alertas de Consistência</h2>'
    for a in alertas:
        html += f'<div class="aviso" style="border-left-color:#991b1b;background:#fef2f2;">{_esc(a)}</div>'
    return html


def gerar_html_planejamento(segurado: Dict, planejamento: Dict, nome_advogado: Optional[str] = None) -> str:
    """Gera relatório profissional de planejamento previdenciário para o cliente."""
    dp = segurado.get("dados_pessoais", {})
    hoje = date.today().strftime("%d/%m/%Y")
    nome = dp.get("nome", "Segurado")
    nome_curto = nome.split()[0]

    projecoes = planejamento.get("projecoes", [])
    alcancaveis = sorted(
        [p for p in projecoes if p.get("data_elegibilidade")],
        key=lambda p: p.get("meses_faltantes", 9999)
    )
    nao_alcancaveis = [p for p in projecoes if not p.get("data_elegibilidade")]
    melhor = alcancaveis[0] if alcancaveis else None
    tc = planejamento.get("tc_atual", {})
    sal = planejamento.get("salario_projetado", "0")
    elegiveis_agora = planejamento.get("elegiveis_agora", False)
    recomendacao = planejamento.get("recomendacao", "")
    argumentos = planejamento.get("argumentos_cliente", [])

    tcanos = tc.get("anos", 0)
    tcmeses = tc.get("meses", 0)
    tcdias = tc.get("dias", 0)
    tc_total_dias = tc.get("total_dias", 0)

    html = _css_planejamento(nome, hoje)

    # ── Capa / Hero ──────────────────────────────────────────────────────────
    status_cor = "#065f46" if elegiveis_agora else "#1e3a5f"
    status_bg = "#d1fae5" if elegiveis_agora else "#dbeafe"
    status_txt = "✅ JÁ PODE SE APOSENTAR" if elegiveis_agora else "⏳ EM FASE DE PLANEJAMENTO"

    rmi_destaque = _fmt_brl(melhor["rmi_projetada"]) if melhor else "—"
    data_destaque = melhor["data_elegibilidade"] if melhor else "—"
    periodo_destaque = melhor["texto_faltante"] if melhor else "—"

    html += f"""
<div class="capa">
  <div class="capa-header">
    <div class="logo-area">⚖️ <strong>SistPrev</strong></div>
    <div class="capa-tipo">PLANEJAMENTO PREVIDENCIÁRIO</div>
  </div>
  <div class="capa-nome">{_esc(nome)}</div>
  <div class="capa-meta">
    CPF: {_fmt_cpf(dp.get('cpf',''))} &nbsp;|&nbsp;
    Nascimento: {_esc(dp.get('data_nascimento','—'))} &nbsp;|&nbsp;
    Sexo: {_esc(dp.get('sexo','—'))} &nbsp;|&nbsp;
    Elaborado em: {hoje}
  </div>
  <div class="status-badge" style="background:{status_bg};color:{status_cor};">{status_txt}</div>
  <div class="capa-destaque-grid">
    <div class="capa-stat">
      <div class="capa-stat-val">{tcanos}a {tcmeses}m {tcdias}d</div>
      <div class="capa-stat-label">Tempo de Contribuição Atual</div>
    </div>
    <div class="capa-stat">
      <div class="capa-stat-val">R$ {_fmt_brl(sal)}</div>
      <div class="capa-stat-label">Salário de Contribuição Projetado</div>
    </div>
    {"" if not melhor else f'''
    <div class="capa-stat destaque-verde">
      <div class="capa-stat-val">R$ {rmi_destaque}</div>
      <div class="capa-stat-label">RMI Estimada — Melhor Cenário</div>
    </div>
    <div class="capa-stat destaque-azul">
      <div class="capa-stat-val">{data_destaque}</div>
      <div class="capa-stat-label">Data Prevista — Melhor Cenário ({periodo_destaque})</div>
    </div>'''}
  </div>
</div>
"""

    # ── Recomendação estratégica ─────────────────────────────────────────────
    if recomendacao:
        html += f"""
<div class="section">
  <div class="section-title">📌 Recomendação Estratégica</div>
  <div class="recomendacao-box">{_esc(recomendacao)}</div>
</div>
"""

    # ── Situação atual ───────────────────────────────────────────────────────
    meta_meses = 420  # 35 anos
    pct_tc = min(100, round((tcanos * 12 + tcmeses) / meta_meses * 100))
    html += f"""
<div class="section">
  <div class="section-title">1. Situação Previdenciária Atual</div>
  <table>
    <tr><th>Item</th><th>Valor</th></tr>
    <tr><td>Nome</td><td><strong>{_esc(nome)}</strong></td></tr>
    <tr><td>Tempo de Contribuição Apurado</td><td><strong>{tcanos} anos, {tcmeses} meses e {tcdias} dias</strong> ({tc_total_dias:,} dias totais)</td></tr>
    <tr><td>Progresso (meta 35 anos)</td><td>
      <div style="display:flex;align-items:center;gap:10px;">
        <div style="flex:1;background:#e5e7eb;border-radius:99px;height:10px;">
          <div style="width:{pct_tc}%;background:linear-gradient(90deg,#1a56db,#3b82f6);height:10px;border-radius:99px;"></div>
        </div>
        <span><strong>{pct_tc}%</strong></span>
      </div>
    </td></tr>
    <tr><td>Salário de Contribuição Projetado</td><td>R$ {_fmt_brl(sal)}</td></tr>
    <tr><td>Status de Elegibilidade Atual</td><td class="{'elegivel' if elegiveis_agora else 'pendente'}"><strong>{'JÁ ELEGÍVEL — pode requerer hoje' if elegiveis_agora else 'Ainda não elegível — planejamento necessário'}</strong></td></tr>
  </table>
</div>
"""

    # ── Linha do tempo ───────────────────────────────────────────────────────
    if alcancaveis:
        html += """
<div class="section page-break">
  <div class="section-title">2. Linha do Tempo — Datas de Aposentadoria por Regra</div>
  <p class="section-desc">Projeções calculadas considerando contribuição contínua a partir de hoje, com o salário informado.</p>
"""
        for i, p in enumerate(alcancaveis):
            is_melhor = (i == 0)
            cor = "#065f46" if is_melhor else "#1e3a5f"
            bg = "#f0fdf4" if is_melhor else "#f0f4ff"
            borda = "#059669" if is_melhor else "#3b82f6"
            badge = '<span class="badge-melhor">⭐ MELHOR OPÇÃO</span>' if is_melhor else ""
            html += f"""
  <div class="timeline-card" style="border-left:4px solid {borda};background:{bg};">
    <div class="tl-header">
      <div>
        <div class="tl-data" style="color:{cor};">{_esc(p.get('data_elegibilidade','—'))}</div>
        <div class="tl-regra">{_esc(p.get('regra','—'))}</div>
      </div>
      <div style="text-align:right;">
        <div class="tl-rmi" style="color:{cor};">R$ {_fmt_brl(p.get('rmi_projetada','0'))}</div>
        {badge}
      </div>
    </div>
    <div class="tl-periodo">Tempo faltando: <strong>{_esc(p.get('texto_faltante','—'))}</strong></div>
    <div class="tl-msg">{_esc(p.get('mensagem_cliente',''))}</div>
    <div class="tl-lei">Base legal: {_esc(p.get('base_legal','—'))}</div>
  </div>
"""
        html += "</div>"

    # ── Tabela comparativa ───────────────────────────────────────────────────
    html += """
<div class="section">
  <div class="section-title">3. Quadro Comparativo — Todas as Regras</div>
  <table>
    <tr><th>Regra</th><th>Data Prevista</th><th>Tempo Faltando</th><th>RMI Estimada</th><th>Status</th></tr>
"""
    todas = sorted(
        alcancaveis + nao_alcancaveis,
        key=lambda p: (p.get("meses_faltantes") or 9999)
    )
    for i, p in enumerate(todas):
        ok = bool(p.get("data_elegibilidade"))
        cls_rmi = "elegivel" if ok else "inelegivel"
        star = "⭐ " if ok and i == 0 else ""
        html += f"""
    <tr class="{'melhor-row' if ok and i==0 else ''}">
      <td>{star}{_esc(p.get('regra','—'))}</td>
      <td>{_esc(p.get('data_elegibilidade') or '—')}</td>
      <td>{_esc(p.get('texto_faltante') or '—')}</td>
      <td class="{cls_rmi}"><strong>{'R$ '+_fmt_brl(p.get('rmi_projetada','0')) if ok else '—'}</strong></td>
      <td class="{cls_rmi}">{'✓ Alcançável' if ok else '✗ Não alcançável'}</td>
    </tr>"""
    html += "</table></div>"

    # ── Cenários de vida ─────────────────────────────────────────────────────
    html += f"""
<div class="section page-break">
  <div class="section-title">4. Cenários de Vida e Impacto na Aposentadoria</div>
  <p class="section-desc">Análise de como diferentes situações afetam o planejamento de {_esc(nome_curto)}:</p>

  <div class="cenario-vida">
    <div class="cv-titulo">📋 Cenário A — Continuar Trabalhando com Carteira Assinada</div>
    <div class="cv-corpo">
      A situação mais favorável. Cada mês trabalhado conta automaticamente como tempo de contribuição.
      Não há necessidade de recolhimento adicional. A renda projetada de <strong>R$ {rmi_destaque}</strong> é baseada
      neste cenário. Recomendado manter o vínculo ativo até a data de elegibilidade.
    </div>
  </div>

  <div class="cenario-vida">
    <div class="cv-titulo">💼 Cenário B — Trabalho por Conta Própria (MEI ou Autônomo)</div>
    <div class="cv-corpo">
      Se {_esc(nome_curto)} passar a trabalhar como MEI ou autônomo, deverá recolher mensalmente como
      Contribuinte Individual. O valor mínimo é 20% sobre o salário-mínimo (para CI geral) ou 5% (MEI, sem
      direito a aposentadoria por tempo de contribuição). <strong>Atenção:</strong> recolhimento como MEI (5%)
      não conta para TC — use a alíquota de 20% para manter o planejamento.
    </div>
  </div>

  <div class="cenario-vida">
    <div class="cv-titulo">⏸️ Cenário C — Período de Desemprego com Recolhimento Facultativo</div>
    <div class="cv-corpo">
      Em caso de desemprego, {_esc(nome_curto)} pode se inscrever como Segurado Facultativo e recolher
      20% sobre qualquer valor entre o salário-mínimo e o teto do INSS. Isso mantém o tempo de
      contribuição correndo normalmente. <strong>Cada mês sem recolhimento atrasa a data de aposentadoria em 1 mês.</strong>
      Período de carência: não há — basta ter inscrição prévia no RGPS.
    </div>
  </div>

  <div class="cenario-vida">
    <div class="cv-titulo">🚫 Cenário D — Desemprego sem Recolhimento</div>
    <div class="cv-corpo">
      O cenário de maior risco. A contagem de tempo paralisa completamente. Se {_esc(nome_curto)} ficar
      {alcancaveis[0]['meses_faltantes'] if alcancaveis else '?'} meses sem contribuir,
      a data de aposentadoria atrasa na mesma proporção. Além disso, a qualidade de segurado se perde após
      12 a 36 meses sem contribuição (dependendo do tempo já contribuído), podendo exigir nova carência.
      <strong>Recomendamos fortemente o recolhimento facultativo em caso de desemprego.</strong>
    </div>
  </div>
</div>
"""

    # ── Argumentos para o cliente ────────────────────────────────────────────
    if argumentos:
        html += """
<div class="section">
  <div class="section-title">5. Pontos-Chave para {}</div>
  <ol class="argumentos-list">
""".format(_esc(nome_curto))
        for arg in argumentos:
            html += f"    <li>{_esc(arg)}</li>\n"
        html += "  </ol>\n</div>\n"

    # ── Resumo Executivo ────────────────────────────────────────────────────
    resumo_exec = planejamento.get("resumo_executivo", {})
    if resumo_exec:
        html += f"""
<div class="section">
  <div class="section-title">6. Resumo Executivo</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
    <div style="background:#f0f4ff;padding:14px;border-radius:8px;">
      <div style="font-size:9pt;color:#6b7280;font-weight:700;margin-bottom:4px;">SITUAÇÃO ATUAL</div>
      <div style="font-size:10pt;">{_esc(resumo_exec.get('situacao_atual','—'))}</div>
    </div>
    <div style="background:#f0fdf4;padding:14px;border-radius:8px;">
      <div style="font-size:9pt;color:#6b7280;font-weight:700;margin-bottom:4px;">MELHOR CAMINHO</div>
      <div style="font-size:10pt;">{_esc(resumo_exec.get('melhor_caminho','—'))}</div>
    </div>
    <div style="background:#fef3c7;padding:14px;border-radius:8px;">
      <div style="font-size:9pt;color:#6b7280;font-weight:700;margin-bottom:4px;">AÇÃO IMEDIATA</div>
      <div style="font-size:10pt;">{_esc(resumo_exec.get('acao_imediata','—'))}</div>
    </div>
    <div style="background:#ede9fe;padding:14px;border-radius:8px;">
      <div style="font-size:9pt;color:#6b7280;font-weight:700;margin-bottom:4px;">PRÓXIMO PASSO</div>
      <div style="font-size:10pt;">{_esc(resumo_exec.get('proximo_passo','—'))}</div>
    </div>
  </div>
</div>
"""

    # ── Qualidade de Segurado ─────────────────────────────────────────────
    qs = planejamento.get("qualidade_segurado", {})
    if qs:
        qs_status = qs.get("status", "—")
        qs_cor = "#065f46" if qs_status == "ATIVA" else "#b45309" if qs_status == "EM_RISCO" else "#991b1b"
        qs_bg = "#f0fdf4" if qs_status == "ATIVA" else "#fef3c7" if qs_status == "EM_RISCO" else "#fef2f2"
        qs_icon = "✅" if qs_status == "ATIVA" else "⚠️" if qs_status == "EM_RISCO" else "❌"
        html += f"""
<div class="section">
  <div class="section-title">7. Qualidade de Segurado</div>
  <div style="background:{qs_bg};padding:14px 18px;border-radius:8px;border-left:4px solid {qs_cor};margin-bottom:12px;">
    <div style="font-size:12pt;font-weight:700;color:{qs_cor};margin-bottom:4px;">{qs_icon} {qs_status}</div>
    <div style="font-size:10pt;color:#374151;">{_esc(qs.get('mensagem',''))}</div>
  </div>
  <table>
    <tr><th>Última Contribuição</th><th>Período de Graça</th><th>Perda da Qualidade</th><th>Dias Restantes</th></tr>
    <tr>
      <td>{_esc(str(qs.get('ultima_contribuicao','—')))}</td>
      <td>{qs.get('periodo_graca_meses',0)} meses</td>
      <td>{_esc(str(qs.get('data_perda_qualidade','—')))}</td>
      <td>{qs.get('dias_restantes',0)} dias</td>
    </tr>
  </table>
</div>
"""

    # ── Cenários de Vida Quantificados ──────────────────────────────────────
    cenarios_q = planejamento.get("cenarios_vida", [])
    if cenarios_q:
        html += """
<div class="section page-break">
  <div class="section-title">8. Cenários de Contribuição — Comparativo com Valores</div>
  <p class="section-desc">Quanto custa cada forma de contribuição e qual o impacto na aposentadoria.</p>
  <table>
    <tr><th>Cenário</th><th>Custo Mensal</th><th>Custo Anual</th><th>Total até Aposentar</th><th>Impacto na Data</th><th>Impacto na RMI</th></tr>
"""
        for cq in cenarios_q:
            nome_cen = f"{cq.get('cenario','')} — {cq.get('nome','')}"
            html += f"""
    <tr>
      <td><strong>{_esc(nome_cen)}</strong><br><small style="color:#6b7280;">{_esc(cq.get('descricao',''))}</small></td>
      <td>R$ {_fmt_brl(cq.get('monthly_cost','0'))}</td>
      <td>R$ {_fmt_brl(cq.get('annual_cost','0'))}</td>
      <td>R$ {_fmt_brl(cq.get('total_cost_until_retirement','0'))}</td>
      <td>{_esc(str(cq.get('impact_on_date','—')))}</td>
      <td>{_esc(str(cq.get('impact_on_rmi','—')))}</td>
    </tr>"""
        html += "</table></div>"

    # ── Pensão por Morte ──────────────────────────────────────────────────
    pensao = planejamento.get("pensao_projetada", {})
    if pensao and pensao.get("cenarios"):
        html += f"""
<div class="section">
  <div class="section-title">9. Pensão por Morte — Projeção para Dependentes</div>
  <p class="section-desc">{_esc(pensao.get('mensagem',''))}</p>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:12px;">"""
        for cp in pensao["cenarios"]:
            html += f"""
    <div style="background:#f0f4ff;padding:16px;border-radius:8px;text-align:center;">
      <div style="font-size:18pt;font-weight:800;color:#1a3c6e;">{_esc(cp.get('valor_formatado','—'))}</div>
      <div style="font-size:9pt;color:#6b7280;margin-top:4px;">{cp.get('dependentes',0)} dependente{'s' if cp.get('dependentes',0)>1 else ''} ({cp.get('cota_pct',0)}%)</div>
    </div>"""
        html += "</div></div>"

    # ── Plano de Ação ────────────────────────────────────────────────────────
    plano = planejamento.get("plano_acao", [])
    if plano:
        html += """
<div class="section page-break">
  <div class="section-title">10. Plano de Ação — Próximos Passos</div>
  <p class="section-desc">Passos concretos para garantir a melhor aposentadoria possível.</p>
"""
        for pa in plano:
            urg_cor = "#991b1b" if pa.get("urgencia") == "ALTA" else "#b45309" if pa.get("urgencia") == "MEDIA" else "#065f46"
            urg_bg = "#fef2f2" if pa.get("urgencia") == "ALTA" else "#fef3c7" if pa.get("urgencia") == "MEDIA" else "#f0fdf4"
            html += f"""
  <div style="display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #e5e7eb;align-items:flex-start;">
    <div style="background:#1a3c6e;color:#fff;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0;font-size:10pt;">{pa.get('numero','')}</div>
    <div style="flex:1;">
      <div style="font-weight:700;font-size:11pt;margin-bottom:4px;">{_esc(pa.get('titulo',''))}</div>
      <div style="font-size:10pt;color:#374151;line-height:1.7;">{_esc(pa.get('descricao',''))}</div>
      <div style="display:flex;gap:12px;margin-top:6px;font-size:9pt;">
        <span style="color:#6b7280;">⏰ {_esc(pa.get('prazo',''))}</span>
        <span style="background:{urg_bg};color:{urg_cor};padding:2px 8px;border-radius:4px;font-weight:600;">Urgência: {_esc(pa.get('urgencia',''))}</span>
      </div>
    </div>
  </div>"""
        html += "</div>"

    # ── Custo-benefício ───────────────────────────────────────────────────────
    custo_beneficio = planejamento.get("custo_beneficio", [])
    expectativa_vida = planejamento.get("expectativa_vida", {})
    if custo_beneficio:
        ev_anos = expectativa_vida.get("anos", 76.6)
        ev_sexo = "mulheres" if expectativa_vida.get("sexo","") == "FEMININO" else "homens"
        ev_fonte = expectativa_vida.get("fonte", "IBGE 2024")
        html += f"""
<div class="section page-break">
  <div class="section-title">11. Análise de Custo-Benefício — Quanto Vale Contribuir?</div>
  <p class="section-desc">
    Baseado na <strong>expectativa de vida do brasileiro segundo IBGE 2024: {ev_anos} anos</strong> para {ev_sexo}.
    Fonte: {_esc(ev_fonte)}.
    A análise mostra quanto você pagará de contribuição até a aposentadoria, quanto receberá até a expectativa de vida e o retorno sobre o investimento.
  </p>
"""
        for cb in custo_beneficio:
            html += f"""
  <div style="margin-bottom:24px;">
    <h3 style="color:#1a3c6e;margin-bottom:4px;">{_esc(cb.get('regra',''))}</h3>
    <div style="background:#f0f4ff;border-radius:8px;padding:12px 16px;margin-bottom:10px;font-size:10pt;display:flex;gap:24px;flex-wrap:wrap;">
      <span>📅 Aposentadoria: <strong>{_esc(cb.get('data_elegibilidade','—'))}</strong></span>
      <span>🎂 Idade estimada: <strong>{cb.get('idade_aposentadoria',0):.1f} anos</strong></span>
      <span>📆 Meses recebendo: <strong>{cb.get('meses_recebendo',0):.0f} meses</strong></span>
      <span>💰 RMI: <strong>{_esc(cb.get('rmi_formatada','—'))}</strong></span>
      <span>💵 Total recebido até expectativa de vida: <strong>R$ {_fmt_brl(cb.get('total_recebido','0'))}</strong></span>
    </div>
    <table>
      <tr>
        <th>Modalidade</th>
        <th>Alíquota</th>
        <th>Contrib. Mensal</th>
        <th>Total Pago</th>
        <th>Total Recebido</th>
        <th>Lucro Líquido</th>
        <th>ROI</th>
        <th>Recupera em</th>
        <th>Vale a Pena?</th>
      </tr>
"""
            for m in cb.get("modalidades", []):
                ok = m.get("vale_a_pena", False)
                bg = "#f0fdf4" if ok else "#fef2f2"
                cor = "#065f46" if ok else "#991b1b"
                sinal = "✅ Sim" if ok else "❌ Não"
                html += f"""
      <tr style="background:{bg};">
        <td><strong>{_esc(m.get('modalidade',''))}</strong></td>
        <td>{m.get('aliquota_pct',0):.0f}%</td>
        <td>R$ {_fmt_brl(m.get('contribuicao_mensal','0'))}</td>
        <td>R$ {_fmt_brl(m.get('total_pago_ate_apos','0'))}</td>
        <td>R$ {_fmt_brl(m.get('total_recebido_ate_obito','0'))}</td>
        <td style="color:{cor};font-weight:700;">R$ {_fmt_brl(m.get('lucro_liquido','0'))}</td>
        <td style="color:{cor};font-weight:700;">{m.get('roi_percentual','0')}%</td>
        <td>{m.get('anos_para_recuperar','0')} anos</td>
        <td style="color:{cor};font-weight:700;">{sinal}</td>
      </tr>
"""
            html += "    </table>\n  </div>"
        html += "</div>"

    # ── Fundamentação ────────────────────────────────────────────────────────
    html += """
<div class="section page-break">
  <div class="section-title">12. Fundamentação Legal</div>
  <table>
    <tr><th>Norma</th><th>Dispositivo</th><th>Aplicação</th></tr>
    <tr><td>EC 103/2019</td><td>Art. 15</td><td>Regra de Transição — Sistema de Pontos (idade + TC)</td></tr>
    <tr><td>EC 103/2019</td><td>Art. 16</td><td>Regra de Transição — Idade Mínima Progressiva</td></tr>
    <tr><td>EC 103/2019</td><td>Art. 17</td><td>Regra de Transição — Pedágio 50% com Fator Previdenciário</td></tr>
    <tr><td>EC 103/2019</td><td>Art. 20</td><td>Regra de Transição — Pedágio 100% com Idade Mínima</td></tr>
    <tr><td>EC 103/2019</td><td>Art. 19</td><td>Aposentadoria por Idade — Regra Permanente</td></tr>
    <tr><td>Lei 8.213/91</td><td>Art. 29</td><td>Período Básico de Cálculo e Salário de Benefício</td></tr>
    <tr><td>Lei 8.213/91</td><td>Art. 25</td><td>Carência — 180 meses para aposentadoria por idade</td></tr>
    <tr><td>Lei 8.213/91</td><td>Art. 15</td><td>Qualidade de segurado e períodos de graça</td></tr>
    <tr><td>Decreto 3.048/99</td><td>Art. 11</td><td>Segurado Facultativo — recolhimento voluntário</td></tr>
    <tr><td>LC 123/2006</td><td>Art. 18-A</td><td>MEI — alíquota reduzida de 5% (não conta para TC)</td></tr>
  </table>
</div>
"""

    # ── Conclusão ────────────────────────────────────────────────────────────
    if melhor:
        concl_data = melhor["data_elegibilidade"]
        concl_periodo = melhor["texto_faltante"]
        concl_rmi = _fmt_brl(melhor["rmi_projetada"])
        concl_regra = melhor["regra"]
    else:
        concl_data = concl_periodo = concl_rmi = concl_regra = "—"

    html += f"""
<div class="section page-break">
  <div class="section-title">13. Conclusão e Recomendação Final</div>
  <div class="conclusao-box">
    <p>Com base na análise completa do histórico previdenciário de <strong>{_esc(nome)}</strong>
    e nas projeções calculadas conforme a legislação vigente (EC 103/2019, Lei 8.213/91),
    conclui-se que:</p>

    <ul style="margin:12px 0 12px 20px;line-height:1.8;">
      <li>O tempo de contribuição atual apurado é de <strong>{tcanos} anos, {tcmeses} meses e {tcdias} dias</strong>.</li>
      {"<li>O segurado <strong>já está elegível</strong> para requerer aposentadoria. Recomenda-se protocolar imediatamente para não perder competências.</li>" if elegiveis_agora else f"<li>A data mais próxima de aposentadoria é <strong>{concl_data}</strong> (faltam {concl_periodo}), pela regra <strong>{_esc(concl_regra)}</strong>, com RMI estimada de <strong>R$ {concl_rmi}</strong>.</li>"}
      <li>Para garantir a elegibilidade no prazo projetado, é essencial manter as contribuições mensais em dia, sem interrupções.</li>
      <li>Em caso de desemprego, recomenda-se o recolhimento como Segurado Facultativo (alíquota 20% sobre o salário-mínimo) para não perder o tempo de contribuição em curso.</li>
      <li>Os valores de RMI são estimativas baseadas no salário atual. Variações salariais e reajustes do teto do INSS podem alterar os valores finais.</li>
    </ul>

    <p>{_esc(recomendacao)}</p>
  </div>

  <div class="assinatura">
    <p>___________________________________________</p>
    <p><strong>{_esc(nome_advogado) if nome_advogado else "Advogado(a) / Consultor(a) Previdenciário(a)"}</strong></p>
    <p style="color:#6b7280;font-size:10pt;">{hoje}</p>
    <p style="font-size:9pt;color:#9ca3af;margin-top:8px;">
      Documento gerado pelo SistPrev · Cálculos conforme Lei 8.213/91, EC 103/2019 e CJF Res. 963/2025
    </p>
  </div>
</div>
</body></html>
"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# CSS e estrutura
# ─────────────────────────────────────────────────────────────────────────────

def _css_e_cabecalho(titulo, hoje, dp, elegivel, rmi, melhor) -> str:
    nome = dp.get("nome", "") or "—"
    cpf = dp.get("cpf", "") or "—"
    nasc = dp.get("data_nascimento", "") or "—"
    nit = dp.get("nit", "") or "—"
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<title>{_esc(titulo)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  @page {{ size: A4; margin: 2cm 2cm 2.5cm 2cm; }}
  body {{ font-family: 'Calibri', 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #1f2937; line-height: 1.55; background: #fff; }}

  /* ── CAPA FELICIANO ADVOCACIA ── */
  .capa-feliciano {{
    text-align: center;
    padding: 60pt 0 40pt 0;
    page-break-after: always;
  }}
  .capa-logo {{ font-size: 32pt; font-weight: 800; color: #1a3c6e; letter-spacing: 2pt; margin-bottom: 8pt; }}
  .capa-sub-logo {{ font-size: 14pt; color: #4F81BD; margin-bottom: 40pt; font-style: italic; }}
  .capa-linha {{ border: none; border-top: 2px solid #4F81BD; width: 60%; margin: 20pt auto; }}
  .capa-titulo {{ font-size: 26pt; font-weight: 800; color: #1a3c6e; margin: 40pt 0 12pt 0; text-transform: uppercase; letter-spacing: 1pt; }}
  .capa-nome {{ font-size: 18pt; font-weight: 700; color: #4F81BD; margin-bottom: 30pt; text-transform: uppercase; }}
  .capa-dados {{
    display: inline-block;
    border: 1px solid #1a3c6e;
    border-radius: 6pt;
    padding: 16pt 24pt;
    margin: 20pt auto;
    text-align: left;
  }}
  .capa-dados .row {{ margin: 4pt 0; }}
  .capa-dados .label {{ font-weight: 700; color: #1a3c6e; display: inline-block; width: 160pt; }}
  .capa-rodape {{
    position: fixed;
    bottom: 1cm; left: 2cm; right: 2cm;
    text-align: center;
    font-size: 9pt; color: #6b7280;
  }}

  /* ── CONTEÚDO INTERNO ── */
  h1 {{ font-size: 18pt; text-align: center; font-weight: 800; color: #1a3c6e; margin-bottom: 4pt; }}
  h2 {{ font-size: 13pt; font-weight: 700; margin-top: 20pt; margin-bottom: 8pt; color: #1a3c6e; border-bottom: 2px solid #1a3c6e; padding-bottom: 4pt; }}
  h3 {{ font-size: 11pt; font-weight: 700; margin-top: 12pt; margin-bottom: 4pt; color: #374151; }}
  h4 {{ font-size: 10pt; font-weight: 600; margin-top: 8pt; margin-bottom: 4pt; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8pt; font-size: 10pt; }}
  th {{ background: #1a3c6e; color: #fff; padding: 6pt 10pt; text-align: left; font-size: 10pt; }}
  td {{ padding: 5pt 10pt; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #f9fafb; }}
  .total-row td {{ font-weight: 700; background: #dbeafe; }}
  .melhor-row td {{ font-weight: 700; background: #d1fae5; }}
  .elegivel {{ color: #065f46; font-weight: 600; }}
  .inelegivel {{ color: #991b1b; }}
  .pendente {{ color: #1d4ed8; }}
  .aviso {{ background: #fef9c3; border-left: 4px solid #b45309; padding: 6pt 10pt; margin: 8pt 0; font-size: 10pt; }}
  .destaque-rmi {{
    text-align: center;
    padding: 20pt; margin: 16pt 0;
    background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
    border-left: 6px solid #16a34a;
    border-radius: 6pt;
  }}
  .destaque-rmi .valor {{ font-size: 28pt; font-weight: 800; color: #065f46; }}
  .destaque-rmi .label {{ font-size: 10pt; color: #064e3b; letter-spacing: 1pt; text-transform: uppercase; }}
  .destaque-rmi.inelegivel {{
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    border-left-color: #b45309;
  }}
  .destaque-rmi.inelegivel .valor {{ color: #92400e; }}

  .subtitulo {{ font-size: 10pt; text-align: center; color: #6b7280; margin-bottom: 12pt; }}
  .page-break {{ page-break-before: always; }}
  .mem-table td {{ padding: 2pt 6pt; font-size: 9pt; }}
  @media print {{
    body {{ padding: 0; }}
    .page-break {{ page-break-before: always; }}
  }}
</style>
</head>
<body>

<!-- ── CAPA FELICIANO ADVOCACIA ── -->
<div class="capa-feliciano">
  <div class="capa-logo">FELICIANO ADVOCACIA</div>
  <div class="capa-sub-logo">Assessoria Jurídica Previdenciária</div>
  <hr class="capa-linha"/>
  <div class="capa-titulo">{_esc(titulo)}</div>
  <div class="capa-nome">{_esc(nome)}</div>
  <div class="capa-dados">
    <div class="row"><span class="label">CPF:</span> {_esc(cpf)}</div>
    <div class="row"><span class="label">Data de Nascimento:</span> {_esc(nasc)}</div>
    <div class="row"><span class="label">NIT / PIS-PASEP:</span> {_esc(nit)}</div>
    <div class="row"><span class="label">Data do Relatório:</span> {hoje}</div>
  </div>
  <hr class="capa-linha"/>
  <div style="font-size:9pt;color:#6b7280;margin-top:30pt;font-style:italic;">
    Documento técnico-pericial · Conforme Lei 8.213/91, EC 103/2019 e Manual CJF Res. 963/2025
  </div>
</div>

<!-- ── CABEÇALHO INTERNO ── -->
<h1>{_esc(titulo)}</h1>
<p class="subtitulo">Elaborado em {hoje} &middot; Conforme Lei 8.213/91, EC 103/2019 e Manual CJF Res. 963/2025</p>
<hr style="border:none;border-top:3px solid #1a3c6e;margin-bottom:16pt;"/>
"""


def _css_planejamento(nome, hoje) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8"/>
<title>Planejamento Previdenciário — {_esc(nome)}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 11pt; color: #1f2937; line-height: 1.6; background: #fff; }}

  /* Capa */
  .capa {{ background: linear-gradient(135deg, #1a3c6e 0%, #1e40af 100%); color: #fff; padding: 40px 48px; margin-bottom: 0; }}
  .capa-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; font-size: 12pt; opacity: .8; }}
  .logo-area {{ font-size: 16pt; font-weight: 700; }}
  .capa-tipo {{ font-size: 10pt; letter-spacing: 2px; text-transform: uppercase; opacity: .7; }}
  .capa-nome {{ font-size: 26pt; font-weight: 800; margin-bottom: 6px; }}
  .capa-meta {{ font-size: 10pt; opacity: .75; margin-bottom: 16px; }}
  .status-badge {{ display: inline-block; padding: 6px 18px; border-radius: 99px; font-size: 11pt; font-weight: 700; margin-bottom: 24px; }}
  .capa-destaque-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }}
  .capa-stat {{ background: rgba(255,255,255,.12); border-radius: 10px; padding: 16px 20px; }}
  .capa-stat.destaque-verde {{ background: rgba(16,185,129,.2); }}
  .capa-stat.destaque-azul {{ background: rgba(96,165,250,.2); }}
  .capa-stat-val {{ font-size: 18pt; font-weight: 800; color: #fff; }}
  .capa-stat-label {{ font-size: 9pt; color: rgba(255,255,255,.7); margin-top: 4px; }}

  /* Seções */
  .section {{ padding: 32px 48px; border-bottom: 1px solid #e5e7eb; }}
  .section-title {{ font-size: 14pt; font-weight: 800; color: #1a3c6e; margin-bottom: 6px; padding-bottom: 6px; border-bottom: 2px solid #1a3c6e; margin-bottom: 16px; }}
  .section-desc {{ font-size: 10pt; color: #6b7280; margin-bottom: 16px; }}
  .recomendacao-box {{ background: #eff6ff; border-left: 4px solid #1d4ed8; padding: 14px 18px; border-radius: 0 8px 8px 0; font-size: 11pt; line-height: 1.7; color: #1e3a5f; }}

  /* Tabelas */
  table {{ width: 100%; border-collapse: collapse; font-size: 10pt; margin-top: 8px; }}
  th {{ background: #1a3c6e; color: #fff; padding: 8px 12px; text-align: left; }}
  td {{ padding: 7px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: top; }}
  tr:nth-child(even) td {{ background: #f9fafb; }}
  .melhor-row td {{ background: #d1fae5; font-weight: 700; }}
  .elegivel {{ color: #065f46; font-weight: 700; }}
  .inelegivel {{ color: #991b1b; }}
  .pendente {{ color: #1d4ed8; font-weight: 700; }}

  /* Timeline cards */
  .timeline-card {{ border-radius: 8px; padding: 18px 20px; margin-bottom: 14px; }}
  .tl-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 8px; }}
  .tl-data {{ font-size: 18pt; font-weight: 800; }}
  .tl-regra {{ font-size: 10pt; font-weight: 600; color: #374151; margin-top: 2px; }}
  .tl-rmi {{ font-size: 14pt; font-weight: 800; }}
  .badge-melhor {{ display: inline-block; background: #065f46; color: #fff; font-size: 9pt; padding: 3px 10px; border-radius: 99px; margin-top: 4px; }}
  .tl-periodo {{ font-size: 10pt; color: #4b5563; margin-bottom: 6px; }}
  .tl-msg {{ font-size: 10pt; color: #374151; line-height: 1.6; margin-bottom: 6px; }}
  .tl-lei {{ font-size: 9pt; color: #9ca3af; }}

  /* Cenários de vida */
  .cenario-vida {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px 20px; margin-bottom: 14px; }}
  .cv-titulo {{ font-size: 11pt; font-weight: 700; color: #1a3c6e; margin-bottom: 6px; }}
  .cv-corpo {{ font-size: 10pt; color: #374151; line-height: 1.7; }}

  /* Argumentos */
  .argumentos-list {{ padding-left: 20px; }}
  .argumentos-list li {{ padding: 6px 0; font-size: 10pt; line-height: 1.7; border-bottom: 1px solid #f3f4f6; }}

  /* Conclusão */
  .conclusao-box {{ background: #f0f9ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 20px 24px; font-size: 10pt; line-height: 1.8; }}
  .conclusao-box ul li {{ margin-bottom: 4px; }}
  .assinatura {{ text-align: center; margin-top: 48px; padding-top: 24px; border-top: 1px solid #e5e7eb; }}

  @media print {{
    .section {{ padding: 20px 32px; }}
    .capa {{ padding: 28px 32px; }}
    .page-break {{ page-break-before: always; }}
  }}
</style>
</head>
<body>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Seções do relatório pericial
# ─────────────────────────────────────────────────────────────────────────────

def _secao_identificacao(dp: Dict, der: str, tipo: str, hoje: str,
                         modo_revisao: bool = False, nb_ativo: Dict = None) -> str:
    nome = _esc(dp.get("nome") or "—")
    cpf = _fmt_cpf(dp.get("cpf") or "")
    dn = _esc(dp.get("data_nascimento") or "—")
    sexo = _esc(dp.get("sexo") or "—")
    nit = _esc(dp.get("nit") or "—")

    modo_str = '<span style="color:#991b1b;font-weight:700;">REVISÃO DE BENEFÍCIO ATIVO</span>' if modo_revisao else "Cálculo inicial"

    nb_row = ""
    if nb_ativo:
        nb_row = f"""
  <tr><td>Benefício Ativo (NB)</td><td><strong>{_esc(nb_ativo.get('numero','—'))}</strong> — Espécie {_esc(nb_ativo.get('especie','—'))}</td></tr>
  <tr><td>DIB do Benefício Ativo</td><td>{_esc(nb_ativo.get('dib','—'))}</td></tr>
  <tr><td>RMI Administrativa Vigente</td><td>R$ {_fmt_brl(nb_ativo.get('rmi','0')) if nb_ativo.get('rmi') else '—'}</td></tr>"""

    return f"""
<h2>1. Identificação do Segurado</h2>
<table>
  <tr><th style="width:220pt">Campo</th><th>Valor</th></tr>
  <tr><td>Nome Completo</td><td><strong>{nome}</strong></td></tr>
  <tr><td>CPF</td><td>{cpf}</td></tr>
  <tr><td>NIT / PIS-PASEP</td><td>{nit}</td></tr>
  <tr><td>Data de Nascimento</td><td>{dn}</td></tr>
  <tr><td>Sexo</td><td>{sexo}</td></tr>
  <tr><td>Data de Entrada do Requerimento (DER)</td><td>{_esc(der)}</td></tr>
  <tr><td>Tipo de Benefício Analisado</td><td>{_esc(tipo)}</td></tr>
  <tr><td>Modalidade do Cálculo</td><td>{modo_str}</td></tr>
  {nb_row}
  <tr><td>Data do Relatório</td><td>{hoje}</td></tr>
</table>
"""


def _secao_vinculos(vinculos: List[Dict]) -> str:
    if not vinculos:
        return "<h2>2. Vínculos Empregatícios</h2><p><em>Nenhum vínculo registrado.</em></p>"

    rows = ""
    total_contrib = 0
    for v in vinculos:
        n_c = len(v.get("contribuicoes", []))
        total_contrib += n_c
        rows += f"""<tr>
          <td>{_esc(v.get('empregador_nome') or '—')}</td>
          <td>{_esc(_fmt_cnpj(v.get('empregador_cnpj') or ''))}</td>
          <td>{_esc(v.get('tipo_vinculo') or '—')}</td>
          <td>{_esc(v.get('data_inicio') or '—')}</td>
          <td>{_esc(v.get('data_fim') or 'Em aberto')}</td>
          <td style="text-align:center">{n_c}</td>
        </tr>"""

    return f"""
<h2>2. Vínculos Empregatícios</h2>
<table>
  <tr><th>Empregador</th><th>CNPJ</th><th>Tipo</th><th>Início</th><th>Fim</th><th>Competências</th></tr>
  {rows}
  <tr class="total-row">
    <td colspan="5"><strong>Total de competências registradas</strong></td>
    <td style="text-align:center"><strong>{total_contrib}</strong></td>
  </tr>
</table>
"""


def _secao_resultado(elegivel: bool, rmi: str, melhor: Optional[Dict], cenarios: List[Dict],
                     modo_revisao: bool = False) -> str:
    cls = "elegivel" if elegivel else "inelegivel"
    # Linguagem condicional: "elegível" é estimativa quando há alertas
    if modo_revisao:
        status = "ELEGÍVEL (estimativa — sujeita a validação revisional)" if elegivel else "NÃO ELEGÍVEL"
    else:
        status = "ELEGÍVEL (conforme dados informados)" if elegivel else "NÃO ELEGÍVEL"
    rmi_fmt = _fmt_brl(rmi)
    melhor_nome = melhor.get("nome_regra", "—") if melhor else "—"
    melhor_lei = melhor.get("base_legal", "—") if melhor else "—"
    sb = _fmt_brl(melhor.get("salario_beneficio", "0")) if melhor else "—"
    coef = _fmt_pct(melhor.get("coeficiente", "0")) if melhor else "—"
    fp = melhor.get("fator_previdenciario") if melhor else None
    tc = melhor.get("tempo_contribuicao") if melhor else None

    tc_str = "—"
    if tc:
        tc_str = f"{tc.get('anos',0)} anos, {tc.get('meses',0)} meses e {tc.get('dias',0)} dias ({tc.get('total_dias',0):,} dias)"

    rmi_label = "RMI Estimada" if modo_revisao else "RMI — Renda Mensal Inicial"
    rmi_nota = ""
    if modo_revisao:
        rmi_nota = '<tr><td colspan="2" class="aviso" style="font-size:9pt;">⚠ Este valor é uma estimativa calculada com base nos dados informados. Deve ser confrontado com a RMI administrativa vigente e a memória de cálculo do INSS antes de ser utilizado em petição.</td></tr>'

    return f"""
<h2>3. Resultado do Cálculo</h2>
<table>
  <tr><th style="width:240pt">Item</th><th>Valor</th></tr>
  <tr><td>Status de Elegibilidade</td><td class="destaque {cls}" style="font-size:13pt;font-weight:800">{status}</td></tr>
  <tr><td>Melhor Regra Identificada</td><td><strong>{_esc(melhor_nome)}</strong></td></tr>
  <tr><td>Base Legal</td><td>{_esc(melhor_lei)}</td></tr>
  <tr><td>Tempo de Contribuição Apurado</td><td>{tc_str}</td></tr>
  <tr><td>Salário de Benefício (SB)</td><td>R$ {sb}</td></tr>
  <tr><td>Coeficiente Aplicado</td><td>{coef}</td></tr>
  {f'<tr><td>Fator Previdenciário</td><td>{_esc(str(fp))}</td></tr>' if fp else ''}
  <tr class="total-row"><td><strong>{rmi_label}</strong></td><td style="font-size:14pt;font-weight:800" class="{cls}">R$ {rmi_fmt}</td></tr>
  {rmi_nota}
</table>
"""


def _secao_cenarios_detalhado(cenarios: List[Dict]) -> str:
    if not cenarios:
        return ""

    html = '<h2 class="page-break">4. Análise Detalhada por Regra de Aposentadoria</h2>'
    html += '<p style="margin-bottom:12pt;font-size:10pt;color:#6b7280;">Análise completa de elegibilidade para cada regra vigente, com memória de cálculo.</p>'

    for c in cenarios:
        ok = c.get("elegivel", False)
        cls = "elegivel" if ok else "inelegivel"
        status = "✓ ELEGÍVEL" if ok else "✗ NÃO ELEGÍVEL"
        rmi = _fmt_brl(c.get("rmi", "0"))
        faltam = c.get("faltam_dias", 0)
        tc = c.get("tempo_contribuicao")
        tc_str = "—"
        if tc:
            tc_str = f"{tc.get('anos',0)}a {tc.get('meses',0)}m {tc.get('dias',0)}d ({tc.get('total_dias',0):,} dias)"

        html += f"""
<h3 style="margin-top:16pt;color:{'#065f46' if ok else '#1a3c6e'};">{_esc(c.get('nome_regra','—'))}</h3>
<table>
  <tr><th style="width:220pt">Item</th><th>Valor</th></tr>
  <tr><td>Status</td><td class="{cls}"><strong>{status}</strong></td></tr>
  <tr><td>Base Legal</td><td>{_esc(c.get('base_legal','—'))}</td></tr>
  <tr><td>Tempo de Contribuição</td><td>{tc_str}</td></tr>
  <tr><td>Salário de Benefício</td><td>R$ {_fmt_brl(c.get('salario_beneficio','0'))}</td></tr>
  <tr><td>Coeficiente</td><td>{_fmt_pct(c.get('coeficiente','0'))}</td></tr>
  {f'<tr><td>Fator Previdenciário</td><td>{c.get("fator_previdenciario")}</td></tr>' if c.get('fator_previdenciario') else ''}
  <tr class="{'total-row' if ok else ''}"><td><strong>RMI</strong></td><td class="{cls}"><strong>R$ {rmi}</strong></td></tr>
  {f'<tr><td>Dias faltantes para elegibilidade</td><td>{faltam:,} dias</td></tr>' if faltam else ''}
</table>
"""
        memoria = c.get("memoria", [])
        if memoria:
            html += '<h4>Memória de Cálculo</h4>'
            html += '<table class="mem-table"><thead><tr><th>Etapa</th><th style="text-align:right;width:120pt">Valor</th><th>Fundamentação</th></tr></thead><tbody>'
            for item in memoria:
                pad = "&nbsp;" * (item.get("nivel", 0) * 4)
                fund = ""
                if item.get("fundamentacao"):
                    f = item["fundamentacao"]
                    fund = f'{_esc(f.get("norma",""))} {_esc(f.get("artigo",""))}'
                valor = item.get("valor", "")
                html += f'<tr><td>{pad}{_esc(item.get("descricao",""))}</td><td style="text-align:right">{_esc(str(valor)) if valor else ""}</td><td>{fund}</td></tr>'
            html += "</tbody></table>"

        for av in c.get("avisos", []):
            html += f'<div class="aviso">⚠️ {_esc(av)}</div>'

    return html


def _secao_fundamentacao() -> str:
    return """
<h2 class="page-break">5. Fundamentação Legal</h2>
<table>
  <tr><th>Norma</th><th>Dispositivo</th><th>Descrição</th></tr>
  <tr><td>Lei 8.213/91</td><td>Art. 29</td><td>Período Básico de Cálculo (PBC)</td></tr>
  <tr><td>Lei 9.876/99</td><td>Art. 3º</td><td>Regra de transição do PBC — salários desde jul/1994</td></tr>
  <tr><td>EC 103/2019</td><td>Art. 15 a 20</td><td>Regras de transição para aposentadoria por TC</td></tr>
  <tr><td>EC 103/2019</td><td>Art. 26</td><td>Coeficiente 60% + 2% ao ano acima do mínimo</td></tr>
  <tr><td>RE 1.276.977 STF</td><td>Tema 1.102</td><td>Revisão da Vida Toda — salários anteriores a jul/1994</td></tr>
  <tr><td>Manual CJF</td><td>Res. 963/2025</td><td>Índices de correção monetária e juros de mora</td></tr>
  <tr><td>Decreto 20.910/32</td><td>Art. 1º</td><td>Prescrição quinquenal dos créditos previdenciários</td></tr>
  <tr><td>EC 113/2021</td><td>Art. 3º</td><td>SELIC como índice de juros a partir de jan/2022</td></tr>
</table>
"""


def _secao_conclusao(elegivel: bool, melhor: Optional[Dict], dp: Dict,
                     modo_revisao: bool = False, nb_ativo: Dict = None,
                     alertas: list = None) -> str:
    hoje = date.today().strftime("%d/%m/%Y")
    nome = dp.get("nome", "o segurado")
    tem_alertas = bool(alertas)

    if modo_revisao and elegivel and melhor:
        # ── MODO REVISÃO: NB ativo existe ──────────────────────────────────
        rmi = _fmt_brl(melhor.get("rmi", "0"))
        regra = melhor.get("nome_regra", "—")
        rmi_admin = _fmt_brl(nb_ativo.get("rmi", "0")) if nb_ativo and nb_ativo.get("rmi") else "não informada"
        concl = f"""Com base nos dados informados e nos cálculos realizados, identifica-se que
        <strong>{_esc(nome)}</strong> possui tese revisional plausível pela regra
        <strong>{_esc(regra)}</strong>, com RMI estimada de <strong>R$ {rmi}</strong>.

        <div class="aviso" style="margin:10pt 0;">
          <strong>IMPORTANTE — CASO DE REVISÃO:</strong> O segurado já possui benefício ativo
          (NB {_esc(nb_ativo.get('numero','—') if nb_ativo else '—')}), com RMI administrativa de
          R$ {rmi_admin}. A RMI estimada acima deve ser confrontada com a memória de cálculo
          administrativa do INSS antes de ser utilizada em petição revisional.
          A saída correta para este caso é <strong>revisão do benefício existente</strong>,
          não novo requerimento.
        </div>"""
    elif elegivel and melhor:
        # ── CÁLCULO INICIAL: sem NB ativo ──────────────────────────────────
        rmi = _fmt_brl(melhor.get("rmi", "0"))
        regra = melhor.get("nome_regra", "—")
        concl = f"""Com base nos dados informados e cálculos realizados, os requisitos para
        aposentadoria pela regra <strong>{_esc(regra)}</strong> aparentam estar preenchidos,
        com RMI estimada de <strong>R$ {rmi}</strong>.
        Recomenda-se a conferência dos dados com o CNIS atualizado e a memória de cálculo do INSS
        antes de protocolar requerimento."""
    else:
        concl = f"""Com base nos dados informados, <strong>{_esc(nome)}</strong> ainda não preenche
        todos os requisitos para a aposentadoria na data de referência informada.
        Os dados, cálculos e fundamentação acima representam a análise técnica da situação previdenciária
        conforme os insumos disponíveis."""

    # ── Nota metodológica (substitui "rigorosamente") ──────────────────
    nota_metodo = """Os cálculos foram realizados pelo Sistema SistPrev, seguindo a metodologia
  do Manual de Cálculos da Justiça Federal — Resolução CJF nº 963/2025. Os índices de correção
  e parâmetros legais são os mesmos utilizados pelos sistemas CECALC/TRF3 e Conta Fácil Prev/TRF4."""

    if tem_alertas:
        nota_metodo += """
  <br/><strong>Ressalva:</strong> Este relatório contém alertas de consistência (vide Seção de Alertas acima).
  Os resultados são estimativas baseadas nos dados informados e devem ser validados contra a documentação
  administrativa do caso antes de serem utilizados como prova técnica."""

    nota_metodo += """
  <br/><em>Os valores apresentados são estimativas calculadas com base nos dados disponíveis no momento
  da elaboração. Variações nos insumos (tempo reconhecido, salários de contribuição, períodos especiais)
  podem alterar significativamente o resultado final.</em>"""

    return f"""
<h2 class="page-break">6. Conclusão</h2>
<p style="margin-bottom:10pt;line-height:1.8;">{concl}</p>
<p style="margin-bottom:10pt;font-size:10pt;color:#6b7280;line-height:1.7;">
  {nota_metodo}
</p>
<div style="margin-top:40pt;text-align:center;border-top:1px solid #e5e7eb;padding-top:24pt;">
  <p>___________________________________________</p>
  <p><strong>Advogado(a) / Perito(a) Previdenciário(a)</strong></p>
  <p style="font-size:10pt;color:#6b7280;">{hoje}</p>
</div>
"""


def _secao_explicacao_revisao_cliente(dp: Dict, der, melhor: Dict, nb_ativo: Dict, elegivel: bool) -> str:
    """
    Seção em linguagem simples para o CLIENTE entender o que está acontecendo.

    Exemplo de saída:
    'Quando você se aposentou em 01/03/2015, o INSS calculou sua aposentadoria
     em R$ 2.000/mês. Mas o cálculo correto deveria ter resultado em R$ 3.000/mês.
     Isso significa que o INSS vem pagando R$ 1.000 a menos por mês desde a data
     em que a aposentadoria começou. Esse valor pode ser cobrado...'
    """
    nome = _esc(dp.get("nome", "o segurado"))
    dib = nb_ativo.get("dib", "—")
    rmi_admin_raw = nb_ativo.get("rmi")
    nb_num = _esc(nb_ativo.get("numero", "—"))
    especie = _esc(nb_ativo.get("especie", "—"))

    if not elegivel or not melhor:
        return f"""
<h2 class="page-break">📋 Explicação para o Cliente</h2>
<div style="background:#f0f9ff;border:2px solid #0284c7;border-radius:10px;padding:20pt;margin:14pt 0;font-size:11pt;line-height:1.9;">
  <p><strong>O que foi analisado:</strong></p>
  <p>O sistema revisou o benefício de aposentadoria de <strong>{nome}</strong>
  (NB {nb_num}, espécie {especie}), que está ativo desde <strong>{dib}</strong>.</p>
  <p><strong>Resultado da análise:</strong> Com base nos dados disponíveis, <u>não foi possível
  identificar uma regra de aposentadoria que gere valor superior ao benefício atual.</u>
  Isso não significa que não haja direito — pode haver períodos faltantes, salários divergentes
  ou vínculos não registrados que, após regularização no CNIS, alterem este resultado.</p>
  <p style="background:#fef3c7;padding:8pt 12pt;border-radius:6px;">
  <strong>Próximo passo:</strong> Conferir o CNIS completo, CTPS física e holerites para
  verificar se há períodos ou salários não registrados que poderiam mudar o cálculo.</p>
</div>"""

    rmi_calc = float(str(melhor.get("rmi", "0")).replace(",", "."))
    rmi_admin = float(str(rmi_admin_raw).replace(",", ".")) if rmi_admin_raw else 0.0
    diferenca = rmi_calc - rmi_admin if rmi_calc > rmi_admin else 0.0

    if diferenca <= 0:
        return f"""
<h2 class="page-break">📋 Explicação para o Cliente</h2>
<div style="background:#f0f9ff;border:2px solid #0284c7;border-radius:10px;padding:20pt;margin:14pt 0;font-size:11pt;line-height:1.9;">
  <p>O cálculo foi revisado com os dados do CNIS. O valor calculado (R$ {_fmt_brl(rmi_calc)}/mês)
  <strong>não supera</strong> o benefício que o INSS já paga (R$ {_fmt_brl(rmi_admin)}/mês).
  Não há diferença a recuperar por esta combinação de regra e dados.</p>
  <p style="background:#fef3c7;padding:8pt 12pt;border-radius:6px;">
  Isso pode mudar se houver períodos faltantes no CNIS ou salários divergentes.
  Verifique a CTPS e holerites.</p>
</div>"""

    # ── Há diferença positiva: gerar explicação didática ─────────────────
    # Cálculo de retroativos (prescrição quinquenal = 60 meses)
    from datetime import date as ddate
    hoje = ddate.today()
    try:
        if "/" in str(dib):
            p = str(dib).split("/")
            data_dib = ddate(int(p[2]), int(p[1]), int(p[0]))
        else:
            data_dib = ddate.fromisoformat(str(dib))
        meses_total = (hoje.year - data_dib.year) * 12 + (hoje.month - data_dib.month)
    except Exception:
        meses_total = 0

    meses_prescritos = max(0, meses_total - 60)
    meses_validos = min(meses_total, 60)
    retroativo_bruto = diferenca * meses_validos

    regra = _esc(melhor.get("nome_regra", "—"))
    tc = melhor.get("tempo_contribuicao", {})
    tc_txt = f"{tc.get('anos','?')} anos, {tc.get('meses','?')} meses" if tc else "—"

    return f"""
<h2 class="page-break">📋 Explicação para o Cliente</h2>
<div style="background:#f0f9ff;border:2px solid #0284c7;border-radius:10px;padding:20pt;margin:14pt 0;font-size:11pt;line-height:1.9;">

  <h3 style="color:#0369a1;font-size:13pt;margin-bottom:14pt;">O que aconteceu com a sua aposentadoria?</h3>

  <p>Quando <strong>{nome}</strong> se aposentou (NB {nb_num}), o benefício começou
  a ser pago em <strong>{dib}</strong>.</p>

  <p>O INSS calculou a aposentadoria e fixou a renda mensal em
  <strong style="color:#dc2626;">R$ {_fmt_brl(rmi_admin)}/mês</strong>.</p>

  <p>Após revisão técnica dos dados do CNIS, aplicando a regra
  <strong>{regra}</strong> com <strong>{tc_txt}</strong> de contribuição,
  o valor correto que deveria ter sido pago desde o início é
  <strong style="color:#059669;">R$ {_fmt_brl(rmi_calc)}/mês</strong>.</p>

  <div style="background:#fff;border:1px solid #bae6fd;border-radius:8px;padding:14pt;margin:14pt 0;">
    <table style="width:100%;font-size:11pt;border-collapse:collapse;">
      <tr><td style="padding:5pt 0;"><strong>O INSS pagou por mês:</strong></td>
          <td style="text-align:right;color:#dc2626;font-weight:700;">R$ {_fmt_brl(rmi_admin)}</td></tr>
      <tr style="border-top:1px solid #e0f2fe;"><td style="padding:5pt 0;"><strong>O correto seria:</strong></td>
          <td style="text-align:right;color:#059669;font-weight:700;">R$ {_fmt_brl(rmi_calc)}</td></tr>
      <tr style="border-top:2px solid #0284c7;"><td style="padding:5pt 0;"><strong>Diferença mensal (o que o INSS pagou a menos):</strong></td>
          <td style="text-align:right;color:#d97706;font-weight:800;font-size:13pt;">R$ {_fmt_brl(diferenca)}</td></tr>
    </table>
  </div>

  <h3 style="color:#0369a1;font-size:13pt;margin:14pt 0 10pt;">Quanto pode ser cobrado de volta?</h3>

  <p>O INSS deve a diferença de <strong>R$ {_fmt_brl(diferenca)}/mês</strong> desde {dib}.</p>
  <p>Porém, a lei (Art. 103, parágrafo único, Lei 8.213/91) diz que
  <strong>só podem ser cobrados os últimos 5 anos</strong> — isso se chama
  <em>prescrição quinquenal</em>. Parcelas com mais de 5 anos ficam prescritas
  (não podem mais ser cobradas).</p>

  <div style="background:#fff;border:1px solid #bae6fd;border-radius:8px;padding:14pt;margin:14pt 0;">
    <table style="width:100%;font-size:11pt;border-collapse:collapse;">
      <tr><td style="padding:5pt 0;">Meses desde que a aposentadoria começou:</td>
          <td style="text-align:right;">{meses_total} meses</td></tr>
      <tr style="border-top:1px solid #e0f2fe;">
          <td style="padding:5pt 0;color:#dc2626;">Meses prescritos (mais de 5 anos — já perdidos por lei):</td>
          <td style="text-align:right;color:#dc2626;">{meses_prescritos} meses</td></tr>
      <tr style="border-top:1px solid #e0f2fe;">
          <td style="padding:5pt 0;color:#059669;"><strong>Meses dentro do prazo (últimos 60 meses):</strong></td>
          <td style="text-align:right;color:#059669;font-weight:700;">{meses_validos} meses</td></tr>
      <tr style="border-top:2px solid #0284c7;background:#f0f9ff;">
          <td style="padding:6pt;"><strong>Retroativo estimado (sem correção):</strong><br>
          <small style="color:#6b7280;">R$ {_fmt_brl(diferenca)}/mês × {meses_validos} meses</small></td>
          <td style="text-align:right;font-weight:800;font-size:14pt;color:#0369a1;">R$ {_fmt_brl(retroativo_bruto)}</td></tr>
    </table>
  </div>

  <div style="background:#fef3c7;border-radius:8px;padding:10pt 14pt;">
    <strong>⚠ Atenção:</strong> O valor acima é uma <u>estimativa</u> sem correção monetária.
    O valor real, após atualização pelo INPC (até nov/2021) e SELIC (a partir de nov/2021,
    conforme EC 113/2021), será calculado pelo contador judicial se o processo for necessário.
    <br><br>
    <strong>Como funciona:</strong> Se o INSS não revisar administrativamente, seu advogado
    entrará com uma ação judicial pedindo: (1) a revisão do valor mensal para R$ {_fmt_brl(rmi_calc)},
    e (2) o pagamento do retroativo (os meses dentro do prazo de 5 anos), com correção.
    Esse pagamento é feito pelo INSS via RPV (pequeno valor) ou precatório, dependendo do total.
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários
# ─────────────────────────────────────────────────────────────────────────────

def _esc(s) -> str:
    return html_module.escape(str(s)) if s is not None else ""


def _fmt_brl(v) -> str:
    try:
        n = float(str(v).replace(",", "."))
        return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)


def _fmt_pct(v) -> str:
    try:
        n = float(str(v)) * 100
        return f"{n:.2f}%"
    except Exception:
        return str(v)


def _fmt_cpf(v: str) -> str:
    d = ''.join(c for c in str(v) if c.isdigit())
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return v or "—"


def _fmt_cnpj(v: str) -> str:
    d = ''.join(c for c in str(v) if c.isdigit())
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return v or "—"
