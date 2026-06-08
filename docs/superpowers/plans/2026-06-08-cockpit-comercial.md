# Cockpit do Gestor Comercial (Fase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o dashboard global e estático num cockpit comercial fatiável por período, vendedor, representada e situação, com comparação temporal livre e painéis que reagem aos filtros.

**Architecture:** Estado dos filtros na querystring; rota `/dashboard` re-renderiza via HTMX (página completa em request normal, parcial dos painéis em request HTMX). SQL agregado isolado em `dashboard_service.py`; lógica pura (filtros, derivação de período de comparação, chave de cache) em `dashboard_filters.py`; cache em memória por recorte. Suíte pytest contra um banco PostgreSQL de teste com isolamento por transação.

**Tech Stack:** FastAPI, SQLAlchemy Core (`text()` parametrizado), Jinja2 + HTMX, Chart.js (já presente), PostgreSQL 16, pytest.

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `app/dashboard_filters.py` (novo) | `FiltrosDashboard` (parsing/padrões), derivação do período de comparação, chave de cache. Lógica pura, sem DB. |
| `app/dashboard_service.py` (novo) | Monta `WHERE` parametrizado e executa as queries agregadas (KPIs, série, ranking, risco, top). Retorna dicts. |
| `app/routers/dashboard.py` (modificar) | Lê filtros da query, orquestra cache por recorte, escolhe render completo vs parcial HTMX. |
| `app/templates/dashboard.html` (modificar) | Página: `head_extra` (Chart.js) + barra de filtros + container de painéis. |
| `app/templates/partials/dashboard_filtros.html` (novo) | Barra de filtros (período, comparação, vendedor, representada, situação). |
| `app/templates/partials/dashboard_paineis.html` (novo) | Container que o HTMX troca: KPIs, série, ranking, risco, top. |
| `app/tests/conftest.py` (novo) | Engine do banco de teste, DDL das tabelas, fixture `db` com rollback por teste, helpers de seed. |
| `app/tests/test_dashboard_filters.py` (novo) | Testes da lógica pura. |
| `app/tests/test_dashboard_service.py` (novo) | Testes das queries contra dados semeados. |
| `app/tests/test_dashboard_route.py` (novo) | Testes da rota (200, parcial HTMX, recorte vazio). |
| `app/requirements.txt` (modificar) | Adicionar `pytest`. |

Comandos de teste rodam no container: `docker exec prospec_app pytest -q`.

---

## Task 1: Infraestrutura de testes (pytest + banco de teste)

**Files:**
- Modify: `app/requirements.txt`
- Create: `app/tests/__init__.py`
- Create: `app/tests/conftest.py`
- Create: `app/pytest.ini`

- [ ] **Step 1: Adicionar pytest ao requirements**

Em `app/requirements.txt`, ao final, acrescentar:

```
# ===========================================
# Testes
# ===========================================
pytest==8.3.3
```

- [ ] **Step 2: Instalar no container**

Run: `docker exec prospec_app pip install pytest==8.3.3`
Expected: "Successfully installed pytest-8.3.3"

- [ ] **Step 3: Config do pytest**

Create `app/pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -ra
```

- [ ] **Step 4: Pacote de testes**

Create `app/tests/__init__.py` (vazio).

- [ ] **Step 5: conftest com banco de teste e isolamento por transação**

Create `app/tests/conftest.py`:

```python
import re

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import settings


def _trocar_db(url: str, novo_nome: str) -> str:
    """Troca o nome do banco no final da URL de conexão."""
    return re.sub(r"/([^/?]+)(\?|$)", f"/{novo_nome}" + r"\2", url, count=1)


NOME_TESTE = "prospec_test"
TEST_URL = _trocar_db(settings.database_url, NOME_TESTE)

DDL = """
CREATE TABLE IF NOT EXISTS cliente_pedido_mobile (
    documento      VARCHAR(14) PRIMARY KEY,
    tipo_documento VARCHAR(4),
    razao_social   VARCHAR(200),
    nome_fantasia  VARCHAR(200),
    vendedor       VARCHAR(100),
    inativo        BOOLEAN DEFAULT FALSE,
    municipio      VARCHAR(100),
    uf             VARCHAR(2),
    ultima_compra_em DATE,
    atualizado_em  TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS pedido_mobile_pedido (
    pedido_numero     INTEGER PRIMARY KEY,
    cliente_documento VARCHAR(20) NOT NULL,
    vendedor          VARCHAR(100),
    representada      VARCHAR(200),
    tabela_preco      VARCHAR(100),
    plano_pagamento   VARCHAR(200),
    desconto1         DECIMAL(10,4) DEFAULT 0,
    desconto2         DECIMAL(10,4) DEFAULT 0,
    desconto3         DECIMAL(10,4) DEFAULT 0,
    emissao           DATE,
    entrega           DATE,
    situacao          VARCHAR(50),
    orcamento         BOOLEAN DEFAULT FALSE,
    total_bruto       DECIMAL(12,2),
    total_liquido     DECIMAL(12,2),
    atualizado_em     TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS pedido_mobile_item (
    id                SERIAL PRIMARY KEY,
    pedido_numero     INTEGER NOT NULL REFERENCES pedido_mobile_pedido(pedido_numero) ON DELETE CASCADE,
    produto_codigo    VARCHAR(50),
    produto_descricao VARCHAR(300),
    produto_unidade   VARCHAR(10),
    quantidade        DECIMAL(12,4),
    preco_unitario    DECIMAL(12,4),
    desconto          DECIMAL(10,4) DEFAULT 0,
    total_liquido     DECIMAL(12,2),
    informacoes_adicionais TEXT
);
"""


def _criar_banco_de_teste():
    """Cria o banco de teste se não existir (conecta no banco de manutenção)."""
    maint = _trocar_db(settings.database_url, "postgres")
    eng = create_engine(maint, isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        existe = c.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": NOME_TESTE}
        ).scalar()
        if not existe:
            c.execute(text(f'CREATE DATABASE "{NOME_TESTE}"'))
    eng.dispose()


@pytest.fixture(scope="session")
def engine():
    _criar_banco_de_teste()
    eng = create_engine(TEST_URL)
    with eng.begin() as c:
        for stmt in DDL.split(";"):
            if stmt.strip():
                c.execute(text(stmt))
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """Sessão isolada: tudo é revertido ao fim de cada teste."""
    conn = engine.connect()
    trans = conn.begin()
    sess = sessionmaker(bind=conn)()
    try:
        yield sess
    finally:
        sess.close()
        trans.rollback()
        conn.close()
```

