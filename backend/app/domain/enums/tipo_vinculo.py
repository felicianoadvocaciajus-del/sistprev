from enum import Enum


class TipoVinculo(str, Enum):
    # Código interno DATAPREV (codigoTipoFiliado)
    EMPREGADO = "EMPREGADO"                        # cód 1 - CLT
    TRABALHADOR_AVULSO = "TRABALHADOR_AVULSO"      # cód 2
    EMPREGADO_DOMESTICO = "EMPREGADO_DOMESTICO"    # cód 3
    CONTRIBUINTE_INDIVIDUAL = "CI"                  # cód 4,5,6,7 - autônomo/empresário
    FACULTATIVO = "FACULTATIVO"                    # cód 8,9,13
    SEGURADO_ESPECIAL = "SEGURADO_ESPECIAL"        # cód 11 - rural
    SERVICO_MILITAR = "SERVICO_MILITAR"            # cód 12
    MEI = "MEI"                                    # Microempreendedor Individual
    DIRIGENTE_SINDICAL = "DIRIGENTE_SINDICAL"      # cód 127

    # Tipos especiais para entrada manual
    SERVIDOR_PUBLICO = "SERVIDOR_PUBLICO"          # RPPS — para contagem recíproca
    RURAL_BOIA_FRIA = "RURAL_BOIA_FRIA"           # Trabalhador rural sem registro
