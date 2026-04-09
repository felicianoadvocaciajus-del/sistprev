"""
Gerador de Relatório Previdenciário em DOCX — Visual Law — Feliciano Advocacia.

Gera documento Word profissional com:
  - Identidade visual Feliciano Advocacia (azul #1a3c6e / #4F81BD)
  - Visual Law (tabelas, ícones textuais, destaques visuais)
  - Memória de cálculo
  - Score de Prontidão
  - TC nos Marcos Legais
  - Plano de Ação
  - Fundamentação Legal
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional
from io import BytesIO

from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml


# ── Cores Feliciano Advocacia ──
AZUL_ESCURO = RGBColor(0x1a, 0x3c, 0x6e)
AZUL_MEDIO = RGBColor(0x4F, 0x81, 0xBD)
AZUL_CLARO = RGBColor(0x36, 0x5F, 0x91)
VERDE = RGBColor(0x06, 0x5f, 0x46)
VERMELHO = RGBColor(0x99, 0x1b, 0x1b)
LARANJA = RGBColor(0xb4, 0x53, 0x09)
CINZA = RGBColor(0x6b, 0x72, 0x80)
BRANCO = RGBColor(0xFF, 0xFF, 0xFF)


def _set_cell_bg(cell, hex_color: str):
    """Define cor de fundo de uma célula."""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def _add_heading(doc, text, level=1):
    """Adiciona heading com estilo Feliciano."""
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        run.font.color.rgb = AZUL_ESCURO if level == 1 else AZUL_MEDIO
    return h


def _add_para(doc, text, bold=False, color=None, size=10, align=None, space_after=6):
    """Adiciona parágrafo formatado."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    if bold:
        run.font.bold = True
    if color:
        run.font.color.rgb = color
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def _fmt_brl(valor) -> str:
    """Formata valor para R$ brasileiro."""
    if valor is None:
        return "R$ 0,00"
    try:
        v = Decimal(str(valor))
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return f"R$ {valor}"