- [ ] **Step 6: Teste fumaça da fixture**

Create temporariamente no fim de `app/tests/conftest.py` nada — em vez disso valide com um teste mínimo. Create `app/tests/test_smoke_db.py`:

```python
from sqlalchemy import text


def test_fixture_db_conecta(db):
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_tabelas_existem(db):
    for t in ("cliente_pedido_mobile", "pedido_mobile_pedido", "pedido_mobile_item"):
        db.execute(text(f"SELECT COUNT(*) FROM {t}"))
```

- [ ] **Step 7: Rodar**

Run: `docker exec prospec_app pytest tests/test_smoke_db.py -v`
Expected: 2 passed.

- [ ] **Step 8: Commit**

```bash
git add app/requirements.txt app/pytest.ini app/tests/
git commit -m "test: infraestrutura pytest com banco de teste isolado por transacao"
```

---

## Task 2: Modelo de filtros e parsing (lógica pura)

**Files:**
- Create: `app/dashboard_filters.py`
- Create: `app/tests/test_dashboard_filters.py`

- [ ] **Step 1: Teste de parsing e padrões**

Create `app/tests/test_dashboard_filters.py`:

```python
from datetime import date

from dashboard_filters import FiltrosDashboard


def test_padrao_e_mes_corrente():
    f = FiltrosDashboard.from_query({}, hoje=date(2026, 6, 8))
    assert f.inicio == date(2026, 6, 1)
    assert f.fim == date(2026, 6, 8)
    assert f.comparacao == "mes_anterior"
    assert f.vendedor is None
    assert f.situacao == "confirmados"


def test_intervalo_explicito():
    f = FiltrosDashboard.from_query(
        {"inicio": "2026-03-01", "fim": "2026-03-15", "vendedor": "Joao"},
        hoje=date(2026, 6, 8),
    )
    assert f.inicio == date(2026, 3, 1)
    assert f.fim == date(2026, 3, 15)
    assert f.vendedor == "Joao"


def test_intervalo_invertido_normaliza():
    f = FiltrosDashboard.from_query(
        {"inicio": "2026-03-15", "fim": "2026-03-01"}, hoje=date(2026, 6, 8)
    )
    assert f.inicio <= f.fim


def test_vazio_string_vira_none():
    f = FiltrosDashboard.from_query({"vendedor": "", "representada": "  "}, hoje=date(2026, 6, 8))
    assert f.vendedor is None
    assert f.representada is None
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_filters.py -v`
Expected: FAIL — "No module named 'dashboard_filters'".

- [ ] **Step 3: Implementar o modelo**

Create `app/dashboard_filters.py`:

```python
from dataclasses import dataclass
from datetime import date


def _parse_date(s, padrao):
    if not s:
        return padrao
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return padrao


def _limpar(v):
    v = (v or "").strip()
    return v or None


_COMPARACOES = {"mes_anterior", "ano_anterior", "trimestre_anterior", "personalizado", "nenhuma"}
_SITUACOES_ESPECIAIS = {"confirmados", "todos"}


@dataclass
class FiltrosDashboard:
    inicio: date
    fim: date
    comparacao: str
    cmp_inicio: date | None
    cmp_fim: date | None
    vendedor: str | None
    representada: str | None
    situacao: str

    @classmethod
    def from_query(cls, q: dict, hoje: date) -> "FiltrosDashboard":
        inicio = _parse_date(q.get("inicio"), hoje.replace(day=1))
        fim = _parse_date(q.get("fim"), hoje)
        if fim < inicio:
            inicio, fim = fim, inicio

        comparacao = q.get("comparacao") or "mes_anterior"
        if comparacao not in _COMPARACOES:
            comparacao = "mes_anterior"

        cmp_inicio = _parse_date(q.get("cmp_inicio"), None)
        cmp_fim = _parse_date(q.get("cmp_fim"), None)

        situacao = q.get("situacao") or "confirmados"

        return cls(
            inicio=inicio,
            fim=fim,
            comparacao=comparacao,
            cmp_inicio=cmp_inicio,
            cmp_fim=cmp_fim,
            vendedor=_limpar(q.get("vendedor")),
            representada=_limpar(q.get("representada")),
            situacao=situacao,
        )
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_filters.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_filters.py app/tests/test_dashboard_filters.py
git commit -m "feat: modelo FiltrosDashboard com parsing e padroes"
```

