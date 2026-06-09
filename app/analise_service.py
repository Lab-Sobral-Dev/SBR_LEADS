"""Serviço do dashboard de Análise de Vendas — curvas ABC (Pareto).

Reusa FiltrosDashboard/build_where/opcoes_filtro do dashboard_service do cockpit.
A classificação ABC é math pura (testável sem banco).
"""

# Whitelist de cortes ABC: string canônica -> (corte_a, corte_b) em pontos percentuais.
# A classe C ocupa o restante (100 - a - b).
_CORTES = {"50-30-20": (50, 30), "70-20-10": (70, 20), "80-15-5": (80, 15)}
_CORTES_PADRAO = "50-30-20"
_CRITERIOS = {"receita", "quantidade"}


def cortes_canonico(s: str | None) -> str:
    """Devolve a string de cortes válida ou o padrão."""
    s = (s or "").strip()
    return s if s in _CORTES else _CORTES_PADRAO


def parse_cortes(s: str | None) -> tuple[int, int]:
    """Converte a string de cortes em (corte_a, corte_b). Fallback no padrão."""
    return _CORTES[cortes_canonico(s)]


def parse_criterio(s: str | None) -> str:
    """Normaliza o critério de classificação. Fallback 'receita'."""
    s = (s or "").strip().lower()
    return s if s in _CRITERIOS else "receita"
