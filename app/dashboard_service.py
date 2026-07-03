from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from dashboard_filters import FiltrosDashboard, derivar_comparacao, _shift_meses
from database import valores_distintos

_NAO_CANCELADO = "UPPER(TRIM(COALESCE(ped.situacao, ''))) <> 'CANCELADO'"


def build_where(f: FiltrosDashboard, *, com_periodo: bool = True) -> tuple[str, dict]:
    """Monta o WHERE parametrizado para queries de pedido (alias ped).

    com_periodo=False omite o filtro de emissão (usado no painel de risco,
    que é medido em relação a hoje).
    """
    cond = []
    params: dict = {}

    if com_periodo:
        cond.append("ped.emissao BETWEEN :inicio AND :fim")
        params["inicio"] = f.inicio
        params["fim"] = f.fim

    if f.situacao == "confirmados":
        cond.append("ped.orcamento = FALSE")
        cond.append(_NAO_CANCELADO)
    elif f.situacao == "todos":
        pass
    else:  # situação específica
        cond.append("UPPER(TRIM(COALESCE(ped.situacao, ''))) = :situacao")
        params["situacao"] = f.situacao.upper()

    if f.vendedor:
        cond.append("ped.vendedor = :vendedor")
        params["vendedor"] = f.vendedor
    if f.representada:
        cond.append("ped.representada = :representada")
        params["representada"] = f.representada

    return (" AND ".join(cond) if cond else "TRUE"), params


# ---------------------------------------------------------------- KPIs

def _agregar(db: Session, where: str, params: dict) -> dict:
    row = db.execute(text(f"""
        SELECT
            COALESCE(SUM(ped.total_liquido), 0)   AS faturamento,
            COUNT(*)                              AS pedidos,
            COUNT(DISTINCT ped.cliente_documento) AS clientes,
            COALESCE(AVG(ped.total_liquido), 0)   AS ticket
        FROM pedido_mobile_pedido ped
        WHERE {where}
    """), params).fetchone()
    return {
        "faturamento": float(row.faturamento or 0),
        "pedidos": int(row.pedidos or 0),
        "clientes": int(row.clientes or 0),
        "ticket": float(row.ticket or 0),
    }


def _delta_pct(atual: float, base: float):
    if not base:
        return None
    return round((atual - base) / base * 100, 1)


def kpis(db: Session, f: FiltrosDashboard) -> dict:
    where, params = build_where(f)
    atual = _agregar(db, where, params)

    cmp = derivar_comparacao(f)
    if cmp:
        base = _agregar(db, where, {**params, "inicio": cmp[0], "fim": cmp[1]})
    else:
        base = {"faturamento": 0, "pedidos": 0, "clientes": 0, "ticket": 0}

    return {
        **atual,
        "faturamento_cmp": base["faturamento"],
        "faturamento_delta_pct": _delta_pct(atual["faturamento"], base["faturamento"]) if cmp else None,
        "pedidos_delta_pct": _delta_pct(atual["pedidos"], base["pedidos"]) if cmp else None,
        "ticket_delta_pct": _delta_pct(atual["ticket"], base["ticket"]) if cmp else None,
        "tem_comparacao": cmp is not None,
    }


# ---------------------------------------------------------------- ranking

def ranking_vendedores(db: Session, f: FiltrosDashboard) -> list[dict]:
    where, params = build_where(f)
    rows = db.execute(text(f"""
        SELECT
            COALESCE(NULLIF(TRIM(ped.vendedor), ''), 'Sem vendedor') AS vendedor,
            SUM(ped.total_liquido)                AS receita,
            COUNT(*)                              AS pedidos,
            AVG(ped.total_liquido)                AS ticket,
            COUNT(DISTINCT ped.cliente_documento) AS clientes
        FROM pedido_mobile_pedido ped
        WHERE {where}
        GROUP BY COALESCE(NULLIF(TRIM(ped.vendedor), ''), 'Sem vendedor')
        ORDER BY receita DESC
    """), params).fetchall()
    total = sum(float(r.receita or 0) for r in rows) or 1.0
    return [{
        "vendedor": r.vendedor,
        "receita": float(r.receita or 0),
        "pedidos": int(r.pedidos or 0),
        "ticket": float(r.ticket or 0),
        "clientes": int(r.clientes or 0),
        "pct_total": round(float(r.receita or 0) / total * 100, 1),
    } for r in rows]


# ---------------------------------------------------------------- clientes em risco

def clientes_risco(db: Session, f: FiltrosDashboard, *, hoje) -> dict:
    # Risco é medido vs. hoje; ignora o período, mas respeita vendedor/representada.
    where, params = build_where(f, com_periodo=False)
    params = {**params, "hoje": hoje}
    base = f"""
        FROM pedido_mobile_pedido ped
        LEFT JOIN cliente_pedido_mobile pm ON pm.documento = ped.cliente_documento
        WHERE {where} AND (pm.inativo = FALSE OR pm.inativo IS NULL)
        GROUP BY ped.cliente_documento
        HAVING (:hoje - MAX(ped.emissao)) >= 30
    """
    lista_rows = db.execute(text(f"""
        SELECT
            ped.cliente_documento AS documento,
            MAX(COALESCE(NULLIF(TRIM(pm.nome_fantasia), ''), pm.razao_social, ped.cliente_documento)) AS nome,
            MAX(COALESCE(NULLIF(TRIM(ped.vendedor), ''), '—')) AS vendedor,
            MAX(ped.emissao) AS ultima_compra,
            (:hoje - MAX(ped.emissao)) AS dias,
            SUM(ped.total_liquido) AS receita
        {base}
        ORDER BY receita DESC LIMIT 25
    """), params).fetchall()

    cont = db.execute(text(f"""
        SELECT
            COUNT(*) FILTER (WHERE dias BETWEEN 30 AND 60) AS leve,
            COUNT(*) FILTER (WHERE dias BETWEEN 61 AND 90) AS medio,
            COUNT(*) FILTER (WHERE dias > 90) AS alto
        FROM (SELECT (:hoje - MAX(ped.emissao)) AS dias {base}) sub
    """), params).fetchone()

    return {
        "lista": [{
            "documento": r.documento,
            "nome": r.nome or "",
            "vendedor": r.vendedor,
            "ultima_compra": r.ultima_compra.strftime("%d/%m/%Y") if r.ultima_compra else None,
            "dias": int(r.dias or 0),
            "receita": float(r.receita or 0),
        } for r in lista_rows],
        "contagem": {"leve": int(cont.leve or 0), "medio": int(cont.medio or 0), "alto": int(cont.alto or 0)},
    }


