"""
Serviço central de cálculo previdenciário.

Orquestra: parsing de documentos → montagem do Segurado → execução
de todos os cálculos → retorno de resultado unificado para a API.
"""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional, List, Dict, Any

from ..domain.models.segurado import Segurado, DadosPessoais
from ..domain.models.vinculo import Vinculo
from ..domain.models.contribuicao import Contribuicao, Competencia
from ..domain.models.resultado import ResultadoCalculo, ResultadoRegra
from ..domain.enums import TipoBeneficio, Sexo, TipoVinculo, RegimePrevidenciario, TipoAtividade, OrigemDado
from ..domain.transicao.comparador import comparar_todas, melhor_regra
from ..domain.beneficios.aposentadoria_idade import CalculadoraAposentadoriaIdade
from ..domain.beneficios.aposentadoria_especial import CalculadoraAposentadoriaEspecial
from ..domain.beneficios.auxilio_doenca import CalculadoraAuxilioDoenca
from ..domain.beneficios.invalidez import CalculadoraInvalidez
from ..domain.beneficios.pensao_morte import CalculadoraPensaoMorte
from ..domain.tempo.contagem import calcular_tempo_contribuicao, calcular_carencia
from ..domain.salario.pbc import calcular_salario_beneficio
from ..domain.indices import teto_na_data
from ..domain.indices.salario_minimo import salario_minimo_na_data
from ..revisoes.vida_toda import calcular_revisao_vida_toda
from ..revisoes.revisao_teto import calcular_revisao_teto
from ..revisoes.liquidacao_sentenca import calcular_atrasados


