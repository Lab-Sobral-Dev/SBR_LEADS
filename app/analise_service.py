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


def _classificar(itens: list[dict], criterio: str, cortes: tuple[int, int]):
    """Classifica itens em A/B/C pela receita acumulada do critério (Pareto).

    Cada item de entrada tem: codigo, nome, receita, quantidade.
    Retorna (lista_classificada, resumo). Convenção: o item que cruza a fronteira
    pertence à classe de cima (classifica pelo acumulado ANTES de somar o item).
    """
    corte_a, corte_b = cortes
    limite_b = corte_a + corte_b
    total = sum(it[criterio] for it in itens)
    ordenados = sorted(itens, key=lambda it: (-it[criterio], it["nome"]))

    resumo = {c: {"itens": 0, "receita": 0.0, "quantidade": 0.0} for c in ("A", "B", "C")}
    saida, acumulado = [], 0.0
    for it in ordenados:
        valor = it[criterio]
        antes_pct = (acumulado / total * 100) if total else 100.0
        if total and antes_pct < corte_a:
            classe = "A"
        elif total and antes_pct < limite_b:
            classe = "B"
        else:
            classe = "C"
        acumulado += valor
        saida.append({
            "codigo": it.get("codigo"),
            "nome": it["nome"],
            "receita": float(it["receita"]),
            "quantidade": float(it["quantidade"]),
            "pct": round(valor / total * 100, 1) if total else 0.0,
            "pct_acumulado": round(acumulado / total * 100, 1) if total else 0.0,
            "classe": classe,
        })
        resumo[classe]["itens"] += 1
        resumo[classe]["receita"] += float(it["receita"])
        resumo[classe]["quantidade"] += float(it["quantidade"])

    for c in ("A", "B", "C"):
        valor_classe = resumo[c]["receita"] if criterio == "receita" else resumo[c]["quantidade"]
        resumo[c]["pct"] = round(valor_classe / total * 100, 1) if total else 0.0
    resumo["total_itens"] = len(saida)
    resumo["total_receita"] = float(sum(i["receita"] for i in saida))
    resumo["total_quantidade"] = float(sum(i["quantidade"] for i in saida))
    return saida, resumo
