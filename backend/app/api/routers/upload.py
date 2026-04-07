"""
Rotas de upload de documentos PDF.
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Form

from ..schemas import ParseCNISResponse, SeguradoSchema, DadosPessoaisSchema, VinculoSchema, ContribuicaoSchema, BeneficioAnteriorSchema
from ...services.upload_service import UploadService
from ...domain.models.segurado import Segurado

import logging
_logger = logging.getLogger("sistprev.upload")

router = APIRouter(prefix="/upload", tags=["Upload de Documentos"])


def _extrair_texto_ocr_upload(caminho_pdf: str, nome_arquivo: str) -> str:
    """Extrai texto via OCR para endpoints de upload."""
    try:
        from ...parsers.pipeline.ocr_engine import extract_document
        _logger.info(f"Iniciando OCR para: {nome_arquivo}")
        doc_result = extract_document(caminho_pdf, filename=nome_arquivo)
        if doc_result.full_text.strip():
            _logger.info(f"OCR extraiu {len(doc_result.full_text)} caracteres de {nome_arquivo}")
            return doc_result.full_text
        _logger.warning(f"OCR nao extraiu texto de {nome_arquivo}")
    except ImportError as e:
        _logger.warning(f"Dependencias OCR nao instaladas: {e}")
        # Fallback: tentar pytesseract direto
        try:
            return _ocr_fallback_direto(caminho_pdf)
        except Exception:
            pass
    except Exception as e:
        _logger.warning(f"Erro OCR pipeline: {e}")
        # Fallback direto
        try:
            return _ocr_fallback_direto(caminho_pdf)
        except Exception:
            pass
    return ""


def _ocr_fallback_direto(caminho_pdf: str) -> str:
    """OCR fallback direto com pytesseract + pdf2image, sem pipeline."""
    import pytesseract
    from pdf2image import convert_from_path

    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    poppler_path = r'C:\Program Files\poppler\poppler-24.08.0\Library\bin'

    _logger.info("Usando OCR fallback direto (pytesseract + pdf2image)")
    images = convert_from_path(caminho_pdf, poppler_path=poppler_path, dpi=300)
    texto_total = ""
    for i, img in enumerate(images):
        texto = pytesseract.image_to_string(img, lang='por')
        texto_total += texto + "\n"
        _logger.info(f"  Pagina {i+1}: {len(texto)} caracteres")
    return texto_total


@router.post("/cnis", response_model=ParseCNISResponse)
async def upload_cnis(arquivo: UploadFile = File(..., description="PDF do CNIS")):
    """
    Faz upload do CNIS em PDF e extrai os dados estruturados.
    Retorna o segurado com vínculos e contribuições prontos para cálculo.
    """
    import logging
    logger = logging.getLogger("sistprev.upload")
    logger.info(f"Upload CNIS recebido: {arquivo.filename} ({arquivo.content_type})")

    if not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(conteudo) > 20 * 1024 * 1024:  # 20 MB
        raise HTTPException(status_code=400, detail="Arquivo muito grande (máximo 20 MB).")

    import io
    segurado, resultado = UploadService.processar_cnis(
        io.BytesIO(conteudo), arquivo.filename
    )

    if not resultado.sucesso or segurado is None:
        return ParseCNISResponse(
            sucesso=False,
            avisos=resultado.avisos,
            erros=resultado.erros,
        )

    schema = _segurado_to_schema(segurado)

    # Serializar benefícios detectados
    beneficios_serial = []
    for b in resultado.beneficios:
        beneficios_serial.append({
            "especie": b.especie,
            "especie_codigo": b.especie_codigo,
            "data_inicio": b.data_inicio.strftime("%d/%m/%Y") if b.data_inicio else None,
            "situacao": b.situacao,
        })

    # Análise especial de TODOS os vínculos do CNIS
    analise_vinculos = _analisar_vinculos_especial_completo(
        [(v.empregador_nome, v.empregador_cnpj, None, None,
          v.data_inicio.strftime("%d/%m/%Y"),
          v.data_fim.strftime("%d/%m/%Y") if v.data_fim else None)
         for v in segurado.vinculos],
        origem="cnis",
    )

    return ParseCNISResponse(
        sucesso=True,
        segurado=schema,
        avisos=resultado.avisos,
        erros=resultado.erros,
        beneficios=beneficios_serial if beneficios_serial else None,
        analise_especial=analise_vinculos if analise_vinculos else None,
    )


@router.post("/carta-concessao")
async def upload_carta_concessao(arquivo: UploadFile = File(...)):
    """
    Faz upload da Carta de Concessão e extrai DIB, RMI, espécie e demais dados.
    """
    if not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    import io
    resultado, aviso = UploadService.processar_carta_concessao(
        io.BytesIO(conteudo), arquivo.filename
    )

    if resultado is None:
        return {
            "sucesso": False,
            "erro": f"Não foi possível extrair dados da Carta de Concessão. {aviso}".strip(),
            "avisos": [aviso] if aviso else [],
        }

    b = resultado.beneficio
    return {
        "sucesso": True,
        "numero_beneficio": b.numero_beneficio,
        "especie": b.especie,
        "descricao_especie": b.descricao_especie,
        "dib": b.dib.strftime("%d/%m/%Y") if b.dib else None,
        "dip": b.dip.strftime("%d/%m/%Y") if b.dip else None,
        "dcb": b.dcb.strftime("%d/%m/%Y") if b.dcb else None,
        "rmi": str(b.rmi) if b.rmi else None,
        "salario_beneficio": str(b.salario_beneficio) if b.salario_beneficio else None,
        "fator_previdenciario": str(b.fator_previdenciario) if b.fator_previdenciario else None,
        "coeficiente": str(b.coeficiente) if b.coeficiente else None,
        "nome_segurado": b.nome_segurado,
        "cpf": b.cpf,
        "avisos": resultado.avisos,
    }


@router.post("/ctps")
async def upload_ctps(arquivo: UploadFile = File(...)):
    """
    Faz upload da CTPS Digital e extrai os vínculos de trabalho.
    Já inclui análise de atividade especial por cargo/empregador.
    """
    if not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF são aceitos.")

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    import io
    resultado, aviso = UploadService.processar_ctps(
        io.BytesIO(conteudo), arquivo.filename
    )

    if resultado is None:
        return {
            "sucesso": False,
            "erro": f"Não foi possível extrair dados da CTPS. {aviso}".strip(),
            "avisos": [aviso] if aviso else [],
        }

    vinculos_serializados = _analisar_vinculos_especial_completo(
        [(v.empregador_nome, v.empregador_cnpj, v.cargo, v.cbo,
          v.data_admissao.strftime("%d/%m/%Y") if v.data_admissao else None,
          v.data_demissao.strftime("%d/%m/%Y") if v.data_demissao else None)
         for v in resultado.vinculos],
        origem="ctps",
    )

    return {
        "sucesso": True,
        "nome": resultado.nome,
        "cpf": resultado.cpf,
        "pis_pasep": resultado.pis_pasep,
        "vinculos": vinculos_serializados,
        "avisos": resultado.avisos,
    }


@router.post("/ppp")
async def upload_ppp(arquivo: UploadFile = File(...)):
    """
    Faz upload do PPP (Perfil Profissiografico Previdenciario).
    Extrai agentes nocivos, intensidades, EPI/EPC, periodos de exposicao.
    Cruza com dados do CNIS/CTPS para fortalecer a analise especial.
    """
    if not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF sao aceitos.")

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    import io, tempfile, os
    # Salvar em arquivo temporario para o parser
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(conteudo)
    tmp.close()

    try:
        from ...parsers.ppp.parser import parsear_ppp_pdf

        # Tentar parsing direto
        resultado = parsear_ppp_pdf(tmp.name)

        # Se falhou, tentar com OCR
        if not resultado.sucesso:
            texto_ocr = _extrair_texto_ocr_upload(tmp.name, arquivo.filename)
            if texto_ocr.strip():
                resultado = parsear_ppp_pdf(tmp.name, texto_ocr=texto_ocr)

        if not resultado.sucesso:
            return {
                "sucesso": False,
                "erro": resultado.erros[0] if resultado.erros else "Nao foi possivel extrair dados do PPP",
                "avisos": resultado.avisos,
            }

        # Buscar jurisprudencia para os agentes encontrados
        juris_serial = []
        agentes_codigos = [e.agente_nocivo for e in resultado.exposicoes if e.agente_nocivo]
        if agentes_codigos:
            try:
                from ...domain.especial.jurisprudencia import buscar_jurisprudencia
                juris = buscar_jurisprudencia(
                    agentes_provaveis=agentes_codigos,
                    categoria_empregador=resultado.empresa_razao_social or "",
                    empregador_nome=resultado.empresa_razao_social or "",
                )
                for j in juris:
                    juris_serial.append({
                        "tipo": j.tipo,
                        "numero": j.numero,
                        "tribunal": j.tribunal,
                        "ementa": j.ementa,
                        "aplicabilidade": j.aplicabilidade,
                        "url": j.url,
                    })
            except ImportError:
                pass

        # Serializar exposicoes
        exposicoes_serial = []
        for e in resultado.exposicoes:
            exposicoes_serial.append({
                "agente_nocivo": e.agente_nocivo,
                "codigo_agente": e.codigo_agente,
                "intensidade": e.intensidade,
                "data_inicio": e.data_inicio.strftime("%d/%m/%Y") if e.data_inicio else None,
                "data_fim": e.data_fim.strftime("%d/%m/%Y") if e.data_fim else None,
                "epi_eficaz": e.epi_eficaz,
                "epc_eficaz": e.epc_eficaz,
                "ca_epi": e.ca_epi,
                "setor": e.setor,
                "cargo": e.cargo,
            })

        return {
            "sucesso": True,
            "tipo_documento": "PPP",
            "trabalhador": {
                "nome": resultado.nome,
                "cpf": resultado.cpf,
                "nit": resultado.nit,
            },
            "empresa": {
                "razao_social": resultado.empresa_razao_social,
                "cnpj": resultado.empresa_cnpj,
                "cnae": resultado.empresa_cnae,
                "grau_risco": resultado.empresa_grau_risco,
            },
            "vinculo": {
                "cargo": resultado.cargo,
                "cbo": resultado.cbo,
                "setor": resultado.setor,
                "data_admissao": resultado.data_admissao.strftime("%d/%m/%Y") if resultado.data_admissao else None,
                "data_demissao": resultado.data_demissao.strftime("%d/%m/%Y") if resultado.data_demissao else None,
            },
            "exposicoes": exposicoes_serial,
            "jurisprudencias": juris_serial,
            "responsavel": {
                "nome": resultado.responsavel_registros,
                "registro": resultado.responsavel_crm_crea,
            },
            "data_emissao": resultado.data_emissao.strftime("%d/%m/%Y") if resultado.data_emissao else None,
            "avisos": resultado.avisos,
        }
    finally:
        os.unlink(tmp.name)


@router.post("/documento-comprobatorio")
async def upload_documento_comprobatorio(
    arquivo: UploadFile = File(...),
    tipo: str = Form("LTCAT", description="Tipo: LTCAT, CAT, LAUDO, DIRBEN, ATESTADO, OUTRO"),
):
    """
    Faz upload de documento comprobatorio generico (LTCAT, CAT, laudos, etc).
    Extrai texto via OCR e busca mencoes a agentes nocivos e periodos.
    """
    if not arquivo.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Apenas arquivos PDF sao aceitos.")

    conteudo = await arquivo.read()
    if len(conteudo) == 0:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    import io, tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.write(conteudo)
    tmp.close()

    try:
        # Extrair texto (nativo + OCR fallback)
        texto = ""
        try:
            import pdfplumber
            with pdfplumber.open(tmp.name) as pdf:
                for page in pdf.pages:
                    t = page.extract_text() or ""
                    texto += t + "\n"
        except Exception:
            pass

        via_ocr = False
        if not texto.strip():
            texto = _extrair_texto_ocr_upload(tmp.name, arquivo.filename)
            if texto.strip():
                via_ocr = True

        if not texto.strip():
            return {
                "sucesso": False,
                "erro": "Nao foi possivel extrair texto do documento",
                "avisos": [],
            }

        import re
        texto_upper = texto.upper()

        # Buscar agentes nocivos mencionados
        AGENTES = {
            r'RU[IÍ]DO': 'RUIDO', r'VIBRA[CÇ]': 'VIBRACAO', r'CALOR': 'CALOR',
            r'FRIO': 'FRIO', r'RADIA[CÇ]': 'RADIACAO', r'ELETRICIDADE': 'ELETRICIDADE',
            r'POEIRA': 'POEIRA', r'S[IÍ]LICA': 'SILICA', r'AMIANTO': 'AMIANTO',
            r'BENZENO': 'BENZENO', r'HIDROCARBONETO': 'HIDROCARBONETOS',
            r'SOLVENTE': 'SOLVENTES', r'CHUMBO': 'CHUMBO', r'MERC[UÚ]RIO': 'MERCURIO',
            r'BIOL[OÓ]GICO|MICRO[\-\s]?ORGANISMO': 'AGENTES_BIOLOGICOS',
            r'COMBUST[IÍ]VEL|GASOLINA': 'COMBUSTIVEIS', r'CLORO': 'CLORO',
            r'SOLDA|FUMO\s*MET': 'FUMOS_METALICOS', r'PERICULOSIDADE': 'PERICULOSIDADE',
        }
        agentes_encontrados = []
        for padrao, codigo in AGENTES.items():
            if re.search(padrao, texto_upper):
                agentes_encontrados.append(codigo)

        # Buscar intensidades
        intensidades = re.findall(
            r'(\d+[\.,]?\d*)\s*(dB\s*\(?A?\)?|mg/m|ppm|[°º]C)',
            texto, re.IGNORECASE
        )

        # Buscar empresa
        empresa = None
        m = re.search(r'(?:RAZ[AÃ]O\s*SOCIAL|EMPRESA|EMPREGADOR)\s*[:\-]?\s*(.{5,80})', texto, re.IGNORECASE)
        if m:
            empresa = m.group(1).strip()

        cnpj = None
        m = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', texto)
        if m:
            cnpj = m.group(1)

        # Buscar jurisprudencia
        juris_serial = []
        if agentes_encontrados:
            try:
                from ...domain.especial.jurisprudencia import buscar_jurisprudencia
                juris = buscar_jurisprudencia(
                    agentes_provaveis=agentes_encontrados,
                    categoria_empregador=empresa or "",
                    empregador_nome=empresa or "",
                )
                for j in juris:
                    juris_serial.append({
                        "tipo": j.tipo, "numero": j.numero, "tribunal": j.tribunal,
                        "ementa": j.ementa, "aplicabilidade": j.aplicabilidade, "url": j.url,
                    })
            except ImportError:
                pass

        return {
            "sucesso": True,
            "tipo_documento": tipo.upper(),
            "via_ocr": via_ocr,
            "empresa": empresa,
            "cnpj": cnpj,
            "agentes_encontrados": agentes_encontrados,
            "intensidades": [f"{v} {u}" for v, u in intensidades],
            "jurisprudencias": juris_serial,
            "texto_resumo": texto[:500],
            "avisos": [f"Documento {tipo} processado"] + (["Texto extraido via OCR"] if via_ocr else []),
        }
    finally:
        os.unlink(tmp.name)


# ─────────────────────────────────────────────────────────────────────────────
# Análise especial completa (compartilhada entre CNIS e CTPS)
# ─────────────────────────────────────────────────────────────────────────────

def _analisar_vinculos_especial_completo(
    vinculos_info: list,
    origem: str = "cnis",
) -> list:
    """
    Analisa todos os vínculos para atividade especial, incluindo jurisprudência.

    Args:
        vinculos_info: Lista de tuplas (nome, cnpj, cargo, cbo, dt_inicio, dt_fim)
        origem: "cnis" ou "ctps"

    Returns:
        Lista de dicts com análise completa por vínculo
    """
    import logging
    logger = logging.getLogger("sistprev.upload")

    try:
        from ...domain.especial.agentes_nocivos import verificar_possivel_especial
        from ...domain.especial.cbo_especial import analisar_cbo
        from ...domain.especial.jurisprudencia import buscar_jurisprudencia
    except ImportError as e:
        logger.warning(f"Módulos de análise especial não disponíveis: {e}")
        return []

    prob_ordem = {"ALTA": 3, "MEDIA": 2, "BAIXA": 1}
    resultado = []

    for nome, cnpj, cargo, cbo, dt_inicio, dt_fim in vinculos_info:
        vinc = {
            "empregador_nome": nome,
            "empregador_cnpj": cnpj,
            "cargo": cargo,
            "cbo": cbo,
            "data_inicio": dt_inicio,
            "data_fim": dt_fim,
        }

        # 1. Analisar pelo nome do empregador
        analise_emp = verificar_possivel_especial(nome or "", cnpj or "")

        # 2. Analisar pelo cargo
        analise_cargo = verificar_possivel_especial(cargo or "", "") if cargo else {"possivel_especial": False}

        # 3. Analisar pelo CBO
        analise_cbo_result = analisar_cbo(cbo or "", cargo or "") if cbo or cargo else None

        # Combinar: usar o melhor resultado
        melhor = analise_emp
        via = "empregador"
        if prob_ordem.get(analise_cargo.get("probabilidade", ""), 0) > prob_ordem.get(melhor.get("probabilidade", ""), 0):
            melhor = analise_cargo
            via = "cargo"
        if analise_cbo_result and prob_ordem.get(analise_cbo_result.get("probabilidade", ""), 0) > prob_ordem.get(melhor.get("probabilidade", ""), 0):
            melhor = analise_cbo_result
            via = "cbo"

        if melhor.get("possivel_especial"):
            agentes = []
            agentes_codigos = []
            for a in melhor.get("agentes_provaveis", []):
                if isinstance(a, dict):
                    agentes.append(a.get("descricao", str(a)))
                    agentes_codigos.append(a.get("codigo", a.get("descricao", "")))
                else:
                    agentes.append(str(a))
                    agentes_codigos.append(str(a))

            # Buscar jurisprudência real
            juris = buscar_jurisprudencia(
                agentes_provaveis=agentes_codigos,
                categoria_empregador=nome or "",
                empregador_nome=nome or "",
            )
            juris_serial = []
            for j in juris:
                juris_serial.append({
                    "tipo": j.tipo,
                    "numero": j.numero,
                    "tribunal": j.tribunal,
                    "ementa": j.ementa,
                    "aplicabilidade": j.aplicabilidade,
                    "url": j.url,
                })

            vinc["especial"] = {
                "possivel": True,
                "probabilidade": melhor.get("probabilidade", "BAIXA"),
                "via": via,
                "agentes": agentes,
                "fundamentacao": melhor.get("fundamentacao", ""),
                "recomendacao": melhor.get("recomendacao", ""),
                "fator": melhor.get("fatores_conversao", {}),
                "anos": melhor.get("aposentadoria_especial_anos", 25),
            }
            vinc["jurisprudencias"] = juris_serial
        else:
            vinc["especial"] = {"possivel": False, "probabilidade": "NENHUMA"}
            vinc["jurisprudencias"] = []

        # Info CBO
        if analise_cbo_result:
            vinc["cbo_info"] = analise_cbo_result.get("descricao_cbo", "")
            vinc["cbo_nr"] = analise_cbo_result.get("nrs_aplicaveis", [])
        else:
            vinc["cbo_info"] = ""
            vinc["cbo_nr"] = []

        resultado.append(vinc)

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Conversor interno
# ─────────────────────────────────────────────────────────────────────────────

def _segurado_to_schema(s: Segurado) -> SeguradoSchema:
    dp = s.dados_pessoais
    vinculos_schema = []
    for v in s.vinculos:
        contribuicoes_schema = []
        for c in v.contribuicoes:
            contribuicoes_schema.append(ContribuicaoSchema(
                competencia=c.competencia.strftime("%m/%Y"),
                salario=str(c.salario_contribuicao),
                teto_aplicado=c.teto_aplicado,
            ))
        vinculos_schema.append(VinculoSchema(
            empregador_cnpj=v.empregador_cnpj,
            empregador_nome=v.empregador_nome,
            tipo_vinculo=v.tipo_vinculo.name,
            tipo_atividade=v.tipo_atividade.name,
            data_inicio=v.data_inicio.strftime("%d/%m/%Y"),
            data_fim=v.data_fim.strftime("%d/%m/%Y") if v.data_fim else None,
            contribuicoes=contribuicoes_schema,
            indicadores=v.indicadores or "",
        ))

    # Converter benefícios anteriores
    beneficios_schema = []
    for b in s.beneficios_anteriores:
        beneficios_schema.append(BeneficioAnteriorSchema(
            numero_beneficio=b.numero_beneficio or "",
            especie=b.especie.value if hasattr(b.especie, 'value') else str(b.especie),
            dib=b.dib.strftime("%d/%m/%Y") if b.dib else "",
            dcb=b.dcb.strftime("%d/%m/%Y") if b.dcb else None,
            rmi=str(b.rmi) if b.rmi else "0",
        ))

    return SeguradoSchema(
        dados_pessoais=DadosPessoaisSchema(
            nome=dp.nome,
            data_nascimento=dp.data_nascimento.strftime("%d/%m/%Y"),
            sexo=dp.sexo.name,
            cpf=dp.cpf or None,
            nit=dp.nit or None,
        ),
        vinculos=vinculos_schema,
        beneficios_anteriores=beneficios_schema,
    )