---

## Task 3: Derivação do período de comparação (lógica pura)

**Files:**
- Modify: `app/dashboard_filters.py`
- Modify: `app/tests/test_dashboard_filters.py`

- [ ] **Step 1: Testes da derivação**

Acrescentar em `app/tests/test_dashboard_filters.py`:

```python
from dashboard_filters import derivar_comparacao


def _f(inicio, fim, comparacao, cmp_inicio=None, cmp_fim=None):
    from dashboard_filters import FiltrosDashboard
    return FiltrosDashboard(inicio=inicio, fim=fim, comparacao=comparacao,
                            cmp_inicio=cmp_inicio, cmp_fim=cmp_fim,
                            vendedor=None, representada=None, situacao="confirmados")


def test_comp_mes_anterior():
    ini, fim = derivar_comparacao(_f(date(2026, 6, 1), date(2026, 6, 8), "mes_anterior"))
    assert (ini, fim) == (date(2026, 5, 1), date(2026, 5, 8))


def test_comp_ano_anterior():
    ini, fim = derivar_comparacao(_f(date(2026, 6, 1), date(2026, 6, 8), "ano_anterior"))
    assert (ini, fim) == (date(2025, 6, 1), date(2025, 6, 8))


def test_comp_trimestre_anterior():
    ini, fim = derivar_comparacao(_f(date(2026, 6, 1), date(2026, 6, 30), "trimestre_anterior"))
    assert (ini, fim) == (date(2026, 3, 1), date(2026, 3, 30))


def test_comp_personalizado():
    ini, fim = derivar_comparacao(
        _f(date(2026, 6, 1), date(2026, 6, 8), "personalizado", date(2026, 1, 1), date(2026, 1, 31))
    )
    assert (ini, fim) == (date(2026, 1, 1), date(2026, 1, 31))


def test_comp_nenhuma():
    assert derivar_comparacao(_f(date(2026, 6, 1), date(2026, 6, 8), "nenhuma")) is None


def test_comp_clampa_dia():
    # 31/03 menos 1 mês -> fevereiro não tem dia 31 -> clampa para 28
    ini, fim = derivar_comparacao(_f(date(2026, 3, 1), date(2026, 3, 31), "mes_anterior"))
    assert (ini, fim) == (date(2026, 2, 1), date(2026, 2, 28))
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_filters.py -k comp -v`
Expected: FAIL — "cannot import name 'derivar_comparacao'".

- [ ] **Step 3: Implementar a derivação**

Acrescentar em `app/dashboard_filters.py`:

```python
import calendar


def _shift_meses(d: date, meses: int) -> date:
    total = (d.year * 12 + (d.month - 1)) + meses
    ano, mes = divmod(total, 12)
    mes += 1
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(d.day, ultimo_dia))


def derivar_comparacao(f: "FiltrosDashboard") -> tuple[date, date] | None:
    """Retorna (inicio, fim) do período de comparação, ou None se 'nenhuma'."""
    if f.comparacao == "nenhuma":
        return None
    if f.comparacao == "personalizado":
        if f.cmp_inicio and f.cmp_fim:
            return (f.cmp_inicio, f.cmp_fim)
        return None
    deslocamento = {"mes_anterior": -1, "trimestre_anterior": -3, "ano_anterior": -12}[f.comparacao]
    return (_shift_meses(f.inicio, deslocamento), _shift_meses(f.fim, deslocamento))
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_filters.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_filters.py app/tests/test_dashboard_filters.py
git commit -m "feat: derivacao do periodo de comparacao (mes/trimestre/ano/personalizado)"
```

---

## Task 4: Chave de cache (lógica pura)

**Files:**
- Modify: `app/dashboard_filters.py`
- Modify: `app/tests/test_dashboard_filters.py`

- [ ] **Step 1: Teste**

Acrescentar em `app/tests/test_dashboard_filters.py`:

```python
def test_chave_cache_distingue_recortes():
    a = FiltrosDashboard.from_query({"vendedor": "Joao"}, hoje=date(2026, 6, 8))
    b = FiltrosDashboard.from_query({"vendedor": "Maria"}, hoje=date(2026, 6, 8))
    c = FiltrosDashboard.from_query({"vendedor": "Joao"}, hoje=date(2026, 6, 8))
    assert a.chave_cache() != b.chave_cache()
    assert a.chave_cache() == c.chave_cache()
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_filters.py -k chave -v`
Expected: FAIL — "no attribute 'chave_cache'".

- [ ] **Step 3: Implementar**

Acrescentar como método em `FiltrosDashboard`:

```python
    def chave_cache(self) -> str:
        return "|".join(str(x) for x in (
            self.inicio, self.fim, self.comparacao, self.cmp_inicio, self.cmp_fim,
            self.vendedor, self.representada, self.situacao,
        ))
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_filters.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_filters.py app/tests/test_dashboard_filters.py
git commit -m "feat: chave de cache por recorte de filtros"
```

---

## Task 5: WHERE parametrizado do serviço

**Files:**
- Create: `app/dashboard_service.py`
- Create: `app/tests/test_dashboard_service.py`

- [ ] **Step 1: Teste do WHERE + helper de seed**

Create `app/tests/test_dashboard_service.py`:

```python
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


def test_where_confirmados_no_periodo(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    where, params = svc.build_where(f)
    total = db.execute(text(f"SELECT COALESCE(SUM(total_liquido),0) FROM pedido_mobile_pedido ped WHERE {where}"), params).scalar()
    # pedidos 1 e 2 (3 é cancelado, 4 é orçamento, 5 é maio) -> 1500
    assert float(total) == 1500.0


def test_where_filtra_vendedor(db):
    _seed(db)
    f = FiltrosDashboard.from_query(
        {"inicio": "2026-06-01", "fim": "2026-06-30", "vendedor": "Maria"}, hoje=date(2026, 6, 8)
    )
    where, params = svc.build_where(f)
    total = db.execute(text(f"SELECT COALESCE(SUM(total_liquido),0) FROM pedido_mobile_pedido ped WHERE {where}"), params).scalar()
    assert float(total) == 500.0
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -v`
Expected: FAIL — "No module named 'dashboard_service'".

- [ ] **Step 3: Implementar build_where**

Create `app/dashboard_service.py`:

```python
from sqlalchemy import text
from sqlalchemy.orm import Session

from dashboard_filters import FiltrosDashboard, derivar_comparacao

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
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_service.py app/tests/test_dashboard_service.py
git commit -m "feat: WHERE parametrizado do dashboard_service"
```

---

## Task 6: KPIs com comparação

**Files:**
- Modify: `app/dashboard_service.py`
- Modify: `app/tests/test_dashboard_service.py`

- [ ] **Step 1: Teste dos KPIs**

Acrescentar em `app/tests/test_dashboard_service.py`:

```python
def test_kpis_periodo_e_comparacao(db):
    _seed(db)
    f = FiltrosDashboard.from_query(
        {"inicio": "2026-06-01", "fim": "2026-06-30", "comparacao": "mes_anterior"},
        hoje=date(2026, 6, 8),
    )
    k = svc.kpis(db, f)
    assert k["faturamento"] == 1500.0          # jun: pedidos 1+2
    assert k["pedidos"] == 2
    assert k["clientes"] == 2                   # 111 e 222
    assert k["faturamento_cmp"] == 300.0        # maio: pedido 5
    assert k["faturamento_delta_pct"] == 400.0  # (1500-300)/300*100
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k kpis -v`
Expected: FAIL — "no attribute 'kpis'".

- [ ] **Step 3: Implementar kpis()**

Acrescentar em `app/dashboard_service.py`:

```python
def _agregar(db: Session, where: str, params: dict) -> dict:
    row = db.execute(text(f"""
        SELECT
            COALESCE(SUM(ped.total_liquido), 0)              AS faturamento,
            COUNT(*)                                         AS pedidos,
            COUNT(DISTINCT ped.cliente_documento)            AS clientes,
            COALESCE(AVG(ped.total_liquido), 0)              AS ticket
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
        cmp_where, cmp_params = build_where(f)
        cmp_params = {**cmp_params, "inicio": cmp[0], "fim": cmp[1]}
        base = _agregar(db, cmp_where, cmp_params)
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
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k kpis -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_service.py app/tests/test_dashboard_service.py
git commit -m "feat: KPIs do cockpit com variacao vs periodo de comparacao"
```

---

## Task 7: Ranking de vendedores

**Files:**
- Modify: `app/dashboard_service.py`
- Modify: `app/tests/test_dashboard_service.py`

- [ ] **Step 1: Teste**

Acrescentar em `app/tests/test_dashboard_service.py`:

```python
def test_ranking_vendedores(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    r = svc.ranking_vendedores(db, f)
    assert [v["vendedor"] for v in r] == ["Joao", "Maria"]  # ordenado por receita desc
    assert r[0]["receita"] == 1000.0
    assert r[0]["clientes"] == 1
    assert r[1]["receita"] == 500.0
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k ranking -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Acrescentar em `app/dashboard_service.py`:

```python
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
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k ranking -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_service.py app/tests/test_dashboard_service.py
git commit -m "feat: ranking de vendedores do cockpit"
```

---

## Task 8: Clientes em risco (medido vs. hoje, respeita vendedor/representada)

**Files:**
- Modify: `app/dashboard_service.py`
- Modify: `app/tests/test_dashboard_service.py`

- [ ] **Step 1: Teste**

Acrescentar em `app/tests/test_dashboard_service.py`:

```python
def test_clientes_risco_usa_hoje_e_filtra_vendedor(db):
    _seed(db)
    # hoje = 2026-09-01: última compra do 111 foi 07/06 (>=30d), do 222 foi 06/06
    f = FiltrosDashboard.from_query({"vendedor": "Joao"}, hoje=date(2026, 9, 1))
    risco = svc.clientes_risco(db, f, hoje=date(2026, 9, 1))
    docs = [c["documento"] for c in risco["lista"]]
    assert "111" in docs           # carteira do Joao, parado há >30d
    assert "222" not in docs       # é do Maria, filtrado fora
    assert risco["contagem"]["alto"] >= 1   # >90d
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k risco -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Acrescentar em `app/dashboard_service.py`:

```python
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
```

> Nota: este desenho corrige a duplicação por vendedor citada no spec — o `GROUP BY` é só por `cliente_documento`, e nome/vendedor saem por `MAX`.

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k risco -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_service.py app/tests/test_dashboard_service.py
git commit -m "feat: clientes em risco (vs hoje) sem duplicacao por vendedor"
```

---

## Task 9: Série temporal + top representadas/produtos

**Files:**
- Modify: `app/dashboard_service.py`
- Modify: `app/tests/test_dashboard_service.py`

- [ ] **Step 1: Testes**

Acrescentar em `app/tests/test_dashboard_service.py`:

```python
def test_serie_temporal_agrupa_por_dia(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    serie = svc.serie_temporal(db, f)
    receitas = {p["rotulo"]: p["receita"] for p in serie}
    assert receitas.get("05/06") == 1000.0
    assert receitas.get("06/06") == 500.0


def test_top_representadas(db):
    _seed(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    top = svc.top_dimensao(db, f, dimensao="representada")
    assert top[0]["nome"] == "Alpha"
    assert top[0]["receita"] == 1000.0
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k "serie or top" -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Acrescentar em `app/dashboard_service.py`:

```python
def serie_temporal(db: Session, f: FiltrosDashboard) -> list[dict]:
    where, params = build_where(f)
    dias = (f.fim - f.inicio).days
    # granularidade: dia até ~62d, senão mês
    if dias <= 62:
        bucket, fmt = "day", "DD/MM"
    else:
        bucket, fmt = "month", "MM/YYYY"
    rows = db.execute(text(f"""
        SELECT TO_CHAR(date_trunc('{bucket}', ped.emissao), '{fmt}') AS rotulo,
               date_trunc('{bucket}', ped.emissao) AS ord,
               SUM(ped.total_liquido) AS receita,
               COUNT(*) AS pedidos
        FROM pedido_mobile_pedido ped
        WHERE {where}
        GROUP BY date_trunc('{bucket}', ped.emissao)
        ORDER BY ord
    """), params).fetchall()
    return [{"rotulo": r.rotulo, "receita": float(r.receita or 0), "pedidos": int(r.pedidos)} for r in rows]


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
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_service.py app/tests/test_dashboard_service.py
git commit -m "feat: serie temporal e top representadas/produtos do cockpit"
```

---

## Task 10: Opções de filtro (distintos) + agregador `montar_dados`

**Files:**
- Modify: `app/dashboard_service.py`
- Modify: `app/tests/test_dashboard_service.py`

- [ ] **Step 1: Testes**

Acrescentar em `app/tests/test_dashboard_service.py`:

```python
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
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -k "opcoes or montar" -v`
Expected: FAIL.

- [ ] **Step 3: Implementar**

Acrescentar em `app/dashboard_service.py`:

```python
def opcoes_filtro(db: Session) -> dict:
    vend = db.execute(text("""
        SELECT DISTINCT TRIM(vendedor) AS v FROM pedido_mobile_pedido
        WHERE NULLIF(TRIM(vendedor), '') IS NOT NULL ORDER BY v
    """)).scalars().all()
    repr_ = db.execute(text("""
        SELECT DISTINCT TRIM(representada) AS r FROM pedido_mobile_pedido
        WHERE NULLIF(TRIM(representada), '') IS NOT NULL ORDER BY r
    """)).scalars().all()
    sit = db.execute(text("""
        SELECT DISTINCT TRIM(situacao) AS s FROM pedido_mobile_pedido
        WHERE NULLIF(TRIM(situacao), '') IS NOT NULL ORDER BY s
    """)).scalars().all()
    return {"vendedores": vend, "representadas": repr_, "situacoes": sit}


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
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_service.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add app/dashboard_service.py app/tests/test_dashboard_service.py
git commit -m "feat: opcoes de filtro e agregador montar_dados"
```

---

## Task 11: Rota /dashboard com filtros, cache por recorte e parcial HTMX

**Files:**
- Modify: `app/routers/dashboard.py`
- Create: `app/tests/test_dashboard_route.py`

- [ ] **Step 1: Teste da rota**

Create `app/tests/test_dashboard_route.py`:

```python
from datetime import date

from sqlalchemy import text

from dashboard_filters import FiltrosDashboard
import routers.dashboard as rota


def test_chave_de_cache_isola_recortes(monkeypatch):
    rota._cache.clear()
    chamadas = []

    def fake_montar(db, f, *, hoje):
        chamadas.append(f.vendedor)
        return {"marcador": f.vendedor}

    monkeypatch.setattr(rota.svc, "montar_dados", fake_montar)

    a = FiltrosDashboard.from_query({"vendedor": "Joao"}, hoje=date(2026, 6, 8))
    b = FiltrosDashboard.from_query({"vendedor": "Maria"}, hoje=date(2026, 6, 8))

    rota._dados_cacheados(None, a, hoje=date(2026, 6, 8))
    rota._dados_cacheados(None, a, hoje=date(2026, 6, 8))  # reusa cache
    rota._dados_cacheados(None, b, hoje=date(2026, 6, 8))

    assert chamadas == ["Joao", "Maria"]  # 'Joao' só calculou uma vez
```

- [ ] **Step 2: Rodar (deve falhar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_route.py -v`
Expected: FAIL — "no attribute '_dados_cacheados'".

- [ ] **Step 3: Reescrever a rota**

Substituir o conteúdo de `app/routers/dashboard.py` por:

```python
import time
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import dashboard_service as svc
from auth import require_login
from config import BRT
from dashboard_filters import FiltrosDashboard
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

_CACHE_TTL_SEGUNDOS = 180
_cache: dict = {}  # chave_cache -> (ts, dados)


def _dados_cacheados(db: Session, f: FiltrosDashboard, *, hoje) -> dict:
    chave = f.chave_cache()
    agora = time.monotonic()
    item = _cache.get(chave)
    if item and (agora - item[0]) < _CACHE_TTL_SEGUNDOS:
        return item[1]
    dados = svc.montar_dados(db, f, hoje=hoje)
    _cache[chave] = (agora, dados)
    return dados


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    hoje = datetime.now(BRT).date()
    f = FiltrosDashboard.from_query(dict(request.query_params), hoje=hoje)
    dados = _dados_cacheados(db, f, hoje=hoje)

    template = "partials/dashboard_paineis.html" if request.headers.get("HX-Request") else "dashboard.html"
    return templates.TemplateResponse(template, {
        "request": request,
        "user": current_user,
        "dados": dados,
    })
```

- [ ] **Step 4: Rodar (deve passar)**

Run: `docker exec prospec_app pytest tests/test_dashboard_route.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routers/dashboard.py app/tests/test_dashboard_route.py
git commit -m "feat: rota /dashboard com filtros na URL, cache por recorte e parcial HTMX"
```

---

## Task 12: Templates — barra de filtros + container de painéis

**Files:**
- Create: `app/templates/partials/dashboard_filtros.html`
- Create: `app/templates/partials/dashboard_paineis.html`
- Modify: `app/templates/dashboard.html`

- [ ] **Step 1: Container de painéis (parcial trocado pelo HTMX)**

Create `app/templates/partials/dashboard_paineis.html`. Renderiza KPIs, série (canvas + `{{ dados.serie | tojson }}`), ranking (tabela), risco (tabela com faixas) e top representadas/produtos. Reaproveita as classes Tailwind do `dashboard.html` atual (cards `bg-[#171717] border border-[#2e2e2e] rounded-xl`). Cada número de variação usa verde/vermelho conforme `*_delta_pct`. Inicia o(s) gráfico(s) Chart.js a partir do JSON embutido. Usa `| tojson` (nunca `| safe`).

```html
<div id="paineis" class="space-y-5">
  <!-- KPIs -->
  <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
    {% set k = dados.kpis %}
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-4">
      <div class="text-2xl font-bold text-[#f97316]">R$ {{ "{:,.0f}".format(k.faturamento).replace(",", ".") }}</div>
      <div class="text-xs text-[#888] mt-1">Faturamento
        {% if k.faturamento_delta_pct is not none %}
        <span class="{{ 'text-green-400' if k.faturamento_delta_pct >= 0 else 'text-red-400' }}">
          {{ '▲' if k.faturamento_delta_pct >= 0 else '▼' }} {{ k.faturamento_delta_pct|abs }}%</span>
        {% endif %}
      </div>
    </div>
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-4">
      <div class="text-2xl font-bold text-white">{{ k.pedidos }}</div>
      <div class="text-xs text-[#888] mt-1">Pedidos</div>
    </div>
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-4">
      <div class="text-2xl font-bold text-white">R$ {{ "{:,.0f}".format(k.ticket).replace(",", ".") }}</div>
      <div class="text-xs text-[#888] mt-1">Ticket médio</div>
    </div>
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-4">
      <div class="text-2xl font-bold text-white">{{ k.clientes }}</div>
      <div class="text-xs text-blue-400 mt-1">Clientes que compraram</div>
    </div>
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-4">
      <div class="text-2xl font-bold text-white">{{ dados.risco.contagem.leve + dados.risco.contagem.medio + dados.risco.contagem.alto }}</div>
      <div class="text-xs text-red-400 mt-1">Clientes em risco</div>
    </div>
  </div>

  <!-- Série + Ranking -->
  <div class="grid grid-cols-1 lg:grid-cols-5 gap-4">
    <div class="lg:col-span-3 bg-[#171717] rounded-xl border border-[#2e2e2e]">
      <div class="text-sm font-semibold text-white px-5 py-3 border-b border-[#2e2e2e]">Faturamento no período</div>
      <div class="p-4 h-72"><canvas id="chartSerie"></canvas></div>
    </div>
    <div class="lg:col-span-2 bg-[#171717] rounded-xl border border-[#2e2e2e]">
      <div class="text-sm font-semibold text-white px-5 py-3 border-b border-[#2e2e2e]">🏆 Ranking de vendedores</div>
      <table class="w-full text-sm">
        <thead class="bg-[#111]"><tr>
          <th class="px-4 py-2 text-left text-[10px] text-[#666] uppercase">Vendedor</th>
          <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase">Receita</th>
          <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase">Clientes</th>
        </tr></thead>
        <tbody class="divide-y divide-[#222]">
          {% for v in dados.ranking %}
          <tr class="hover:bg-[#1a1a1a]">
            <td class="px-4 py-2 text-[#ccc]">{{ loop.index }}. {{ v.vendedor }}</td>
            <td class="px-4 py-2 text-right text-[#ccc]">R$ {{ "{:,.0f}".format(v.receita).replace(",", ".") }}</td>
            <td class="px-4 py-2 text-right text-[#ccc]">{{ v.clientes }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Risco + Top representadas -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e]">
      <div class="text-sm font-semibold text-white px-5 py-3 border-b border-[#2e2e2e]">⚠️ Clientes em risco</div>
      <table class="w-full text-sm">
        <thead class="bg-[#111]"><tr>
          <th class="px-4 py-2 text-left text-[10px] text-[#666] uppercase">Cliente</th>
          <th class="px-4 py-2 text-left text-[10px] text-[#666] uppercase">Vendedor</th>
          <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase">Sem comprar</th>
          <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase">Receita</th>
        </tr></thead>
        <tbody class="divide-y divide-[#222]">
          {% for c in dados.risco.lista %}
          <tr class="hover:bg-[#1a1a1a]">
            <td class="px-4 py-2 text-[#ccc]">{{ c.nome }}</td>
            <td class="px-4 py-2 text-[#888] text-xs">{{ c.vendedor }}</td>
            <td class="px-4 py-2 text-right text-[#ccc]">{{ c.dias }}d</td>
            <td class="px-4 py-2 text-right text-[#ccc]">R$ {{ "{:,.0f}".format(c.receita).replace(",", ".") }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e]">
      <div class="text-sm font-semibold text-white px-5 py-3 border-b border-[#2e2e2e]">Top representadas</div>
      <table class="w-full text-sm">
        <thead class="bg-[#111]"><tr>
          <th class="px-4 py-2 text-left text-[10px] text-[#666] uppercase">Representada</th>
          <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase">Receita</th>
          <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase">% total</th>
        </tr></thead>
        <tbody class="divide-y divide-[#222]">
          {% for t in dados.top_representadas %}
          <tr class="hover:bg-[#1a1a1a]">
            <td class="px-4 py-2 text-[#ccc]">{{ t.nome }}</td>
            <td class="px-4 py-2 text-right text-[#ccc]">R$ {{ "{:,.0f}".format(t.receita).replace(",", ".") }}</td>
            <td class="px-4 py-2 text-right text-[#888]">{{ t.pct_total }}%</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <script>
    (function () {
      const serie = {{ dados.serie | tojson }};
      const el = document.getElementById('chartSerie');
      if (el && window.Chart) {
        if (el._chart) el._chart.destroy();
        el._chart = new Chart(el, {
          type: 'bar',
          data: { labels: serie.map(p => p.rotulo),
                  datasets: [{ data: serie.map(p => p.receita),
                               backgroundColor: 'rgba(249,115,22,0.7)', borderRadius: 4 }] },
          options: { maintainAspectRatio: false, plugins: { legend: { display: false } } }
        });
      }
    })();
  </script>
</div>
```

- [ ] **Step 2: Barra de filtros**

Create `app/templates/partials/dashboard_filtros.html`. Form com `hx-get="/dashboard"`, `hx-target="#paineis"`, `hx-swap="outerHTML"`, `hx-push-url="true"`, `hx-trigger="change"`. Campos: `inicio`/`fim` (date), `comparacao` (select com as 5 opções), `vendedor`/`representada`/`situacao` (selects populados de `dados.opcoes`). Seleção atual vinda de `dados.filtros`.

```html
<form id="filtros-dashboard"
      hx-get="/dashboard" hx-target="#paineis" hx-swap="outerHTML"
      hx-push-url="true" hx-trigger="change"
      class="sticky top-[53px] z-20 -mx-5 px-5 py-3 bg-[#111] border-b border-[#2a2a2a] flex flex-wrap items-end gap-2.5">
  {% set f = dados.filtros %}
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase">De</label>
    <input type="date" name="inicio" value="{{ f.inicio }}"
           class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5]">
  </div>
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase">Até</label>
    <input type="date" name="fim" value="{{ f.fim }}"
           class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5]">
  </div>
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase">Comparar com</label>
    <select name="comparacao" class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5]">
      {% for val, txt in [('mes_anterior','Mês anterior'),('ano_anterior','Mesmo período ano passado'),('trimestre_anterior','Trimestre anterior'),('nenhuma','Sem comparação')] %}
      <option value="{{ val }}" {% if f.comparacao == val %}selected{% endif %}>{{ txt }}</option>
      {% endfor %}
    </select>
  </div>
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase">Vendedor</label>
    <select name="vendedor" class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5]">
      <option value="">Todos</option>
      {% for v in dados.opcoes.vendedores %}<option value="{{ v }}" {% if f.vendedor == v %}selected{% endif %}>{{ v }}</option>{% endfor %}
    </select>
  </div>
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase">Representada</label>
    <select name="representada" class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5]">
      <option value="">Todas</option>
      {% for r in dados.opcoes.representadas %}<option value="{{ r }}" {% if f.representada == r %}selected{% endif %}>{{ r }}</option>{% endfor %}
    </select>
  </div>
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase">Situação</label>
    <select name="situacao" class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5]">
      <option value="confirmados" {% if f.situacao == 'confirmados' %}selected{% endif %}>Confirmados</option>
      <option value="todos" {% if f.situacao == 'todos' %}selected{% endif %}>Todos (inclui orçamentos)</option>
      {% for s in dados.opcoes.situacoes %}<option value="{{ s|lower }}" {% if f.situacao == s|lower %}selected{% endif %}>{{ s }}</option>{% endfor %}
    </select>
  </div>
</form>
```

- [ ] **Step 3: Reescrever dashboard.html**

Substituir o conteúdo de `app/templates/dashboard.html` por:

```html
{% extends "base.html" %}

{% block head_extra %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
{% endblock %}

{% block title %}Dashboard Comercial{% endblock %}

{% block content %}
{% include "partials/dashboard_filtros.html" %}
<div class="p-5">
  {% include "partials/dashboard_paineis.html" %}
</div>
{% endblock %}
```

- [ ] **Step 4: Verificar render autenticado (smoke)**

Run (cria script, executa e remove):

```bash
docker exec prospec_app python - <<'PY'
import requests
s = requests.Session()
s.post("http://localhost:8000/login", data={"email":"admin@sbr.local","senha":"Acesso06597"}, allow_redirects=False)
# página completa
full = s.get("http://localhost:8000/dashboard")
assert full.status_code == 200 and 'id="paineis"' in full.text and "Ranking de vendedores" in full.text
# parcial HTMX
part = s.get("http://localhost:8000/dashboard?vendedor=&comparacao=nenhuma", headers={"HX-Request":"true"})
assert part.status_code == 200 and part.text.strip().startswith('<div id="paineis"')
assert "<html" not in part.text  # parcial não traz a página inteira
print("SMOKE OK", len(full.text), len(part.text))
PY
```
Expected: "SMOKE OK ...".

- [ ] **Step 5: Commit**

```bash
git add app/templates/dashboard.html app/templates/partials/dashboard_filtros.html app/templates/partials/dashboard_paineis.html
git commit -m "feat: barra de filtros e paineis reativos do cockpit (HTMX)"
```

---

## Task 13: Suíte completa + validação final autenticada

**Files:** nenhum novo (validação).

- [ ] **Step 1: Rodar a suíte inteira**

Run: `docker exec prospec_app pytest -q`
Expected: todos passam (filters, service, route, smoke_db).

- [ ] **Step 2: Smoke autenticado com vários recortes**

Run:

```bash
docker exec prospec_app python - <<'PY'
import requests
s = requests.Session()
s.post("http://localhost:8000/login", data={"email":"admin@sbr.local","senha":"Acesso06597"}, allow_redirects=False)
casos = [
  "/dashboard",
  "/dashboard?inicio=2026-01-01&fim=2026-06-30&comparacao=ano_anterior",
  "/dashboard?comparacao=nenhuma&situacao=todos",
]
for u in casos:
    r = s.get("http://localhost:8000"+u)
    assert r.status_code == 200, (u, r.status_code)
    print("OK", u, len(r.text))
PY
```
Expected: 3 linhas "OK".

- [ ] **Step 3: Commit final (se houver ajuste)**

```bash
git add -A && git commit -m "test: validacao final do cockpit (suite + smoke autenticado)" || echo "nada a commitar"
git push origin main
```

---

## Notas de implementação

- **Sempre** parametrizar valores de filtro (`:vendedor`, `:inicio`, …); nunca interpolar valor de usuário na string SQL. Nomes de bucket/format da série (`day`/`month`, `DD/MM`) são literais controlados pelo código, não entrada de usuário.
- O `cmp_inicio`/`cmp_fim` só aparecem na UI quando `comparacao = personalizado` (refinamento de UI pode ser feito após a Fase 1 — o backend já suporta).
- Estados vazios: as tabelas Jinja já iteram listas vazias sem quebrar; KPIs com base 0 retornam `delta_pct = None` e a UI omite a seta.
- **Desvio consciente do spec — linha de comparação na série temporal:** o mockup mostrava uma linha pontilhada do período comparado sobre o gráfico de faturamento. Neste plano a série traz **apenas o período atual** (as barras); a comparação fica carregada pelos KPIs (▲▼). Motivo: alinhar dois períodos de tamanhos diferentes na mesma escala temporal agrega complexidade desproporcional ao valor na Fase 1. A série já retorna pontos estruturados — adicionar um `dataset` de linha depois é incremental. **Pendente decisão do usuário** no handoff: incluir agora ou deixar para a Fase 2.
- Após a Fase 1 validada em produção, retomar pelo roadmap (Fase 2 — visão analítica).
