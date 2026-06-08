from datetime import date

from sqlalchemy import text

import dashboard_service as svc
from dashboard_filters import FiltrosDashboard


def _seed(db):
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, razao_social, nome_fantasia, vendedor, inativo)
        VALUES ('111', 'Cli Um', 'Um', 'Joao', FALSE),
               ('222', 'Cli Dois', 'Dois', 'Maria', FALSE)
    """))
    db.execute(text("""
        INSERT INTO pedido_mobile_pedido
            (pedido_numero, cliente_documento, vendedor, representada, emissao, situacao, orcamento, total_liquido)
        VALUES
            (1, '111', 'Joao', 'Alpha', '2026-06-05', 'Enviado',   FALSE, 1000),
            (2, '222', 'Maria','Beta',  '2026-06-06', 'Enviado',   FALSE,  500),
            (3, '111', 'Joao', 'Alpha', '2026-06-07', 'Cancelado', FALSE,  999),
            (4, '111', 'Joao', 'Alpha', '2026-06-07', 'Enviado',   TRUE,   777),
            (5, '222', 'Maria','Beta',  '2026-05-10', 'Enviado',   FALSE,  300)
    """))


def _soma(db, where, params):
    return float(db.execute(text(
        f"SELECT COALESCE(SUM(total_liquido),0) FROM pedido_mobile_pedido ped WHERE {where}"
    ), params).scalar())


# ---- WHERE ----

def test_where_confirmados_no_periodo(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    where, params = svc.build_where(f)
    # pedidos 1 e 2 (3 cancelado, 4 orçamento, 5 é maio) -> 1500
    assert _soma(db, where, params) == 1500.0


def test_where_filtra_vendedor(db):
    _seed(db)
    f = FiltrosDashboard.from_query(
        {"inicio": "2026-06-01", "fim": "2026-06-30", "vendedor": "Maria"}, hoje=date(2026, 6, 8)
    )
    where, params = svc.build_where(f)
    assert _soma(db, where, params) == 500.0


# ---- KPIs ----

def test_kpis_periodo_e_comparacao(db):
    _seed(db)
    f = FiltrosDashboard.from_query(
        {"inicio": "2026-06-01", "fim": "2026-06-30", "comparacao": "mes_anterior"},
        hoje=date(2026, 6, 8),
    )
    k = svc.kpis(db, f)
    assert k["faturamento"] == 1500.0
    assert k["pedidos"] == 2
    assert k["clientes"] == 2
    assert k["faturamento_cmp"] == 300.0
    assert k["faturamento_delta_pct"] == 400.0


# ---- ranking ----

def test_ranking_vendedores(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    r = svc.ranking_vendedores(db, f)
    assert [v["vendedor"] for v in r] == ["Joao", "Maria"]
    assert r[0]["receita"] == 1000.0
    assert r[0]["clientes"] == 1
    assert r[1]["receita"] == 500.0


# ---- clientes em risco ----

def test_clientes_risco_usa_hoje_e_filtra_vendedor(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"vendedor": "Joao"}, hoje=date(2026, 9, 1))
    risco = svc.clientes_risco(db, f, hoje=date(2026, 9, 1))
    docs = [c["documento"] for c in risco["lista"]]
    assert "111" in docs
    assert "222" not in docs
    # última compra confirmada do 111 = 05/06; até 01/09 = 88 dias -> faixa "médio" (61-90)
    assert risco["contagem"]["medio"] >= 1
    c111 = next(c for c in risco["lista"] if c["documento"] == "111")
    assert c111["dias"] == 88


# ---- série temporal ----

def test_serie_temporal_agrupa_por_dia(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    serie = svc.serie_temporal(db, f)
    receitas = {p["rotulo"]: p["receita"] for p in serie}
    assert receitas.get("05/06") == 1000.0
    assert receitas.get("06/06") == 500.0


def test_serie_inclui_comparacao_alinhada_por_offset(db):
    _seed(db)
    f = FiltrosDashboard.from_query(
        {"inicio": "2026-06-01", "fim": "2026-06-30", "comparacao": "mes_anterior"},
        hoje=date(2026, 6, 8),
    )
    serie = svc.serie_temporal(db, f)
    por_rotulo = {p["rotulo"]: p for p in serie}
    assert por_rotulo["10/06"]["receita"] == 0.0
    assert por_rotulo["10/06"]["receita_cmp"] == 300.0
    assert por_rotulo["05/06"]["receita"] == 1000.0
    assert por_rotulo["05/06"]["receita_cmp"] == 0.0


# ---- top dimensão ----

def test_top_representadas(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    top = svc.top_dimensao(db, f, dimensao="representada")
    assert top[0]["nome"] == "Alpha"
    assert top[0]["receita"] == 1000.0


# ---- opções e agregador ----

def test_opcoes_filtro(db):
    _seed(db)
    ops = svc.opcoes_filtro(db)
    assert "Joao" in ops["vendedores"] and "Maria" in ops["vendedores"]
    assert "Alpha" in ops["representadas"]


def test_montar_dados_inclui_todos_paineis(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    dados = svc.montar_dados(db, f, hoje=date(2026, 6, 8))
    for chave in ("kpis", "serie", "ranking", "risco", "top_representadas", "opcoes", "filtros"):
        assert chave in dados
