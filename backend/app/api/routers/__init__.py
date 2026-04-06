from .calculo import router as calculo_router
from .upload import router as upload_router
from .indices import router as indices_router
from .relatorio import router as relatorio_router
from .planejamento import router as planejamento_router
from .estudos import router as estudos_router

__all__ = ["calculo_router", "upload_router", "indices_router", "relatorio_router", "planejamento_router", "estudos_router"]
