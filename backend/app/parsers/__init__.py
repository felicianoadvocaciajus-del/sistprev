from .cnis.parser import parsear_cnis_pdf, parsear_cnis_texto
from .carta_concessao.parser import parsear_carta_concessao
from .ctps.parser import parsear_ctps_digital

__all__ = [
    "parsear_cnis_pdf",
    "parsear_cnis_texto",
    "parsear_carta_concessao",
    "parsear_ctps_digital",
]
