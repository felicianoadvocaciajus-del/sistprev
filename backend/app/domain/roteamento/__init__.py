"""
Motor de Roteamento de Caso Previdenciario.

Analisa os documentos uploadados e dados do segurado para recomendar
o caminho correto: REVISAO, NOVO_BENEFICIO, REANALISE, etc.

Deve ser chamado APOS o upload de documentos e ANTES de qualquer calculo.
"""
from .motor_roteamento import rotear_caso, ModoRecomendado

__all__ = ["rotear_caso", "ModoRecomendado"]
