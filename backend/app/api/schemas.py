"""
Schemas Pydantic para a API REST.
Todos os valores monetários são string para preservar precisão.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, field_validator, model_validator
import re


# ─────────────────────────────────────────────────────────────────────────────
# Primitivos reutilizáveis
# ─────────────────────────────────────────────────────────────────────────────

class ContribuicaoSchema(BaseModel):
    competencia: str           # "MM/AAAA"
    salario: str               # valor em reais, ex: "2500.00"
    teto_aplicado: bool = False

    @field_validator("competencia")
    @classmethod
    def validar_competencia(cls, v: str) -> str:
        if not re.match(r"^\d{2}/\d{4}$", v):
            raise ValueError("Competência deve estar no formato MM/AAAA")
        mes, ano = int(v[:2]), int(v[3:])
        if not (1 <= mes <= 12):
            raise ValueError("Mês inválido")
        if not (1940 <= ano <= 2100):
            raise ValueError("Ano fora do intervalo permitido")
        return v

    @field_validator("salario")
    @classmethod
    def validar_salario(cls, v: str) -> str:
        try:
            val = Decimal(v)
            if val < 0:
                raise ValueError
        except Exception:
            raise ValueError("Salário deve ser um número não-negativo")
        return v


class VinculoSchema(BaseModel):
    empregador_cnpj: Optional[str] = None
    empregador_nome: Optional[str] = None
    tipo_vinculo: str = "EMPREGADO"
    tipo_atividade: str = "NORMAL"
    data_inicio: str               # "DD/MM/AAAA" ou ISO "AAAA-MM-DD"
    data_fim: Optional[str] = None
    contribuicoes: List[ContribuicaoSchema] = []
    indicadores: Optional[str] = ""  # Indicadores CNIS (PREC-MENOR-MIN, etc.)

    @field_validator("tipo_vinculo")
    @classmethod
    def validar_tipo_vinculo(cls, v: str) -> str:
        validos = {
            "EMPREGADO", "EMPREGADO_DOMESTICO", "TRABALHADOR_AVULSO",
            "CONTRIBUINTE_INDIVIDUAL", "FACULTATIVO", "MEI",
            "SEGURADO_ESPECIAL", "SERVIDOR_PUBLICO",
        }
        if v.upper() not in validos:
            raise ValueError(f"Tipo de vínculo inválido: {v}. Válidos: {validos}")
        return v.upper()

    @field_validator("tipo_atividade")
    @classmethod
    def validar_tipo_atividade(cls, v: str) -> str:
        validos = {"NORMAL", "ESPECIAL_15", "ESPECIAL_20", "ESPECIAL_25"}
        if v.upper() not in validos:
            raise ValueError(f"Tipo de atividade inválido: {v}. Válidos: {validos}")
        return v.upper()


class DadosPessoaisSchema(BaseModel):
    nome: str
    data_nascimento: str          # "DD/MM/AAAA"
    sexo: str                     # "MASCULINO" ou "FEMININO"
    cpf: Optional[str] = None
    nit: Optional[str] = None

    @field_validator("sexo")
    @classmethod
    def validar_sexo(cls, v: str) -> str:
        if v.upper() not in ("MASCULINO", "FEMININO", "M", "F"):
            raise ValueError("Sexo deve ser MASCULINO ou FEMININO")
        return "MASCULINO" if v.upper() in ("M", "MASCULINO") else "FEMININO"

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        limpo = re.sub(r"[^\d]", "", v)
        if len(limpo) not in (0, 11):
            raise ValueError("CPF deve ter 11 dígitos")
        return limpo


class BeneficioAnteriorSchema(BaseModel):
    """Benefício previdenciário anterior (ex: auxílio-doença B31)."""
    numero_beneficio: str = ""
    especie: str             # "B31", "B32", "B91", "B92", etc.
    dib: str                 # "DD/MM/AAAA"
    dcb: Optional[str] = None  # Data de cessação (None = ativo)
    rmi: str = "0"


class SeguradoSchema(BaseModel):
    dados_pessoais: DadosPessoaisSchema
    vinculos: List[VinculoSchema] = []
    beneficios_anteriores: List[BeneficioAnteriorSchema] = []


# ─────────────────────────────────────────────────────────────────────────────
# Requests
# ─────────────────────────────────────────────────────────────────────────────

class CalculoAposentadoriaRequest(BaseModel):
    segurado: SeguradoSchema
    der: str                    # "DD/MM/AAAA" ou ISO
    tipo: str = "transicao"     # "transicao" | "idade" | "especial_15/20/25"


class CalculoAuxilioDoencaRequest(BaseModel):
    segurado: SeguradoSchema
    der: str
    acidentario: bool = False


class CalculoInvalidezRequest(BaseModel):
    segurado: SeguradoSchema
    der: str
    acidentaria: bool = False
    grande_invalido: bool = False


class CalculoPensaoRequest(BaseModel):
    segurado: SeguradoSchema
    der: str
    num_dependentes: int = 1
    data_obito: str
    tem_dependente_invalido: bool = False
    rma_instituidor: Optional[str] = None  # valor decimal como string


class RevisaoVidaTodaRequest(BaseModel):
    segurado: SeguradoSchema
    der: str
    dib: str
    rmi_original: Optional[str] = None


class RevisaoTetoRequest(BaseModel):
    dib: str
    rmi_original: str
    sb_original: str
    der_revisao: str


class AtrasadosRequest(BaseModel):
    dib: str
    rmi_original: str  # RMI correta (como deveria ser)
    rmi_paga: Optional[str] = None  # RMI que o INSS paga (se revisão). Atrasados = diferença.
    data_atualizacao: str
    data_ajuizamento: Optional[str] = None
    incluir_juros: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Responses
# ─────────────────────────────────────────────────────────────────────────────

class TempoContribuicaoResponse(BaseModel):
    anos: int
    meses: int
    dias: int
    total_dias: int
    anos_decimal: float


class CenarioResponse(BaseModel):
    nome_regra: str
    base_legal: str
    elegivel: bool
    rmi: str
    rmi_formatada: str
    salario_beneficio: str
    coeficiente: str
    fator_previdenciario: Optional[str] = None
    tempo_contribuicao: Optional[TempoContribuicaoResponse] = None
    faltam_dias: int = 0
    avisos: List[str] = []
    memoria: List[Dict[str, Any]] = []


class CalculoResponse(BaseModel):
    elegivel: bool
    der: str
    tipo: str
    rmi: str
    rmi_formatada: str
    melhor_cenario: Optional[CenarioResponse] = None
    todos_cenarios: List[CenarioResponse] = []
    erros: List[str] = []
    avisos: List[str] = []


class ResumoSeguradoResponse(BaseModel):
    nome: str
    cpf: Optional[str]
    data_nascimento: str
    sexo: str
    idade_na_der: float
    tempo_contribuicao: TempoContribuicaoResponse
    carencia_meses: int
    teto_vigente: str
    piso_vigente: str
    num_vinculos: int
    salario_beneficio: Optional[str]
    media_salarios: Optional[str]


class ParseCNISResponse(BaseModel):
    sucesso: bool
    segurado: Optional[SeguradoSchema] = None
    avisos: List[str] = []
    erros: List[str] = []
    beneficios: Optional[list] = None
    analise_especial: Optional[list] = None


class ParcelasAtrasadasResponse(BaseModel):
    total_principal: str
    total_juros: str
    total_geral: str
    parcelas_calculadas: int
    parcelas_prescritas: int
    parcelas: List[Dict[str, Any]] = []
    tipo_calculo: str = "integral"  # 'diferenca' ou 'integral'
    rmi_correta: Optional[str] = None
    rmi_paga: Optional[str] = None
    diferenca_mensal: Optional[str] = None
    explicacao: Optional[str] = None


class RevisaoVidaTodaResponse(BaseModel):
    favoravel: bool
    diferenca_rmi_mensal: str
    metodo_original: CenarioResponse
    metodo_vida_toda: CenarioResponse
    resultado_final: CenarioResponse


class RevisaoTetoResponse(BaseModel):
    ec20_aplicavel: bool
    ec41_aplicavel: bool
    rmi_original: str
    rmi_revisada: str
    diferenca_mensal: str
    rmi_pos_ec20: Optional[str] = None
    rmi_pos_ec41: Optional[str] = None