def gerar_docx_planejamento(
    segurado: Dict,
    planejamento: Dict,
    nome_advogado: Optional[str] = None,
) -> bytes:
    """
    Gera DOCX profissional de planejamento previdenciário.

    Returns:
        bytes do arquivo .docx
    """
    doc = Document()

    # ── Configurar estilos ──
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(10)

    for level in range(1, 4):
        hs = doc.styles[f'Heading {level}']
        hs.font.name = 'Calibri'
        hs.font.color.rgb = AZUL_ESCURO if level == 1 else AZUL_MEDIO

    # ── Margens ──
    for section in doc.sections:
        section.top_margin = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin = Cm(2.5)
        section.right_margin = Cm(2.5)

    dp = segurado.get("dados_pessoais", {})
    hoje = date.today().strftime("%d/%m/%Y")
    nome = dp.get("nome", "Segurado")
    tc = planejamento.get("tc_atual", {})
    score = planejamento.get("score_prontidao", {})
    marcos = planejamento.get("marcos_legais") or []
    projecoes = planejamento.get("projecoes") or []
    custo = planejamento.get("custo_beneficio") or []
    qualidade = planejamento.get("qualidade_segurado") or {}
    pensao = planejamento.get("pensao_projetada") or {}
    plano = planejamento.get("plano_acao") or []
    resumo = planejamento.get("resumo_executivo") or {}
    comp_sem = planejamento.get("competencias_sem_salario") or {}
    cenarios = planejamento.get("cenarios_vida") or []
    argumentos = planejamento.get("argumentos_cliente") or []

    alcancaveis = sorted(
        [p for p in projecoes if p.get("data_elegibilidade")],
        key=lambda p: p.get("meses_faltantes", 999)
    )
    melhor = alcancaveis[0] if alcancaveis else None

    # ═══════════════════════════════════════════════════════════════════════
    # CAPA
    # ═══════════════════════════════════════════════════════════════════════

    # Linha decorativa (simulada com tabela de 1 célula)
    _add_para(doc, "", size=6, space_after=0)
    _add_para(doc, "", size=6, space_after=0)

    p_logo = doc.add_paragraph()
    p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_logo = p_logo.add_run("FELICIANO ADVOCACIA")
    run_logo.font.size = Pt(28)
    run_logo.font.bold = True
    run_logo.font.color.rgb = AZUL_ESCURO
    run_logo.font.name = "Calibri"

    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_sub = p_sub.add_run("Assessoria Jurídica Previdenciária")
    run_sub.font.size = Pt(12)
    run_sub.font.color.rgb = AZUL_MEDIO
    run_sub.font.name = "Calibri"
    p_sub.paragraph_format.space_after = Pt(40)

    # Linha separadora
    p_line = doc.add_paragraph()
    p_line.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_line = p_line.add_run("━" * 60)
    run_line.font.color.rgb = AZUL_MEDIO
    run_line.font.size = Pt(8)
    p_line.paragraph_format.space_after = Pt(30)

    # Título do documento
    p_titulo = doc.add_paragraph()
    p_titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_t = p_titulo.add_run("PLANEJAMENTO PREVIDENCIÁRIO")
    run_t.font.size = Pt(22)
    run_t.font.bold = True
    run_t.font.color.rgb = AZUL_ESCURO
    p_titulo.paragraph_format.space_after = Pt(8)

    p_nome_cli = doc.add_paragraph()
    p_nome_cli.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_nc = p_nome_cli.add_run(nome.upper())
    run_nc.font.size = Pt(16)
    run_nc.font.bold = True
    run_nc.font.color.rgb = AZUL_MEDIO
    p_nome_cli.paragraph_format.space_after = Pt(30)

    # Quadro de dados na capa
    tabela_capa = doc.add_table(rows=4, cols=2)
    tabela_capa.alignment = WD_TABLE_ALIGNMENT.CENTER
    dados_capa = [
        ("CPF:", dp.get("cpf", "—")),
        ("Data de Nascimento:", dp.get("data_nascimento", "—")),
        ("NIT/PIS:", dp.get("nit", "—")),
        ("Data da Análise:", hoje),
    ]
    for i, (label, valor) in enumerate(dados_capa):
        cell_l = tabela_capa.cell(i, 0)
        cell_v = tabela_capa.cell(i, 1)
        cell_l.text = label
        cell_v.text = str(valor) if valor else "—"
        for p in cell_l.paragraphs:
            p.runs[0].font.bold = True
            p.runs[0].font.size = Pt(10)
            p.runs[0].font.color.rgb = AZUL_ESCURO
        for p in cell_v.paragraphs:
            p.runs[0].font.size = Pt(10)

    doc.add_page_break()

    # ═══════════════════════════════════════════════════════════════════════
    # 1. SCORE DE PRONTIDÃO PREVIDENCIÁRIA
    # ═══════════════════════════════════════════════════════════════════════

    if score:
        _add_heading(doc, "1. Score de Prontidão Previdenciária", level=1)

        score_val = score.get("score", 0)
        classif = score.get("classificacao", "").replace("_", " ")
        msg = score.get("mensagem", "")

        # Score grande
        p_score = doc.add_paragraph()
        p_score.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_s = p_score.add_run(f"{score_val}")
        run_s.font.size = Pt(48)
        run_s.font.bold = True
        cor_hex = score.get("cor", "#1a3c6e")
        try:
            run_s.font.color.rgb = RGBColor(int(cor_hex[1:3], 16), int(cor_hex[3:5], 16), int(cor_hex[5:7], 16))
        except Exception:
            run_s.font.color.rgb = AZUL_ESCURO
        run_s2 = p_score.add_run(" / 1000")
        run_s2.font.size = Pt(14)
        run_s2.font.color.rgb = CINZA

        p_classif = doc.add_paragraph()
        p_classif.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_cl = p_classif.add_run(classif)
        run_cl.font.size = Pt(14)
        run_cl.font.bold = True
        run_cl.font.color.rgb = AZUL_MEDIO

        _add_para(doc, msg, size=10, color=CINZA, align=WD_ALIGN_PARAGRAPH.CENTER)

        # Tabela de componentes
        comp = score.get("componentes", {})
        if comp:
            tabela_score = doc.add_table(rows=len(comp) + 1, cols=4)
            tabela_score.style = 'Light List Accent 1'
            tabela_score.alignment = WD_TABLE_ALIGNMENT.CENTER

            headers = ["Componente", "Pontos", "Máximo", "Detalhe"]
            for j, h in enumerate(headers):
                cell = tabela_score.cell(0, j)
                cell.text = h
                _set_cell_bg(cell, "1a3c6e")
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.color.rgb = BRANCO
                        r.font.bold = True
                        r.font.size = Pt(9)

            labels = {
                "tempo_contribuicao": "Tempo de Contribuição",
                "idade": "Idade",
                "carencia": "Carência",
                "qualidade_segurado": "Qualidade Segurado",
                "proximidade": "Proximidade",
                "valor_beneficio": "Valor Benefício",
            }
            for i, (key, c) in enumerate(comp.items()):
                row = i + 1
                tabela_score.cell(row, 0).text = labels.get(key, key)
                tabela_score.cell(row, 1).text = str(c.get("pontos", 0))
                tabela_score.cell(row, 2).text = str(c.get("maximo", 0))
                tabela_score.cell(row, 3).text = str(c.get("detalhe", ""))
                for j in range(4):
                    for p in tabela_score.cell(row, j).paragraphs:
                        for r in p.runs:
                            r.font.size = Pt(9)

        doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 2. RESUMO EXECUTIVO
    # ═══════════════════════════════════════════════════════════════════════

    if resumo:
        _add_heading(doc, "2. Resumo Executivo", level=1)

        campos_resumo = [
            ("SITUAÇÃO ATUAL", resumo.get("situacao_atual", "")),
            ("MELHOR CAMINHO", resumo.get("melhor_caminho", "")),
            ("AÇÃO IMEDIATA", resumo.get("acao_imediata", "")),
            ("PRÓXIMO PASSO", resumo.get("proximo_passo", "")),
        ]
        cores_bg = ["DBE5F1", "E2EFDA", "FFF2CC", "E8DAEF"]

        for (titulo, texto), cor_bg in zip(campos_resumo, cores_bg):
            tabela_r = doc.add_table(rows=1, cols=1)
            cell = tabela_r.cell(0, 0)
            p = cell.paragraphs[0]
            run_t = p.add_run(f"{titulo}\n")
            run_t.font.size = Pt(8)
            run_t.font.bold = True
            run_t.font.color.rgb = AZUL_ESCURO
            run_v = p.add_run(texto)
            run_v.font.size = Pt(10)
            _set_cell_bg(cell, cor_bg)
            doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. SITUAÇÃO PREVIDENCIÁRIA ATUAL
    # ═══════════════════════════════════════════════════════════════════════

    _add_heading(doc, "3. Situação Previdenciária Atual", level=1)

    # Tabela de dados do segurado
    tabela_sit = doc.add_table(rows=6, cols=2)
    tabela_sit.style = 'Light List Accent 1'
    dados_sit = [
        ("Nome:", nome),
        ("Tempo de Contribuição:", f"{tc.get('anos', 0)} anos, {tc.get('meses', 0)} meses e {tc.get('dias', 0)} dias"),
        ("Salário de Contribuição Projetado:", _fmt_brl(planejamento.get("salario_projetado", 0))),
        ("Qualidade de Segurado:", qualidade.get("status", "—")),
        ("Elegível Agora:", "SIM — Pode requerer hoje" if planejamento.get("elegiveis_agora") else "NÃO — Ainda não preenche os requisitos"),
        ("Melhor RMI Projetada:", _fmt_brl(planejamento.get("melhor_rmi", 0))),
    ]
    for i, (label, valor) in enumerate(dados_sit):
        tabela_sit.cell(i, 0).text = label
        tabela_sit.cell(i, 1).text = str(valor)
        for p in tabela_sit.cell(i, 0).paragraphs:
            for r in p.runs:
                r.font.bold = True
                r.font.size = Pt(10)
        for p in tabela_sit.cell(i, 1).paragraphs:
            for r in p.runs:
                r.font.size = Pt(10)

    # Fundamentação legal da contagem de TC
    _add_para(doc, (
        "Metodologia de contagem conforme legislação vigente: "
        "Empregado CLT/Avulso/Doméstico — TC em dias corridos do período (Art. 60, Decreto 3.048/99); "
        "Facultativo/CI/MEI — TC por competências com contribuição efetiva, 30 dias/mês (Art. 19-C, Decreto 10.410/2020); "
        "Contribuições abaixo do SM pós-EC 103/2019 NÃO contam (Art. 19-E, Decreto 3.048/99); "
        "Auxílio-doença intercalado conta como TC (Art. 60 §3º, Lei 8.213/91); "
        "Períodos concomitantes contados apenas uma vez; "
        "Indicadores CNIS (PREC-MENOR-MIN, IREC-INDPEND) excluem contribuições com pendência."
    ), size=8, color=CINZA)

    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 4. QUALIDADE DE SEGURADO
    # ═══════════════════════════════════════════════════════════════════════

    if qualidade:
        _add_heading(doc, "4. Qualidade de Segurado", level=1)

        status_qs = qualidade.get("status", "PERDIDA")
        icon = "ATIVA" if status_qs == "ATIVA" else "EM RISCO" if status_qs == "EM_RISCO" else "PERDIDA"
        _add_para(doc, f"Status: {icon}", bold=True, size=12,
                  color=VERDE if status_qs == "ATIVA" else LARANJA if status_qs == "EM_RISCO" else VERMELHO)
        _add_para(doc, qualidade.get("mensagem", ""))

        tabela_qs = doc.add_table(rows=1, cols=3)
        tabela_qs.style = 'Light List Accent 1'
        tabela_qs.cell(0, 0).text = f"Última contribuição: {qualidade.get('ultima_contribuicao', '—')}"
        tabela_qs.cell(0, 1).text = f"Período de graça: {qualidade.get('periodo_graca_meses', 0)} meses"
        tabela_qs.cell(0, 2).text = f"Perda em: {qualidade.get('data_perda_qualidade', '—')}"
        for j in range(3):
            for p in tabela_qs.cell(0, j).paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)

    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 5. TC NOS MARCOS LEGAIS
    # ═══════════════════════════════════════════════════════════════════════

    if marcos:
        _add_heading(doc, "5. Tempo de Contribuição nos Marcos Legais", level=1)
        _add_para(doc, "Análise do tempo acumulado em cada data-chave da legislação previdenciária.", color=CINZA, size=9)

        tabela_marcos = doc.add_table(rows=len(marcos) + 1, cols=5)
        tabela_marcos.style = 'Light List Accent 1'
        tabela_marcos.alignment = WD_TABLE_ALIGNMENT.CENTER

        headers_m = ["Marco Legal", "Data", "TC Acumulado", "Contribuições", "Análise"]
        for j, h in enumerate(headers_m):
            cell = tabela_marcos.cell(0, j)
            cell.text = h
            _set_cell_bg(cell, "1a3c6e")
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.color.rgb = BRANCO
                    r.font.bold = True
                    r.font.size = Pt(8)

        for i, m in enumerate(marcos):
            row = i + 1
            tabela_marcos.cell(row, 0).text = f"{m.get('sigla', '')} — {m.get('nome', '')}"
            tabela_marcos.cell(row, 1).text = str(m.get("data", ""))
            tabela_marcos.cell(row, 2).text = str(m.get("tc_texto", ""))
            tabela_marcos.cell(row, 3).text = str(m.get("contribuicoes", ""))
            tabela_marcos.cell(row, 4).text = str(m.get("observacao", ""))
            for j in range(5):
                for p in tabela_marcos.cell(row, j).paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(8)

    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 6. COMPETÊNCIAS SEM SALÁRIO
    # ═══════════════════════════════════════════════════════════════════════

    if comp_sem and comp_sem.get("total_problemas", 0) > 0:
        _add_heading(doc, "6. Competências sem Salário de Contribuição", level=1)
        _add_para(doc, comp_sem.get("mensagem", ""), bold=True, color=LARANJA)
        _add_para(doc, f"Impacto: {comp_sem.get('impacto', '')}", size=10)

        sem_sal = comp_sem.get("sem_salario", [])
        if sem_sal:
            competencias_texto = ", ".join([s.get("competencia", "") for s in sem_sal])
            _add_para(doc, f"Competências afetadas: {competencias_texto}", size=9, color=VERMELHO)
            if sem_sal:
                _add_para(doc, f"Empregador: {sem_sal[0].get('empregador', '—')}", size=9, color=CINZA)

    # ═══════════════════════════════════════════════════════════════════════
    # 7. LINHA DO TEMPO — REGRAS DE APOSENTADORIA
    # ═══════════════════════════════════════════════════════════════════════

    doc.add_page_break()
    _add_heading(doc, "7. Análise das Regras de Transição (EC 103/2019)", level=1)
    _add_para(doc, "Projeção de datas de aposentadoria considerando contribuição contínua.", color=CINZA, size=9)

    if projecoes:
        tabela_regras = doc.add_table(rows=len(projecoes) + 1, cols=5)
        tabela_regras.style = 'Light List Accent 1'
        tabela_regras.alignment = WD_TABLE_ALIGNMENT.CENTER

        headers_r = ["Regra", "Data Prevista", "Tempo Faltando", "RMI Estimada", "Status"]
        for j, h in enumerate(headers_r):
            cell = tabela_regras.cell(0, j)
            cell.text = h
            _set_cell_bg(cell, "1a3c6e")
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.color.rgb = BRANCO
                    r.font.bold = True
                    r.font.size = Pt(8)

        sorted_proj = sorted(projecoes, key=lambda p: p.get("meses_faltantes") or 9999)
        for i, proj in enumerate(sorted_proj):
            row = i + 1
            is_melhor = i == 0 and proj.get("data_elegibilidade")
            tabela_regras.cell(row, 0).text = (">>> " if is_melhor else "") + str(proj.get("regra", ""))
            tabela_regras.cell(row, 1).text = str(proj.get("data_elegibilidade", "—"))
            tabela_regras.cell(row, 2).text = str(proj.get("texto_faltante", "—"))
            tabela_regras.cell(row, 3).text = str(proj.get("rmi_formatada", "—"))
            tabela_regras.cell(row, 4).text = "Alcançável" if proj.get("data_elegibilidade") else "Não alcançável"

            if is_melhor:
                for j in range(5):
                    _set_cell_bg(tabela_regras.cell(row, j), "DBE5F1")

            for j in range(5):
                for p in tabela_regras.cell(row, j).paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(8)
                        if is_melhor:
                            r.font.bold = True

    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 8. CUSTO-BENEFÍCIO (ROI)
    # ═══════════════════════════════════════════════════════════════════════

    if custo:
        _add_heading(doc, "8. Análise de Custo-Benefício — Retorno sobre Investimento", level=1)

        ev = planejamento.get("expectativa_vida", {})
        ev_anos = ev.get("anos", 76.6)
        _add_para(doc, f"Expectativa de vida IBGE 2024: {ev_anos} anos. Análise do retorno financeiro de cada modalidade de contribuição.", color=CINZA, size=9)

        for cb in custo:
            _add_heading(doc, cb.get("regra", ""), level=2)

            info_text = (
                f"Data: {cb.get('data_elegibilidade', '—')} | "
                f"Idade: {cb.get('idade_aposentadoria', 0):.1f} anos | "
                f"Meses recebendo: {int(cb.get('meses_recebendo', 0))} | "
                f"Total recebido: {_fmt_brl(cb.get('total_recebido', 0))}"
            )
            _add_para(doc, info_text, size=9, color=AZUL_ESCURO)

            mods = cb.get("modalidades", [])
            if mods:
                tabela_roi = doc.add_table(rows=len(mods) + 1, cols=7)
                tabela_roi.style = 'Light List Accent 1'

                headers_roi = ["Modalidade", "Alíquota", "Contrib/mês", "Total Pago", "Lucro", "ROI", "Vale?"]
                for j, h in enumerate(headers_roi):
                    cell = tabela_roi.cell(0, j)
                    cell.text = h
                    _set_cell_bg(cell, "1a3c6e")
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.font.color.rgb = BRANCO
                            r.font.bold = True
                            r.font.size = Pt(8)

                for mi, m in enumerate(mods):
                    row = mi + 1
                    tabela_roi.cell(row, 0).text = str(m.get("modalidade", ""))
                    tabela_roi.cell(row, 1).text = f"{m.get('aliquota_pct', 0)}%"
                    tabela_roi.cell(row, 2).text = _fmt_brl(m.get("contribuicao_mensal", 0))
                    tabela_roi.cell(row, 3).text = _fmt_brl(m.get("total_pago_ate_apos", 0))
                    tabela_roi.cell(row, 4).text = _fmt_brl(m.get("lucro_liquido", 0))
                    tabela_roi.cell(row, 5).text = f"{m.get('roi_percentual', 0)}%"
                    tabela_roi.cell(row, 6).text = "SIM" if m.get("vale_a_pena") else "NÃO"

                    cor_bg = "E2EFDA" if m.get("vale_a_pena") else "FCE4EC"
                    for j in range(7):
                        _set_cell_bg(tabela_roi.cell(row, j), cor_bg)
                        for p in tabela_roi.cell(row, j).paragraphs:
                            for r in p.runs:
                                r.font.size = Pt(8)

            doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 9. CENÁRIOS DE CONTRIBUIÇÃO
    # ═══════════════════════════════════════════════════════════════════════

    if cenarios:
        doc.add_page_break()
        _add_heading(doc, "9. Cenários de Contribuição — Comparativo com Valores", level=1)

        tabela_cen = doc.add_table(rows=len(cenarios) + 1, cols=5)
        tabela_cen.style = 'Light List Accent 1'

        headers_cen = ["Cenário", "Custo/mês", "Custo/ano", "Total até aposentar", "Impacto na RMI"]
        for j, h in enumerate(headers_cen):
            cell = tabela_cen.cell(0, j)
            cell.text = h
            _set_cell_bg(cell, "1a3c6e")
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.color.rgb = BRANCO
                    r.font.bold = True
                    r.font.size = Pt(8)

        for i, cv in enumerate(cenarios):
            row = i + 1
            nome_cen = cv.get("nome", cv.get("cenario", ""))
            tabela_cen.cell(row, 0).text = nome_cen
            tabela_cen.cell(row, 1).text = _fmt_brl(cv.get("monthly_cost", cv.get("custo_mensal", 0)))
            tabela_cen.cell(row, 2).text = _fmt_brl(cv.get("annual_cost", cv.get("custo_anual", 0)))
            tabela_cen.cell(row, 3).text = _fmt_brl(cv.get("total_cost_until_retirement", cv.get("custo_total", 0)))
            rmi_impact = cv.get("impact_on_rmi", cv.get("impacto_rmi", "—"))
            tabela_cen.cell(row, 4).text = str(rmi_impact)
            for j in range(5):
                for p in tabela_cen.cell(row, j).paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(8)

    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 10. PENSÃO POR MORTE
    # ═══════════════════════════════════════════════════════════════════════

    if pensao:
        _add_heading(doc, "10. Pensão por Morte — Projeção para Dependentes", level=1)
        _add_para(doc, pensao.get("mensagem", ""), size=10)

        cen_pensao = pensao.get("cenarios", [])
        if cen_pensao:
            tabela_pen = doc.add_table(rows=len(cen_pensao) + 1, cols=3)
            tabela_pen.style = 'Light List Accent 1'

            for j, h in enumerate(["Dependentes", "Cota (%)", "Valor Mensal"]):
                cell = tabela_pen.cell(0, j)
                cell.text = h
                _set_cell_bg(cell, "1a3c6e")
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.color.rgb = BRANCO
                        r.font.bold = True
                        r.font.size = Pt(9)

            for i, c in enumerate(cen_pensao):
                row = i + 1
                tabela_pen.cell(row, 0).text = f"{c.get('dependentes', 0)} dependente(s)"
                tabela_pen.cell(row, 1).text = f"{c.get('cota_pct', 0)}%"
                tabela_pen.cell(row, 2).text = str(c.get("valor_formatado", _fmt_brl(c.get("valor", 0))))
                for j in range(3):
                    for p in tabela_pen.cell(row, j).paragraphs:
                        for r in p.runs:
                            r.font.size = Pt(9)

    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 11. PLANO DE AÇÃO
    # ═══════════════════════════════════════════════════════════════════════

    if plano:
        doc.add_page_break()
        _add_heading(doc, "11. Plano de Ação — Próximos Passos", level=1)

        for p_acao in plano:
            numero = p_acao.get("numero", "")
            titulo_p = p_acao.get("titulo", "")
            desc = p_acao.get("descricao", "")
            prazo = p_acao.get("prazo", "")
            urgencia = p_acao.get("urgencia", "")

            _add_heading(doc, f"Passo {numero}: {titulo_p}", level=2)
            _add_para(doc, desc, size=10)

            urg_color = VERMELHO if urgencia == "ALTA" else LARANJA if urgencia == "MEDIA" else VERDE
            p_urg = doc.add_paragraph()
            run_prazo = p_urg.add_run(f"Prazo: {prazo}")
            run_prazo.font.size = Pt(9)
            run_prazo.font.color.rgb = CINZA
            p_urg.add_run("   |   ")
            run_urg = p_urg.add_run(f"Urgência: {urgencia}")
            run_urg.font.size = Pt(9)
            run_urg.font.bold = True
            run_urg.font.color.rgb = urg_color

    # ═══════════════════════════════════════════════════════════════════════
    # 12. ARGUMENTOS PARA O CLIENTE
    # ═══════════════════════════════════════════════════════════════════════

    if argumentos:
        _add_heading(doc, "12. Argumentos para Apresentação ao Cliente", level=1)
        for i, arg in enumerate(argumentos):
            _add_para(doc, f"{i+1}. {arg}", size=10)

    # ═══════════════════════════════════════════════════════════════════════
    # 13. FUNDAMENTAÇÃO LEGAL
    # ═══════════════════════════════════════════════════════════════════════

    doc.add_page_break()
    _add_heading(doc, "13. Fundamentação Legal", level=1)

    leis = [
        ("EC 103/2019", "Art. 15", "Regra de Transição — Sistema de Pontos (idade + TC)"),
        ("EC 103/2019", "Art. 16", "Regra de Transição — Idade Mínima Progressiva"),
        ("EC 103/2019", "Art. 17", "Regra de Transição — Pedágio 50% com Fator Previdenciário"),
        ("EC 103/2019", "Art. 20", "Regra de Transição — Pedágio 100% com Idade Mínima"),
        ("EC 103/2019", "Art. 19", "Aposentadoria por Idade (Regra Permanente)"),
        ("Lei 8.213/91", "Art. 29", "Período Básico de Cálculo e Salário de Benefício"),
        ("Lei 8.213/91", "Art. 25", "Carência — 180 meses de contribuição"),
        ("Lei 8.213/91", "Art. 15", "Qualidade de segurado e períodos de graça"),
        ("Decreto 3.048/99", "Art. 11", "Segurado facultativo — recolhimento voluntário"),
        ("LC 123/2006", "Art. 18-A", "MEI — alíquota reduzida de 5% (não conta para TC)"),
    ]

    tabela_leis = doc.add_table(rows=len(leis) + 1, cols=3)
    tabela_leis.style = 'Light List Accent 1'

    for j, h in enumerate(["Norma", "Dispositivo", "Aplicação"]):
        cell = tabela_leis.cell(0, j)
        cell.text = h
        _set_cell_bg(cell, "1a3c6e")
        for p in cell.paragraphs:
            for r in p.runs:
                r.font.color.rgb = BRANCO
                r.font.bold = True
                r.font.size = Pt(9)

    for i, (norma, art, desc) in enumerate(leis):
        tabela_leis.cell(i + 1, 0).text = norma
        tabela_leis.cell(i + 1, 1).text = art
        tabela_leis.cell(i + 1, 2).text = desc
        for j in range(3):
            for p in tabela_leis.cell(i + 1, j).paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)

    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 14. ANÁLISE DE ATIVIDADE ESPECIAL POR EMPREGADOR
    # ═══════════════════════════════════════════════════════════════════════

    analise_esp = planejamento.get("analise_especial", [])
    if analise_esp:
        _add_heading(doc, "14. Análise de Atividade Especial por Empregador", level=1)
        _add_para(doc, (
            "O sistema analisou automaticamente cada empregador do CNIS e identificou "
            "possíveis atividades especiais (insalubridade/periculosidade) com base em padrões "
            "conhecidos de CNAE e razão social. A conversão de tempo especial para comum "
            "utiliza fator de 1,4 (homem) ou 1,2 (mulher) — Art. 57 e 58, Lei 8.213/91."
        ), size=10, color=CINZA)

        tabela_esp = doc.add_table(rows=len(analise_esp) + 1, cols=5)
        tabela_esp.style = 'Light List Accent 1'
        for j, h in enumerate(["Empregador", "Período", "Probabilidade", "Agentes Prováveis", "Recomendação"]):
            cell = tabela_esp.cell(0, j)
            cell.text = h
            _set_cell_bg(cell, "b45309")
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.color.rgb = BRANCO
                    r.font.bold = True
                    r.font.size = Pt(8)

        for i, ae in enumerate(analise_esp):
            tabela_esp.cell(i + 1, 0).text = ae.get("empregador", "—")
            periodo = f"{ae.get('data_inicio', '—')} a {ae.get('data_fim', 'atual')}"
            tabela_esp.cell(i + 1, 1).text = periodo
            tabela_esp.cell(i + 1, 2).text = ae.get("probabilidade", "—")
            agentes = ae.get("agentes_provaveis", [])
            tabela_esp.cell(i + 1, 3).text = ", ".join(agentes) if agentes else "—"
            tabela_esp.cell(i + 1, 4).text = ae.get("recomendacao", "—")
            for j in range(5):
                for p in tabela_esp.cell(i + 1, j).paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(8)
            # Highlight high probability
            prob = ae.get("probabilidade", "")
            if prob == "ALTA":
                _set_cell_bg(tabela_esp.cell(i + 1, 2), "fef2f2")

        # Jurisprudências consolidadas
        juris_total = []
        for ae in analise_esp:
            for j in ae.get("jurisprudencias", []):
                key = f"{j.get('tipo', '')}_{j.get('numero', '')}"
                if key not in [f"{x.get('tipo','')}_{x.get('numero','')}" for x in juris_total]:
                    juris_total.append(j)

        if juris_total:
            _add_heading(doc, "14.1 Jurisprudência Consolidada Aplicável", level=2)
            _add_para(doc, (
                f"Foram identificadas {len(juris_total)} referências jurisprudenciais consolidadas "
                "com alto grau de confiabilidade (≥95%), aplicáveis aos empregadores analisados. "
                "Todas as referências são de jurisprudência pacificada (Súmulas TNU, Temas STJ/STF "
                "com repercussão geral ou recurso repetitivo)."
            ), size=10, color=CINZA)

            for j in juris_total:
                tipo = (j.get("tipo", "").replace("_", " ") + " " + j.get("numero", "")).strip()
                tribunal = j.get("tribunal", "")
                p_titulo = doc.add_paragraph()
                run_t = p_titulo.add_run(f"📚 {tipo} ({tribunal})")
                run_t.font.size = Pt(10)
                run_t.font.bold = True
                run_t.font.color.rgb = RGBColor(0x1E, 0x40, 0xAF)

                if j.get("data_julgamento"):
                    _add_para(doc, f"Julgado em {j['data_julgamento']}", size=8, color=CINZA)

                ementa = j.get("ementa", "")
                if ementa:
                    _add_para(doc, f"Ementa: {ementa}", size=9)

                aplic = j.get("aplicabilidade", "")
                if aplic:
                    p_aplic = doc.add_paragraph()
                    run_a = p_aplic.add_run(f"➜ Aplicabilidade ao caso: {aplic}")
                    run_a.font.size = Pt(9)
                    run_a.font.italic = True
                    run_a.font.color.rgb = RGBColor(0x06, 0x5F, 0x46)

                doc.add_paragraph()  # Espaçamento

        doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 15. ANÁLISE DE REVISÃO DO BENEFÍCIO
    # ═══════════════════════════════════════════════════════════════════════

    analise_rev = planejamento.get("analise_revisao", {})
    if analise_rev.get("beneficio_ativo"):
        secnum = "15" if analise_esp else "14"
        _add_heading(doc, f"{secnum}. Análise de Possibilidade de Revisão", level=1)
        _add_para(doc, (
            f"O segurado possui benefício ativo ({analise_rev.get('especie', '')}). "
            f"Foi realizada análise automática de {len(analise_rev.get('revisoes_possiveis', []))} "
            "tipos de revisão conforme legislação vigente."
        ), size=10, color=CINZA)

        # Decadência
        dec = analise_rev.get("decadencia", {})
        if dec:
            cor_dec = VERDE if dec.get("dentro_prazo") else VERMELHO
            _add_para(doc, dec.get("mensagem", ""), size=10, bold=True, color=cor_dec)

        # Tabela de revisões
        revisoes = analise_rev.get("revisoes_possiveis", [])
        if revisoes:
            tabela_rev = doc.add_table(rows=len(revisoes) + 1, cols=5)
            tabela_rev.style = 'Light List Accent 1'
            for j, h in enumerate(["Revisão", "Aplicável", "Viável", "Impacto", "Análise"]):
                cell = tabela_rev.cell(0, j)
                cell.text = h
                _set_cell_bg(cell, "7c3aed")
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.color.rgb = BRANCO
                        r.font.bold = True
                        r.font.size = Pt(8)

            for i, rev in enumerate(revisoes):
                tabela_rev.cell(i + 1, 0).text = rev.get("tipo", "—")
                tabela_rev.cell(i + 1, 1).text = "SIM" if rev.get("aplicavel") else "NÃO"
                tabela_rev.cell(i + 1, 2).text = "SIM" if rev.get("viavel") else "NÃO"
                tabela_rev.cell(i + 1, 3).text = rev.get("impacto_estimado", "—")
                tabela_rev.cell(i + 1, 4).text = rev.get("analise", "—")
                for j in range(5):
                    for p in tabela_rev.cell(i + 1, j).paragraphs:
                        for r in p.runs:
                            r.font.size = Pt(8)
                if rev.get("viavel"):
                    _set_cell_bg(tabela_rev.cell(i + 1, 2), "f0fdf4")

        if analise_rev.get("recomendacao_geral"):
            _add_para(doc, analise_rev["recomendacao_geral"], size=10, bold=True, color=AZUL_ESCURO)

        doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # 16. MEMÓRIA DE CÁLCULO
    # ═══════════════════════════════════════════════════════════════════════

    memoria = planejamento.get("memoria_calculo", {})
    if memoria.get("linhas"):
        secnum_mc = "16"
        _add_heading(doc, f"{secnum_mc}. Memória de Cálculo — Correção Monetária", level=1)
        _add_para(doc, (
            f"Tabela com {memoria.get('total_contribuicoes', 0)} contribuições corrigidas pelo INPC "
            f"até a DER. {memoria.get('fundamentacao', '')}"
        ), size=10, color=CINZA)

        # Resumo de médias
        _add_para(doc, f"Média dos 80% maiores: {_fmt_brl(memoria.get('media_80_maiores', '0'))}", size=10, bold=True)
        _add_para(doc, f"Média 100% (EC 103/2019): {_fmt_brl(memoria.get('media_100', '0'))}", size=10)

        descarte = memoria.get("descarte", {})
        if descarte.get("aplicado"):
            _add_para(doc, (
                f"Descarte automático aplicado: {descarte.get('total_descartados', 0)} contribuições descartadas. "
                f"Economia mensal: {_fmt_brl(descarte.get('economia_mensal', '0'))}. "
                f"Fundamentação: {descarte.get('fundamentacao', 'Art. 26 §6 EC 103/2019')}"
            ), size=10, bold=True, color=VERDE)

        # Tabela (primeiras 50 linhas)
        linhas = memoria.get("linhas", [])[:50]
        if linhas:
            tabela_mc = doc.add_table(rows=len(linhas) + 1, cols=6)
            tabela_mc.style = 'Light List Accent 1'
            for j, h in enumerate(["Competência", "Empregador", "Sal. Original", "Índice", "Sal. Corrigido", "Status"]):
                cell = tabela_mc.cell(0, j)
                cell.text = h
                _set_cell_bg(cell, "1a3c6e")
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.color.rgb = BRANCO
                        r.font.bold = True
                        r.font.size = Pt(7)

            for i, l in enumerate(linhas):
                tabela_mc.cell(i + 1, 0).text = l.get("competencia", "")
                emp = l.get("vinculo_nome", "")
                tabela_mc.cell(i + 1, 1).text = emp[:25] if emp else "—"
                tabela_mc.cell(i + 1, 2).text = _fmt_brl(l.get("salario_original", "0"))
                try:
                    idx = float(l.get("indice_correcao", "1"))
                    tabela_mc.cell(i + 1, 3).text = f"{idx:.4f}"
                except:
                    tabela_mc.cell(i + 1, 3).text = str(l.get("indice_correcao", ""))
                tabela_mc.cell(i + 1, 4).text = _fmt_brl(l.get("salario_corrigido", "0"))
                status = "Descartado" if l.get("descartado") else ("Teto" if l.get("limitado_teto") else "OK")
                tabela_mc.cell(i + 1, 5).text = status
                for j in range(6):
                    for p in tabela_mc.cell(i + 1, j).paragraphs:
                        for r in p.runs:
                            r.font.size = Pt(7)
                if l.get("descartado"):
                    _set_cell_bg(tabela_mc.cell(i + 1, 5), "fef2f2")

            if len(memoria.get("linhas", [])) > 50:
                _add_para(doc, f"... e mais {len(memoria['linhas']) - 50} contribuições.", size=9, color=CINZA)

        doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # CONCLUSÃO E RECOMENDAÇÃO FINAL
    # ═══════════════════════════════════════════════════════════════════════

    _add_heading(doc, "Conclusão e Recomendação Final", level=1)

    recomendacao = planejamento.get("recomendacao", "")
    _add_para(doc, recomendacao, size=11, bold=True, color=AZUL_ESCURO)

    _add_para(doc, (
        f"Com base na análise completa do histórico previdenciário de {nome}, "
        f"conforme legislação vigente (EC 103/2019, Lei 8.213/91), conclui-se que:"
    ), size=10)

    tc_texto = f"{tc.get('anos', 0)} anos, {tc.get('meses', 0)} meses e {tc.get('dias', 0)} dias"
    conclusoes = [
        f"O tempo de contribuição atual apurado é de {tc_texto}.",
        f"{'O segurado já é elegível para requerer aposentadoria.' if planejamento.get('elegiveis_agora') else 'O segurado ainda não preenche todos os requisitos.'}",
        "Para garantir a elegibilidade no prazo projetado, é essencial manter as contribuições mensais em dia, sem interrupções.",
        "Em caso de desemprego, recomenda-se o recolhimento como Segurado Facultativo (alíquota 20% sobre o salário-mínimo) para não perder o tempo de contribuição em curso.",
        "Os valores da RMI são estimativas baseadas nos salários atuais. Variações salariais e reajustes do teto podem alterar estes valores.",
    ]

    for c in conclusoes:
        p = doc.add_paragraph(style='List Bullet')
        run = p.add_run(c)
        run.font.size = Pt(10)

    doc.add_paragraph()
    doc.add_paragraph()

    # ═══════════════════════════════════════════════════════════════════════
    # ASSINATURA
    # ═══════════════════════════════════════════════════════════════════════

    p_line2 = doc.add_paragraph()
    p_line2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_line2 = p_line2.add_run("━" * 40)
    run_line2.font.color.rgb = AZUL_MEDIO
    run_line2.font.size = Pt(8)

    adv_nome = nome_advogado or "Advogado(a) / Consultor(a) Previdenciário(a)"
    p_adv = doc.add_paragraph()
    p_adv.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_adv = p_adv.add_run(adv_nome)
    run_adv.font.size = Pt(12)
    run_adv.font.bold = True
    run_adv.font.color.rgb = AZUL_ESCURO

    p_data = doc.add_paragraph()
    p_data.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_data = p_data.add_run(hoje)
    run_data.font.size = Pt(10)
    run_data.font.color.rgb = CINZA

    p_rodape = doc.add_paragraph()
    p_rodape.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_rod = p_rodape.add_run("Documento gerado pelo SistPrev — Cálculos conforme Lei 8.213/91, EC 103/2019 e CJF Res. 963/2025")
    run_rod.font.size = Pt(8)
    run_rod.font.color.rgb = CINZA
    run_rod.font.italic = True

    # ── Salvar em bytes ──
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