# ---------------------------------------------------------------- série temporal

def _coletar_serie(db, where, params, ini, fim, por_mes):
    """Série DENSA (inclui buckets sem venda) entre ini e fim. Lista de (rotulo, receita, pedidos)."""
    if por_mes:
        rows = db.execute(text(f"""
            SELECT date_trunc('month', ped.emissao)::date AS b,
                   SUM(ped.total_liquido) AS receita, COUNT(*) AS pedidos
            FROM pedido_mobile_pedido ped WHERE {where}
            GROUP BY 1
        """), params).fetchall()
        mapa = {r.b: (float(r.receita or 0), int(r.pedidos)) for r in rows}
        out, cur = [], ini.replace(day=1)
        while cur <= fim:
            rec, ped = mapa.get(cur, (0.0, 0))
            out.append((cur.strftime("%m/%Y"), rec, ped))
            cur = _shift_meses(cur, 1)
        return out
    rows = db.execute(text(f"""
        SELECT ped.emissao AS b, SUM(ped.total_liquido) AS receita, COUNT(*) AS pedidos
        FROM pedido_mobile_pedido ped WHERE {where}
        GROUP BY ped.emissao
    """), params).fetchall()
    mapa = {r.b: (float(r.receita or 0), int(r.pedidos)) for r in rows}
    out, cur = [], ini
    while cur <= fim:
        rec, ped = mapa.get(cur, (0.0, 0))
        out.append((cur.strftime("%d/%m"), rec, ped))
        cur = cur + timedelta(days=1)
    return out


def serie_temporal(db: Session, f: FiltrosDashboard) -> list[dict]:
    where, params = build_where(f)
    por_mes = (f.fim - f.inicio).days > 62

    atual = _coletar_serie(db, where, params, f.inicio, f.fim, por_mes)

    cmp = derivar_comparacao(f)
    comparado = None
    if cmp:
        comparado = _coletar_serie(db, where, {**params, "inicio": cmp[0], "fim": cmp[1]}, cmp[0], cmp[1], por_mes)

    pontos = []
    for i, (rotulo, receita, pedidos) in enumerate(atual):
        receita_cmp = comparado[i][1] if comparado and i < len(comparado) else None
        pontos.append({"rotulo": rotulo, "receita": receita, "pedidos": pedidos, "receita_cmp": receita_cmp})
    return pontos


# ---------------------------------------------------------------- top dimensão

def top_dimensao(db: Session, f: FiltrosDashboard, *, dimensao: str, limite: int = 10) -> list[dict]:
    coluna = {"representada": "ped.representada"}.get(dimensao)
    if coluna:  # dimensão no nível do pedido
        where, params = build_where(f)
        rows = db.execute(text(f"""
            SELECT COALESCE(NULLIF(TRIM({coluna}), ''), '—') AS nome,
                   SUM(ped.total_liquido) AS receita
            FROM pedido_mobile_pedido ped
            WHERE {where}
            GROUP BY COALESCE(NULLIF(TRIM({coluna}), ''), '—')
            ORDER BY receita DESC LIMIT :limite
        """), {**params, "limite": limite}).fetchall()
    else:  # produto: nível do item
        where, params = build_where(f)
        rows = db.execute(text(f"""
            SELECT MAX(pit.produto_descricao) AS nome, SUM(pit.total_liquido) AS receita
            FROM pedido_mobile_item pit
            JOIN pedido_mobile_pedido ped ON ped.pedido_numero = pit.pedido_numero
            WHERE {where} AND pit.produto_codigo IS NOT NULL
            GROUP BY pit.produto_codigo
            ORDER BY receita DESC LIMIT :limite
        """), {**params, "limite": limite}).fetchall()
    total = sum(float(r.receita or 0) for r in rows) or 1.0
    return [{"nome": r.nome or "", "receita": float(r.receita or 0),
             "pct_total": round(float(r.receita or 0) / total * 100, 1)} for r in rows]


# ---------------------------------------------------------------- opções e agregador

def opcoes_filtro(db: Session) -> dict:
    origem = "pedido_mobile_pedido"
    return {
        "vendedores": list(valores_distintos(db, "vendedor", origem=origem)),
        "representadas": list(valores_distintos(db, "representada", origem=origem)),
        "situacoes": list(valores_distintos(db, "situacao", origem=origem)),
    }


def montar_dados(db: Session, f: FiltrosDashboard, *, hoje) -> dict:
    return {
        "filtros": f,
        "opcoes": opcoes_filtro(db),
        "kpis": kpis(db, f),
        "serie": serie_temporal(db, f),
        "ranking": ranking_vendedores(db, f),
        "risco": clientes_risco(db, f, hoje=hoje),
        "top_representadas": top_dimensao(db, f, dimensao="representada"),
        "top_produtos": top_dimensao(db, f, dimensao="produto"),
    }