class CalculoService:
    """
    Serviço de cálculo — não guarda estado entre chamadas.
    Todos os métodos são estáticos/de classe.
    """

    @staticmethod
    def calcular_aposentadoria(
        segurado: Segurado,
        der: date,
        tipo: str = "transicao",
    ) -> Dict[str, Any]:
        """
        Calcula aposentadoria por tempo de contribuição ou por idade.

        tipo:
          "transicao"  → compara todas as regras (pre-reforma ou EC 103 conforme DER)
          "idade"      → apenas regra de idade (60H/57M permanente)
          "especial_15" / "especial_20" / "especial_25" → atividade especial
        """
        from ..domain.constantes import DatasCorte

        # ── Classificação temporal correta ──────────────────────────────────
        is_pre_reforma = der < DatasCorte.EC_103_2019
        tipo_label = "pre_reforma" if is_pre_reforma else "transicao_ec103"

        # ── Detecção de NB ativo → modo revisão ────────────────────────────
        nb_ativo = None
        alertas_consistencia = []
        if segurado.beneficios_anteriores:
            for b in segurado.beneficios_anteriores:
                if b.ativo:
                    nb_ativo = b
                    break

        modo_revisao = nb_ativo is not None
        if modo_revisao:
            alertas_consistencia.append(
                f"ATENÇÃO: Benefício NB {nb_ativo.numero_beneficio} (espécie "
                f"{nb_ativo.especie.value}) encontra-se ATIVO com DIB "
                f"{nb_ativo.dib.strftime('%d/%m/%Y')}. Este caso é de REVISÃO, "
                f"não de novo requerimento. A conclusão deve refletir tese revisional."
            )
            if nb_ativo.rmi and nb_ativo.rmi > 0:
                alertas_consistencia.append(
                    f"RMI administrativa vigente: R$ {float(nb_ativo.rmi):.2f}. "
                    f"Qualquer RMI calculada deve ser confrontada com este valor."
                )

        result: Dict[str, Any] = {
            "der": der,
            "tipo": tipo_label,
            "tipo_original": tipo,
            "erros": [],
            "modo_revisao": modo_revisao,
            "nb_ativo": {
                "numero": nb_ativo.numero_beneficio,
                "especie": nb_ativo.especie.value,
                "dib": nb_ativo.dib.strftime("%d/%m/%Y"),
                "rmi": str(nb_ativo.rmi) if nb_ativo.rmi else None,
            } if nb_ativo else None,
            "alertas_consistencia": alertas_consistencia,
        }

        if tipo == "transicao":
            cenarios = comparar_todas(segurado, der)
            melhor = melhor_regra(segurado, der)
            result["cenarios"] = cenarios
            result["melhor"] = melhor
            result["elegivel"] = melhor is not None and melhor.elegivel
            result["rmi"] = melhor.rmi_teto if melhor and melhor.elegivel else Decimal("0")

        elif tipo == "idade":
            calc = CalculadoraAposentadoriaIdade()
            rc = calc.calcular(segurado, der)
            regra = rc.cenarios[0] if rc.cenarios else None
            result["cenarios"] = rc.cenarios
            result["melhor"] = regra
            result["elegivel"] = rc.elegivel
            result["rmi"] = regra.rmi_teto if regra and rc.elegivel else Decimal("0")

        elif tipo in ("especial_15", "especial_20", "especial_25"):
            anos = int(tipo.split("_")[1])
            calc = CalculadoraAposentadoriaEspecial(anos_especial=anos)
            rc = calc.calcular(segurado, der)
            regra = rc.cenarios[0] if rc.cenarios else None
            result["cenarios"] = rc.cenarios
            result["melhor"] = regra
            result["elegivel"] = rc.elegivel
            result["rmi"] = regra.rmi_teto if regra and rc.elegivel else Decimal("0")

        else:
            result["erros"].append(f"Tipo de cálculo desconhecido: {tipo}")

        # ── Validação de vínculos suspeitos ────────────────────────────────
        # Alertar sobre vínculos com duração anormalmente longa ou que
        # se estendem muito além dos demais (possível erro de parse CNIS)
        vinculos_suspeitos = []
        for v in segurado.vinculos:
            fim_efetivo = min(v.data_fim_efetiva, der)
            if v.data_inicio > der:
                continue
            duracao_anos = (fim_efetivo - v.data_inicio).days / 365.25
            duracao_meses = duracao_anos * 12
            n_contribs = len(v.contribuicoes)
            is_empregado = v.tipo_vinculo in (
                TipoVinculo.EMPREGADO, TipoVinculo.EMPREGADO_DOMESTICO,
                TipoVinculo.TRABALHADOR_AVULSO,
            )

            suspeito = False
            motivo = ""

            # Vínculo CLT com menos de 10% das contribuições esperadas
            if is_empregado and duracao_meses > 60 and n_contribs < duracao_meses * 0.10:
                suspeito = True
                motivo = (
                    f"tem {duracao_anos:.1f} anos de duração mas apenas "
                    f"{n_contribs} contribuições registradas "
                    f"(esperado: ~{int(duracao_meses)}). "
                    f"Possível erro de parse do CNIS."
                )

            # Vínculo cuja data_fim é muito posterior à DER
            if v.data_fim and v.data_fim > der:
                anos_alem = (v.data_fim - der).days / 365.25
                if anos_alem > 3:
                    suspeito = True
                    motivo = (
                        f"data_fim ({v.data_fim.strftime('%d/%m/%Y')}) é "
                        f"{anos_alem:.1f} anos posterior à DER. "
                        f"O INSS pode não reconhecer este período."
                    )

            if suspeito:
                vinculos_suspeitos.append(v)
                alertas_consistencia.append(
                    f"VÍNCULO SUSPEITO: {v.empregador_nome or 'Sem nome'} "
                    f"({v.data_inicio.strftime('%d/%m/%Y')} a "
                    f"{v.data_fim.strftime('%d/%m/%Y') if v.data_fim else 'EM ABERTO'}) — {motivo} "
                    f"Este vínculo pode estar inflando o TC."
                )

        # Se há vínculos suspeitos, calcular TC SEM eles para comparação
        if vinculos_suspeitos:
            vinculos_limpos = [v for v in segurado.vinculos if v not in vinculos_suspeitos]
            if vinculos_limpos:
                tc_sem_suspeitos = calcular_tempo_contribuicao(
                    vinculos_limpos, der, segurado.sexo,
                    beneficios_anteriores=segurado.beneficios_anteriores,
                )
                tc_com = calcular_tempo_contribuicao(
                    segurado.vinculos, der, segurado.sexo,
                    beneficios_anteriores=segurado.beneficios_anteriores,
                )
                dif_anos = float(tc_com.anos_decimal - tc_sem_suspeitos.anos_decimal)
                if dif_anos > 1:
                    alertas_consistencia.append(
                        f"IMPACTO: Sem os vínculos suspeitos, o TC seria de "
                        f"{tc_sem_suspeitos.anos} anos, {tc_sem_suspeitos.meses_restantes} meses "
                        f"e {tc_sem_suspeitos.dias_restantes} dias "
                        f"(diferença de {dif_anos:.1f} anos). "
                        f"O TC com vínculos suspeitos é "
                        f"{tc_com.anos}a {tc_com.meses_restantes}m {tc_com.dias_restantes}d. "
                        f"Confrontar com a memória de cálculo do INSS."
                    )
                result["tc_sem_suspeitos"] = {
                    "anos": tc_sem_suspeitos.anos,
                    "meses": tc_sem_suspeitos.meses_restantes,
                    "dias": tc_sem_suspeitos.dias_restantes,
                    "total_dias": tc_sem_suspeitos.dias_total,
                    "anos_decimal": float(tc_sem_suspeitos.anos_decimal),
                }

        # ── Detecção de períodos MEI 5% complementáveis ───────────────────
        # LC 123/2006 Art. 18-A §4°: MEI 5% NÃO conta para TC (aposentadoria por tempo)
        # mas PODE ser complementado: pagar +15% sobre o SM (código 1910) para contar.
        # Esta seção detecta períodos MEI e calcula o custo da complementação.
        from ..domain.indices.salario_minimo import salario_minimo_em
        alertas_mei = []
        for v in segurado.vinculos:
            contribs_mei = [
                c for c in v.contribuicoes
                if getattr(c, "complementavel_mei", False)
                and c.competencia <= der
            ]
            if not contribs_mei:
                continue

            # Agrupar em blocos contínuos
            contribs_mei.sort()
            grupos = []
            inicio_grupo = contribs_mei[0]
            fim_grupo = contribs_mei[0]
            for i in range(1, len(contribs_mei)):
                prox = contribs_mei[i]
                prev = contribs_mei[i - 1]
                mesmo_mes = (prox.year == prev.year and prox.month == prev.month + 1) or \
                            (prox.year == prev.year + 1 and prox.month == 1 and prev.month == 12)
                if mesmo_mes:
                    fim_grupo = prox
                else:
                    grupos.append((inicio_grupo, fim_grupo))
                    inicio_grupo = prox
                    fim_grupo = prox
            grupos.append((inicio_grupo, fim_grupo))

            for (ini, fim) in grupos:
                n_meses = (fim.year - ini.year) * 12 + (fim.month - ini.month) + 1
                # Custo da complementação: 15% do SM médio do período
                sm_ini = salario_minimo_em(ini)
                sm_fim = salario_minimo_em(fim)
                sm_medio = (sm_ini + sm_fim) / 2
                custo_mes = float(sm_medio) * 0.15
                custo_total = custo_mes * n_meses

                alertas_mei.append({
                    "periodo_inicio": ini.strftime("%m/%Y"),
                    "periodo_fim": fim.strftime("%m/%Y"),
                    "meses": n_meses,
                    "custo_complementacao_mes": f"R$ {custo_mes:.2f}",
                    "custo_total_estimado": f"R$ {custo_total:.2f}",
                    "impacto_tc_meses": n_meses,
                    "base_legal": "LC 123/2006, Art. 18-A §4° c/c Art. 21 §3° Lei 8.212/91",
                })

        result["alertas_mei"] = alertas_mei
        if alertas_mei:
            total_meses_mei = sum(a["meses"] for a in alertas_mei)
            alertas_consistencia.append(
                f"MEI 5% DETECTADO: {total_meses_mei} meses de contribuição MEI não contam "
                f"para TC (LC 123/2006, Art. 18-A §4°). Se complementados (+15% SM/mês, "
                f"código GPS 1910), passariam a contar. Veja alertas MEI no resultado."
            )

        # ── Validação de consistência pós-cálculo ──────────────────────────
        # Comparar RMI calculada com RMI administrativa quando NB ativo existe
        if modo_revisao and nb_ativo and nb_ativo.rmi and nb_ativo.rmi > 0:
            rmi_calc = result.get("rmi", Decimal("0"))
            if rmi_calc and rmi_calc > 0:
                diferenca_pct = abs(float(rmi_calc - nb_ativo.rmi) / float(nb_ativo.rmi) * 100)
                if diferenca_pct > 20:
                    alertas_consistencia.append(
                        f"DIVERGÊNCIA SIGNIFICATIVA: RMI calculada (R$ {float(rmi_calc):.2f}) "
                        f"difere em {diferenca_pct:.1f}% da RMI administrativa "
                        f"(R$ {float(nb_ativo.rmi):.2f}). Verificar se os insumos (tempo de "
                        f"contribuição, salários, períodos especiais) correspondem à fotografia "
                        f"histórica da DER, e não a dados posteriores."
                    )

        # Alerta temporal: DER pré-reforma com tipo "transição"
        if is_pre_reforma and tipo == "transicao":
            alertas_consistencia.append(
                f"NOTA TEMPORAL: A DER informada ({der.strftime('%d/%m/%Y')}) é anterior à "
                f"EC 103/2019 (13/11/2019). As regras aplicáveis são as pré-reforma "
                f"(Lei 8.213/91, Lei 9.876/99, Lei 13.183/2015), não as regras de transição "
                f"da EC 103. O sistema aplicou corretamente as regras pré-reforma."
            )

        result["alertas_consistencia"] = alertas_consistencia

        return result

    @staticmethod
    def calcular_auxilio_doenca(
        segurado: Segurado,
        der: date,
        acidentario: bool = False,
    ) -> Dict[str, Any]:
        calc = CalculadoraAuxilioDoenca(acidentario=acidentario)
        rc = calc.calcular(segurado, der)
        regra = rc.cenarios[0] if rc.cenarios else None
        return {
            "der": der,
            "tipo": "B91" if acidentario else "B31",
            "elegivel": rc.elegivel,
            "rmi": regra.rmi_teto if regra and rc.elegivel else Decimal("0"),
            "resultado": regra,
        }

    @staticmethod
    def calcular_invalidez(
        segurado: Segurado,
        der: date,
        acidentaria: bool = False,
        grande_invalido: bool = False,
    ) -> Dict[str, Any]:
        calc = CalculadoraInvalidez(acidentaria=acidentaria, grande_invalido=grande_invalido)
        rc = calc.calcular(segurado, der)
        regra = rc.cenarios[0] if rc.cenarios else None
        return {
            "der": der,
            "tipo": "B92" if acidentaria else "B32",
            "elegivel": rc.elegivel,
            "rmi": regra.rmi_teto if regra and rc.elegivel else Decimal("0"),
            "resultado": regra,
        }

    @staticmethod
    def calcular_pensao_morte(
        segurado: Segurado,
        der: date,
        num_dependentes: int,
        data_obito: date,
        tem_dependente_invalido: bool = False,
        rma_instituidor: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        calc = CalculadoraPensaoMorte(
            num_dependentes=num_dependentes,
            tem_dependente_invalido=tem_dependente_invalido,
            data_obito=data_obito,
            rma_instituidor=rma_instituidor,
        )
        rc = calc.calcular(segurado, der)
        regra = rc.cenarios[0] if rc.cenarios else None
        return {
            "der": der,
            "tipo": "B21",
            "elegivel": rc.elegivel,
            "rmi": regra.rmi_teto if regra and rc.elegivel else Decimal("0"),
            "resultado": regra,
        }

    @staticmethod
    def calcular_revisao_vida_toda(
        segurado: Segurado,
        der: date,
        dib: date,
        rmi_original: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        return calcular_revisao_vida_toda(segurado, der, dib, rmi_original)

    @staticmethod
    def calcular_revisao_teto(
        dib: date,
        rmi_original: Decimal,
        sb_original: Decimal,
        der_revisao: date,
    ) -> Dict[str, Any]:
        return calcular_revisao_teto(dib, rmi_original, sb_original, der_revisao)

    @staticmethod
    def calcular_atrasados(
        dib: date,
        rmi_original: Decimal,
        data_atualizacao: date,
        data_ajuizamento: Optional[date] = None,
        incluir_juros: bool = True,
        rmi_paga: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        return calcular_atrasados(dib, rmi_original, data_atualizacao, data_ajuizamento, incluir_juros, rmi_paga)

    @staticmethod
    def resumo_segurado(segurado: Segurado, der: date) -> Dict[str, Any]:
        """Dados básicos calculados do segurado para exibição no dashboard."""
        tc = calcular_tempo_contribuicao(
            segurado.vinculos, der, segurado.sexo,
            beneficios_anteriores=segurado.beneficios_anteriores,
        )
        carencia = calcular_carencia(segurado.vinculos, der)
        teto = teto_na_data(der)
        piso = salario_minimo_na_data(der)

        # Tentar calcular SB para preview
        sb_info: Dict[str, Any] = {}
        try:
            sb_info = calcular_salario_beneficio(
                segurado.vinculos, der,
                usar_regra_ec103=True,
                usar_vida_toda=False,
            )
        except Exception:
            pass

        return {
            "nome": segurado.dados_pessoais.nome,
            "cpf": segurado.dados_pessoais.cpf,
            "data_nascimento": segurado.dados_pessoais.data_nascimento,
            "sexo": segurado.dados_pessoais.sexo.value,
            "idade_na_der": float(segurado.idade_na(der)),
            "tempo_contribuicao": {
                "anos": tc.anos,
                "meses": tc.meses_restantes,
                "dias": tc.dias_restantes,
                "total_dias": tc.dias_total,
                "anos_decimal": float(tc.anos_decimal),
            },
            "carencia_meses": carencia,
            "teto_vigente": teto,
            "piso_vigente": piso,
            "num_vinculos": len(segurado.vinculos),
            "salario_beneficio": sb_info.get("salario_beneficio"),
            "media_salarios": sb_info.get("media"),
        }

    @staticmethod
    def montar_segurado_de_dados(dados: Dict[str, Any]) -> Segurado:
        """
        Constrói um objeto Segurado a partir de um dict (vindo da API).
        Usado quando os dados são inseridos manualmente ou editados.
        """
        from datetime import date as d
        dp = DadosPessoais(
            nome=dados["nome"],
            data_nascimento=_parse_date(dados["data_nascimento"]),
            sexo=Sexo[dados["sexo"].upper()],
            cpf=dados.get("cpf", ""),
            nit=dados.get("nit", ""),
        )

        vinculos = []
        for v_dict in dados.get("vinculos", []):
            contribuicoes = []
            for c_dict in v_dict.get("contribuicoes", []):
                comp_str = c_dict["competencia"]  # "MM/AAAA"
                comp = Competencia.criar(
                    int(comp_str[3:7]), int(comp_str[:2])
                )
                contribuicoes.append(Contribuicao(
                    competencia=comp,
                    salario_contribuicao=Decimal(str(c_dict["salario"])),
                ))

            v = Vinculo(
                tipo_vinculo=TipoVinculo[v_dict.get("tipo_vinculo", "EMPREGADO").upper()],
                regime=RegimePrevidenciario.RGPS,
                tipo_atividade=TipoAtividade[v_dict.get("tipo_atividade", "NORMAL").upper()],
                empregador_cnpj=v_dict.get("empregador_cnpj"),
                empregador_nome=v_dict.get("empregador_nome"),
                data_inicio=_parse_date(v_dict["data_inicio"]),
                data_fim=_parse_date(v_dict["data_fim"]) if v_dict.get("data_fim") else None,
                contribuicoes=contribuicoes,
                origem=OrigemDado.MANUAL,
            )
            vinculos.append(v)

        return Segurado(dados_pessoais=dp, vinculos=vinculos)


def _parse_date(s) -> date:
    if isinstance(s, date):
        return s
    if isinstance(s, str):
        if "/" in s:
            p = s.split("/")
            if len(p) == 3:
                return date(int(p[2]), int(p[1]), int(p[0]))
        return date.fromisoformat(s)
    raise ValueError(f"Data inválida: {s!r}")
