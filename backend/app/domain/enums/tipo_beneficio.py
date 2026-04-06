from enum import Enum


class TipoBeneficio(str, Enum):
    # Aposentadorias
    APOSENTADORIA_IDADE = "B41"                    # Aposentadoria por Idade (urbana)
    APOSENTADORIA_IDADE_RURAL = "B42"              # Aposentadoria por Idade (rural)
    APOSENTADORIA_INVALIDEZ_PREV = "B32"           # Aposentadoria por Incapacidade Permanente (previdenciária)
    APOSENTADORIA_INVALIDEZ_ACID = "B92"           # Aposentadoria por Incapacidade Permanente (acidentária)
    APOSENTADORIA_ESPECIAL = "B46"                 # Aposentadoria Especial (tempo especial)
    APOSENTADORIA_TEMPO_CONTRIB = "B57"            # Aposentadoria por Tempo de Contribuição (professor)

    # Auxílios por incapacidade
    AUXILIO_DOENCA_PREV = "B31"                    # Auxílio por Incapacidade Temporária (previdenciário)
    AUXILIO_DOENCA_ACID = "B91"                    # Auxílio por Incapacidade Temporária (acidentário)
    AUXILIO_ACIDENTE = "B36"                       # Auxílio-Acidente

    # Pensões e benefícios familiares
    PENSAO_MORTE_URBANA = "B21"                    # Pensão por Morte (urbana)
    PENSAO_MORTE_RURAL = "B22"                     # Pensão por Morte (rural)
    SALARIO_MATERNIDADE = "B80"                    # Salário-Maternidade
    AUXILIO_RECLUSAO = "B25"                       # Auxílio-Reclusão

    # Benefício assistencial
    BPC_LOAS_IDOSO = "B87"                         # BPC/LOAS - Idoso
    BPC_LOAS_DEFICIENTE = "B88"                    # BPC/LOAS - Deficiente

    # Certidão / revisão
    REVISAO = "REVISAO"                            # Para cálculos de revisão genéricos
