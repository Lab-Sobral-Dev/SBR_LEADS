# Dashboard de Análise de Vendas (Curvas ABC) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar o dashboard de Análise de Vendas ao hub, com duas curvas ABC (produtos e representadas), critério selecionável (receita/quantidade), cortes configuráveis (50/30/20 padrão), Pareto + resumo + tabela com filtro por classe, em abas.

**Architecture:** Página irmã do cockpit em `GET /dashboard/analise`, reusando `FiltrosDashboard`, `build_where` e `opcoes_filtro`. Novo módulo `app/analise_service.py` faz toda a agregação e a classificação ABC (math pura, testável sem banco). A barra de filtros compartilhada é parametrizada (`acao`/`alvo`/`mostrar_abc`). Cache por recorte (TTL 180s) com chave incluindo critério e cortes. Tabs e chips de classe são client-side; trocar filtro/critério/corte refaz via HTMX.

**Tech Stack:** Python 3.11 + FastAPI, SQLAlchemy Core (`text`), Jinja2, HTMX, TailwindCSS, Chart.js 4.4.4, pytest + Postgres de teste.

**Convenções do projeto a respeitar:**
- Testes rodam a partir do diretório `app/` (há `app/pytest.ini` com `testpaths = tests`). Comando base: `cd app && python -m pytest tests/<arquivo> -v`.
- Os testes de serviço usam a fixture `db` (sessão isolada com rollback) de `app/tests/conftest.py` e fazem seed com SQL cru.
- Imports nos módulos de `app/` são sem prefixo `app.` (ex.: `import dashboard_service as svc`).
- Comentários e UI em português brasileiro. Commits no formato `tipo: descrição`.
- Commitar direto na `main` (sem branch), conforme preferência do usuário.

---

## File Structure

**Novos:**
- `app/analise_service.py` — agregação ABC + classificação. Funções: `cortes_canonico`, `parse_cortes`, `parse_criterio`, `_classificar`, `_itens_produto`, `_itens_representada`, `curva_abc`, `montar_analise`.
- `app/templates/analise.html` — página completa (estende `base.html`).
- `app/templates/partials/analise_paineis.html` — região `#paineis` (swap HTMX): abas + resumo + Pareto + tabela + JS.
- `app/tests/test_analise_service.py` — testes unitários do serviço.

**Modificados:**
- `app/routers/dashboard.py` — rota `/dashboard/analise` + cache dedicado.
- `app/tests/test_dashboard_route.py` — teste de isolamento do cache da análise.
- `app/templates/partials/dashboard_filtros.html` — parametrizar `acao`/`alvo` + bloco `mostrar_abc`.
- `app/templates/dashboards.html` — card "Análise de Vendas" → *Disponível*.

---

## Task 1: `cortes_canonico`, `parse_cortes` e `parse_criterio`

Funções puras de parsing/validação. Sem banco.

**Files:**
- Create: `app/analise_service.py`
- Test: `app/tests/test_analise_service.py`

- [ ] **Step 1: Write the failing test**

Criar `app/tests/test_analise_service.py`:

```python
import analise_service as svc


# ---- parsing de cortes ----

def test_cortes_canonico_valido():
    assert svc.cortes_canonico("70-20-10") == "70-20-10"


def test_cortes_canonico_invalido_volta_ao_padrao():
    assert svc.cortes_canonico("abc") == "50-30-20"
    assert svc.cortes_canonico(None) == "50-30-20"
    assert svc.cortes_canonico("") == "50-30-20"


def test_parse_cortes_retorna_tupla_a_b():
    assert svc.parse_cortes("50-30-20") == (50, 30)
    assert svc.parse_cortes("70-20-10") == (70, 20)
    assert svc.parse_cortes("80-15-5") == (80, 15)


def test_parse_cortes_invalido_usa_padrao():
    assert svc.parse_cortes("xpto") == (50, 30)
    assert svc.parse_cortes(None) == (50, 30)


# ---- parsing de critério ----

def test_parse_criterio_normaliza():
    assert svc.parse_criterio("receita") == "receita"
    assert svc.parse_criterio("QUANTIDADE") == "quantidade"
    assert svc.parse_criterio(" Quantidade ") == "quantidade"


def test_parse_criterio_invalido_usa_receita():
    assert svc.parse_criterio("xpto") == "receita"
    assert svc.parse_criterio(None) == "receita"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest tests/test_analise_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analise_service'`

- [ ] **Step 3: Write minimal implementation**

Criar `app/analise_service.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest tests/test_analise_service.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Commit**

```bash
git add app/analise_service.py app/tests/test_analise_service.py
git commit -m "feat: parsing de cortes e criterio da analise ABC"
```

---

## Task 2: `_classificar` — classificação ABC (math pura)

Recebe uma lista de itens (cada um com `receita` e `quantidade`) e devolve a lista
classificada + o resumo por classe. Sem banco.

**Files:**
- Modify: `app/analise_service.py`
- Test: `app/tests/test_analise_service.py`

- [ ] **Step 1: Write the failing test**

Adicionar ao final de `app/tests/test_analise_service.py`:

```python
# ---- classificação ABC (math pura) ----

def _itens(*pares):
    """Helper: cria itens a partir de (nome, receita, quantidade)."""
    return [{"codigo": n, "nome": n, "receita": float(r), "quantidade": float(q)}
            for n, r, q in pares]


def test_classificar_por_receita_50_30_20():
    # Receitas: 50, 30, 15, 5 (total 100). Corte 50/30/20.
    # Acumulado ANTES de cada item: 0, 50, 80, 95.
    #   item1 (antes 0  < 50) -> A
    #   item2 (antes 50 < 80) -> B
    #   item3 (antes 80 -> não <80) -> C
    #   item4 (antes 95) -> C
    itens = _itens(("P1", 50, 1), ("P2", 30, 1), ("P3", 15, 1), ("P4", 5, 1))
    saida, resumo = svc._classificar(itens, "receita", (50, 30))
    classes = {i["nome"]: i["classe"] for i in saida}
    assert classes == {"P1": "A", "P2": "B", "P3": "C", "P4": "C"}
    assert saida[0]["pct"] == 50.0
    assert saida[0]["pct_acumulado"] == 50.0
    assert saida[1]["pct_acumulado"] == 80.0
    assert resumo["A"]["itens"] == 1
    assert resumo["A"]["receita"] == 50.0
    assert resumo["A"]["pct"] == 50.0
    assert resumo["C"]["itens"] == 2
    assert resumo["total_itens"] == 4
    assert resumo["total_receita"] == 100.0


def test_classificar_ordena_e_muda_com_criterio_quantidade():
    # Por quantidade a ordem muda: P2 (qtd 90) vira o líder.
    itens = _itens(("P1", 90, 10), ("P2", 10, 90))
    saida, _ = svc._classificar(itens, "quantidade", (50, 30))
    assert [i["nome"] for i in saida] == ["P2", "P1"]
    assert saida[0]["classe"] == "A"  # P2: acumulado antes = 0 < 50
    assert saida[1]["classe"] == "C"  # P1: acumulado antes = 90 -> >= 80


def test_classificar_item_unico_eh_A():
    saida, resumo = svc._classificar(_itens(("UNICO", 123, 7)), "receita", (50, 30))
    assert saida[0]["classe"] == "A"
    assert saida[0]["pct_acumulado"] == 100.0
    assert resumo["A"]["itens"] == 1


def test_classificar_vazio_nao_quebra():
    saida, resumo = svc._classificar([], "receita", (50, 30))
    assert saida == []
    assert resumo["total_itens"] == 0
    assert resumo["total_receita"] == 0.0
    assert resumo["A"]["pct"] == 0.0


def test_classificar_total_zero_vira_tudo_C():
    saida, resumo = svc._classificar(_itens(("Z1", 0, 0), ("Z2", 0, 0)), "receita", (50, 30))
    assert all(i["classe"] == "C" for i in saida)
    assert all(i["pct"] == 0.0 for i in saida)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest tests/test_analise_service.py -k classificar -v`
Expected: FAIL — `AttributeError: module 'analise_service' has no attribute '_classificar'`

- [ ] **Step 3: Write minimal implementation**

Adicionar a `app/analise_service.py` (após `parse_criterio`):

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest tests/test_analise_service.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add app/analise_service.py app/tests/test_analise_service.py
git commit -m "feat: classificacao ABC pura (criterio receita/quantidade)"
```

---

## Task 3: `_itens_produto` + `curva_abc` para produtos (com banco)

**Files:**
- Modify: `app/analise_service.py`
- Test: `app/tests/test_analise_service.py`

- [ ] **Step 1: Write the failing test**

Adicionar ao topo de `app/tests/test_analise_service.py` os imports e helper de seed
(logo abaixo do `import analise_service as svc`):

```python
from datetime import date

from sqlalchemy import text

from dashboard_filters import FiltrosDashboard


def _seed_itens(db):
    db.execute(text("""
        INSERT INTO pedido_mobile_pedido
            (pedido_numero, cliente_documento, vendedor, representada, emissao, situacao, orcamento, total_liquido)
        VALUES
            (1, '111', 'Joao', 'Alpha', '2026-06-05', 'Enviado', FALSE, 100),
            (2, '222', 'Maria','Beta',  '2026-06-06', 'Enviado', FALSE,  60)
    """))
    db.execute(text("""
        INSERT INTO pedido_mobile_item
            (pedido_numero, produto_codigo, produto_descricao, quantidade, total_liquido)
        VALUES
            (1, 'A', 'Produto A', 2, 80),
            (1, 'B', 'Produto B', 5, 20),
            (2, 'A', 'Produto A', 3, 60)
    """))
```

E adicionar os testes:

```python
def test_curva_abc_produto_agrega_por_codigo(db):
    _seed_itens(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    curva = svc.curva_abc(db, f, dimensao="produto", criterio="receita", cortes=(50, 30))
    por_nome = {i["nome"]: i for i in curva["itens"]}
    # Produto A: 80 + 60 = 140; Produto B: 20. Total 160.
    assert por_nome["Produto A"]["receita"] == 140.0
    assert por_nome["Produto A"]["quantidade"] == 5.0  # 2 + 3
    assert por_nome["Produto B"]["receita"] == 20.0
    assert curva["itens"][0]["nome"] == "Produto A"  # ordenado por receita desc
    assert curva["itens"][0]["classe"] == "A"


def test_curva_abc_produto_respeita_filtro_periodo(db):
    _seed_itens(db)
    # Período que exclui tudo -> sem itens, sem exceção.
    f = FiltrosDashboard.from_query({"inicio": "2020-01-01", "fim": "2020-01-31"}, hoje=date(2026, 6, 8))
    curva = svc.curva_abc(db, f, dimensao="produto", criterio="receita", cortes=(50, 30))
    assert curva["itens"] == []
    assert curva["resumo"]["total_itens"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest tests/test_analise_service.py -k curva_abc_produto -v`
Expected: FAIL — `AttributeError: module 'analise_service' has no attribute 'curva_abc'`

- [ ] **Step 3: Write minimal implementation**

Adicionar a `app/analise_service.py`. Primeiro os imports no topo do arquivo
(logo abaixo do docstring do módulo):

```python
from sqlalchemy import text
from sqlalchemy.orm import Session

from dashboard_filters import FiltrosDashboard
from dashboard_service import build_where, opcoes_filtro
```

Depois, após `_classificar`, adicionar:

```python
def _itens_produto(db: Session, where: str, params: dict) -> list[dict]:
    rows = db.execute(text(f"""
        SELECT pit.produto_codigo                  AS codigo,
               MAX(pit.produto_descricao)          AS nome,
               COALESCE(SUM(pit.total_liquido), 0) AS receita,
               COALESCE(SUM(pit.quantidade), 0)    AS quantidade
        FROM pedido_mobile_item pit
        JOIN pedido_mobile_pedido ped ON ped.pedido_numero = pit.pedido_numero
        WHERE {where} AND pit.produto_codigo IS NOT NULL
        GROUP BY pit.produto_codigo
    """), params).fetchall()
    return [{
        "codigo": r.codigo,
        "nome": r.nome or r.codigo or "—",
        "receita": float(r.receita or 0),
        "quantidade": float(r.quantidade or 0),
    } for r in rows]


def curva_abc(db: Session, f: FiltrosDashboard, *, dimensao: str,
              criterio: str, cortes: tuple[int, int]) -> dict:
    where, params = build_where(f)
    if dimensao == "produto":
        itens = _itens_produto(db, where, params)
    else:
        itens = _itens_representada(db, where, params)
    saida, resumo = _classificar(itens, criterio, cortes)
    return {"itens": saida, "resumo": resumo}
```

> `_itens_representada` ainda não existe — será criada na Task 4. Como `dimensao="produto"`
> não passa por esse ramo, os testes desta task passam mesmo assim.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest tests/test_analise_service.py -k curva_abc_produto -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/analise_service.py app/tests/test_analise_service.py
git commit -m "feat: curva ABC de produtos (agrega item por codigo)"
```

---

## Task 4: `_itens_representada` + `curva_abc` para representadas

Receita no nível do pedido (consistente com o cockpit); quantidade no nível do item;
mescladas por representada.

**Files:**
- Modify: `app/analise_service.py`
- Test: `app/tests/test_analise_service.py`

- [ ] **Step 1: Write the failing test**

Adicionar a `app/tests/test_analise_service.py`:

```python
def test_curva_abc_representada_receita_pedido_quantidade_item(db):
    _seed_itens(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    curva = svc.curva_abc(db, f, dimensao="representada", criterio="receita", cortes=(50, 30))
    por_nome = {i["nome"]: i for i in curva["itens"]}
    # Alpha = pedido 1 (total_liquido 100); Beta = pedido 2 (60).
    assert por_nome["Alpha"]["receita"] == 100.0
    assert por_nome["Beta"]["receita"] == 60.0
    # Quantidade vem dos itens: Alpha = 2 + 5 = 7; Beta = 3.
    assert por_nome["Alpha"]["quantidade"] == 7.0
    assert por_nome["Beta"]["quantidade"] == 3.0
    assert curva["itens"][0]["nome"] == "Alpha"  # maior receita primeiro


def test_curva_abc_representada_sem_dados(db):
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    curva = svc.curva_abc(db, f, dimensao="representada", criterio="quantidade", cortes=(50, 30))
    assert curva["itens"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest tests/test_analise_service.py -k representada -v`
Expected: FAIL — `NameError: name '_itens_representada' is not defined`

- [ ] **Step 3: Write minimal implementation**

Adicionar a `app/analise_service.py` (antes de `curva_abc`, junto de `_itens_produto`):

```python
def _itens_representada(db: Session, where: str, params: dict) -> list[dict]:
    # Receita no nível do pedido (igual ao cockpit).
    receitas = db.execute(text(f"""
        SELECT COALESCE(NULLIF(TRIM(representada), ''), '—') AS nome,
               COALESCE(SUM(total_liquido), 0)              AS receita
        FROM pedido_mobile_pedido ped
        WHERE {where}
        GROUP BY COALESCE(NULLIF(TRIM(representada), ''), '—')
    """), params).fetchall()
    # Quantidade no nível do item.
    quantidades = db.execute(text(f"""
        SELECT COALESCE(NULLIF(TRIM(ped.representada), ''), '—') AS nome,
               COALESCE(SUM(pit.quantidade), 0)                 AS quantidade
        FROM pedido_mobile_item pit
        JOIN pedido_mobile_pedido ped ON ped.pedido_numero = pit.pedido_numero
        WHERE {where}
        GROUP BY COALESCE(NULLIF(TRIM(ped.representada), ''), '—')
    """), params).fetchall()
    mapa_qtd = {r.nome: float(r.quantidade or 0) for r in quantidades}
    return [{
        "codigo": None,
        "nome": r.nome,
        "receita": float(r.receita or 0),
        "quantidade": mapa_qtd.get(r.nome, 0.0),
    } for r in receitas]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest tests/test_analise_service.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add app/analise_service.py app/tests/test_analise_service.py
git commit -m "feat: curva ABC de representadas (receita pedido + qtd item)"
```

---

## Task 5: `montar_analise` — agregador

**Files:**
- Modify: `app/analise_service.py`
- Test: `app/tests/test_analise_service.py`

- [ ] **Step 1: Write the failing test**

Adicionar a `app/tests/test_analise_service.py`:

```python
def test_montar_analise_inclui_todas_as_chaves(db):
    _seed_itens(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    dados = svc.montar_analise(db, f, criterio="receita", cortes_str="50-30-20")
    for chave in ("filtros", "opcoes", "criterio", "cortes", "produtos", "representadas"):
        assert chave in dados
    assert dados["criterio"] == "receita"
    assert dados["cortes"] == "50-30-20"
    assert "itens" in dados["produtos"] and "resumo" in dados["produtos"]
    assert "itens" in dados["representadas"] and "resumo" in dados["representadas"]


def test_montar_analise_normaliza_entradas_invalidas(db):
    _seed_itens(db)
    f = FiltrosDashboard.from_query({"inicio": "2026-06-01", "fim": "2026-06-30"}, hoje=date(2026, 6, 8))
    dados = svc.montar_analise(db, f, criterio="xpto", cortes_str="zzz")
    assert dados["criterio"] == "receita"
    assert dados["cortes"] == "50-30-20"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest tests/test_analise_service.py -k montar_analise -v`
Expected: FAIL — `AttributeError: module 'analise_service' has no attribute 'montar_analise'`

- [ ] **Step 3: Write minimal implementation**

Adicionar ao final de `app/analise_service.py`:

```python
def montar_analise(db: Session, f: FiltrosDashboard, *, criterio: str, cortes_str: str) -> dict:
    """Agrega os dados das duas curvas ABC. Normaliza critério e cortes."""
    criterio = parse_criterio(criterio)
    cortes_str = cortes_canonico(cortes_str)
    cortes = parse_cortes(cortes_str)
    return {
        "filtros": f,
        "opcoes": opcoes_filtro(db),
        "criterio": criterio,
        "cortes": cortes_str,
        "produtos": curva_abc(db, f, dimensao="produto", criterio=criterio, cortes=cortes),
        "representadas": curva_abc(db, f, dimensao="representada", criterio=criterio, cortes=cortes),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest tests/test_analise_service.py -v`
Expected: PASS (todos)

- [ ] **Step 5: Commit**

```bash
git add app/analise_service.py app/tests/test_analise_service.py
git commit -m "feat: montar_analise agrega as duas curvas ABC"
```

---

## Task 6: Rota `/dashboard/analise` + cache dedicado

**Files:**
- Modify: `app/routers/dashboard.py`
- Test: `app/tests/test_dashboard_route.py`

- [ ] **Step 1: Write the failing test**

Adicionar ao final de `app/tests/test_dashboard_route.py`:

```python
def test_cache_analise_isola_por_criterio_e_cortes(monkeypatch):
    rota._cache_analise.clear()
    chamadas = []

    def fake_montar(db, f, *, criterio, cortes_str):
        chamadas.append((criterio, cortes_str))
        return {"marcador": criterio}

    monkeypatch.setattr(rota.svc_analise, "montar_analise", fake_montar)

    f = FiltrosDashboard.from_query({}, hoje=date(2026, 6, 8))
    rota._dados_analise_cacheados(None, f, criterio="receita", cortes_str="50-30-20")
    rota._dados_analise_cacheados(None, f, criterio="receita", cortes_str="50-30-20")  # reusa cache
    rota._dados_analise_cacheados(None, f, criterio="quantidade", cortes_str="50-30-20")
    rota._dados_analise_cacheados(None, f, criterio="receita", cortes_str="70-20-10")

    assert chamadas == [
        ("receita", "50-30-20"),
        ("quantidade", "50-30-20"),
        ("receita", "70-20-10"),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && python -m pytest tests/test_dashboard_route.py -k analise -v`
Expected: FAIL — `AttributeError: module 'routers.dashboard' has no attribute 'svc_analise'`

- [ ] **Step 3: Write minimal implementation**

Em `app/routers/dashboard.py`, adicionar o import junto dos demais (após `import dashboard_service as svc`):

```python
import analise_service as svc_analise
```

Adicionar o cache dedicado logo após a definição de `_cache` (linha ~19):

```python
_cache_analise: dict = {}  # chave -> (ts, dados)


def _dados_analise_cacheados(db: Session, f: FiltrosDashboard, *, criterio: str, cortes_str: str) -> dict:
    chave = "|".join([f.chave_cache(), criterio, cortes_str])
    agora = time.monotonic()
    item = _cache_analise.get(chave)
    if item and (agora - item[0]) < _CACHE_TTL_SEGUNDOS:
        return item[1]
    dados = svc_analise.montar_analise(db, f, criterio=criterio, cortes_str=cortes_str)
    _cache_analise[chave] = (agora, dados)
    return dados
```

Adicionar a rota ao final do arquivo:

```python
@router.get("/dashboard/analise", response_class=HTMLResponse)
def dashboard_analise(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    hoje = datetime.now(BRT).date()
    q = dict(request.query_params)
    f = FiltrosDashboard.from_query(q, hoje=hoje)
    criterio = svc_analise.parse_criterio(q.get("criterio"))
    cortes_str = svc_analise.cortes_canonico(q.get("cortes"))
    dados = _dados_analise_cacheados(db, f, criterio=criterio, cortes_str=cortes_str)

    template = "partials/analise_paineis.html" if request.headers.get("HX-Request") else "analise.html"
    return templates.TemplateResponse(template, {
        "request": request,
        "user": current_user,
        "dados": dados,
    })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && python -m pytest tests/test_dashboard_route.py -v`
Expected: PASS (ambos os testes do arquivo)

- [ ] **Step 5: Commit**

```bash
git add app/routers/dashboard.py app/tests/test_dashboard_route.py
git commit -m "feat: rota /dashboard/analise com cache por recorte"
```

---

## Task 7: Parametrizar a barra de filtros compartilhada

A barra deve continuar idêntica para o cockpit (defaults) e ganhar os seletores de
critério/cortes só na análise (`mostrar_abc`).

**Files:**
- Modify: `app/templates/partials/dashboard_filtros.html`

- [ ] **Step 1: Editar o `<form>` para usar `acao`/`alvo`**

Substituir as duas primeiras linhas do arquivo:

```html
<form id="filtros-dashboard"
      hx-get="/dashboard" hx-target="#paineis" hx-swap="outerHTML"
```

por:

```html
<form id="filtros-dashboard"
      hx-get="{{ acao|default('/dashboard') }}" hx-target="{{ alvo|default('#paineis') }}" hx-swap="outerHTML"
```

- [ ] **Step 2: Adicionar o bloco dos seletores ABC**

Imediatamente **antes** da linha de fechamento `</form>` (última linha), inserir:

```html
  {% if mostrar_abc %}
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase tracking-wider">Classificar por</label>
    <select name="criterio" class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5] focus:outline-none focus:border-orange-500">
      <option value="receita" {% if dados.criterio == 'receita' %}selected{% endif %}>Receita</option>
      <option value="quantidade" {% if dados.criterio == 'quantidade' %}selected{% endif %}>Quantidade</option>
    </select>
  </div>
  <div>
    <label class="block text-[10px] font-semibold text-[#666] mb-1 uppercase tracking-wider">Cortes ABC</label>
    <select name="cortes" class="rounded-lg bg-[#1a1a1a] border border-[#333] px-2.5 py-1.5 text-sm text-[#e5e5e5] focus:outline-none focus:border-orange-500">
      {% for val in ['50-30-20', '70-20-10', '80-15-5'] %}
      <option value="{{ val }}" {% if dados.cortes == val %}selected{% endif %}>{{ val.replace('-', '/') }}</option>
      {% endfor %}
    </select>
  </div>
  {% endif %}
```

- [ ] **Step 3: Verificar que o cockpit não quebrou**

Run: `cd app && python -m pytest tests/ -v`
Expected: PASS (suite inteira — os testes de rota/serviço do cockpit continuam verdes)

- [ ] **Step 4: Commit**

```bash
git add app/templates/partials/dashboard_filtros.html
git commit -m "refactor: barra de filtros parametrizada (acao/alvo/mostrar_abc)"
```

---

## Task 8: Parcial `analise_paineis.html` (abas + resumo + Pareto + tabela)

**Files:**
- Create: `app/templates/partials/analise_paineis.html`

- [ ] **Step 1: Criar o parcial completo**

Criar `app/templates/partials/analise_paineis.html`:

```html
<div id="paineis" class="space-y-5">
  {% set criterio_label = 'Receita' if dados.criterio == 'receita' else 'Quantidade' %}

  <!-- Abas -->
  <div class="flex gap-1 border-b border-[#2e2e2e]">
    <button type="button" data-aba-btn="produtos"
            class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-[#888] hover:text-white">
      Produtos
    </button>
    <button type="button" data-aba-btn="representadas"
            class="px-4 py-2 text-sm font-medium border-b-2 border-transparent text-[#888] hover:text-white">
      Representadas
    </button>
  </div>

  {% set abas = [('produtos', 'Produto', dados.produtos), ('representadas', 'Representada', dados.representadas)] %}
  {% for chave, rotulo, curva in abas %}
  <div data-aba-painel="{{ chave }}" class="space-y-4 {% if not loop.first %}hidden{% endif %}">

    <!-- Resumo por classe -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {% set cores = {'A': 'text-green-400', 'B': 'text-orange-400', 'C': 'text-[#888]'} %}
      {% for classe in ['A', 'B', 'C'] %}
      {% set r = curva.resumo[classe] %}
      <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-4">
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold {{ cores[classe] }}">Classe {{ classe }}</span>
          <span class="text-xs text-[#666]">{{ r.itens }} itens</span>
        </div>
        <div class="text-xl font-bold {{ cores[classe] }} mt-2">{{ r.pct }}%</div>
        <div class="text-[11px] text-[#888] mt-1">do total de {{ criterio_label|lower }}</div>
        <div class="text-[11px] text-[#666] mt-2">
          R$ {{ "{:,.0f}".format(r.receita).replace(",", ".") }} · {{ "{:,.0f}".format(r.quantidade).replace(",", ".") }} un
        </div>
      </div>
      {% endfor %}
    </div>

    <!-- Pareto -->
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e]">
      <div class="text-sm font-semibold text-white px-5 py-3 border-b border-[#2e2e2e]">
        Curva ABC — {{ criterio_label }} por {{ rotulo|lower }}
      </div>
      <div class="p-4 h-80"><canvas id="chart_{{ chave }}"></canvas></div>
    </div>

    <!-- Tabela com chips de classe -->
    <div class="bg-[#171717] rounded-xl border border-[#2e2e2e]">
      <div class="px-5 py-3 border-b border-[#2e2e2e] flex items-center gap-2 flex-wrap">
        <span class="text-sm font-semibold text-white mr-2">Detalhamento</span>
        {% for chip in ['A', 'B', 'C', 'todas'] %}
        <button type="button" data-chip="{{ chip }}"
                class="text-xs px-2.5 py-1 rounded-full border border-[#333] text-[#888] hover:text-white">
          {{ 'Todas' if chip == 'todas' else 'Classe ' ~ chip }}
        </button>
        {% endfor %}
      </div>
      <div class="overflow-x-auto max-h-[28rem] overflow-y-auto">
        <table class="w-full text-sm">
          <thead class="bg-[#111] sticky top-0"><tr>
            <th class="px-4 py-2 text-left  text-[10px] text-[#666] uppercase tracking-wide">#</th>
            <th class="px-4 py-2 text-left  text-[10px] text-[#666] uppercase tracking-wide">{{ rotulo }}</th>
            <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase tracking-wide">Receita</th>
            <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase tracking-wide">Qtd</th>
            <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase tracking-wide">% {{ criterio_label|lower }}</th>
            <th class="px-4 py-2 text-right text-[10px] text-[#666] uppercase tracking-wide">% acum.</th>
            <th class="px-4 py-2 text-center text-[10px] text-[#666] uppercase tracking-wide">Classe</th>
          </tr></thead>
          <tbody class="divide-y divide-[#222]">
            {% set badge = {'A': 'bg-green-500/12 text-green-400', 'B': 'bg-orange-500/12 text-orange-400', 'C': 'bg-[#333]/40 text-[#999]'} %}
            {% for i in curva.itens %}
            <tr data-classe="{{ i.classe }}" class="hover:bg-[#1a1a1a]">
              <td class="px-4 py-2 text-[#666]">{{ loop.index }}</td>
              <td class="px-4 py-2 text-[#ccc]">{{ i.nome }}</td>
              <td class="px-4 py-2 text-right text-[#ccc] whitespace-nowrap">R$ {{ "{:,.0f}".format(i.receita).replace(",", ".") }}</td>
              <td class="px-4 py-2 text-right text-[#ccc]">{{ "{:,.0f}".format(i.quantidade).replace(",", ".") }}</td>
              <td class="px-4 py-2 text-right text-[#888]">{{ i.pct }}%</td>
              <td class="px-4 py-2 text-right text-[#888]">{{ i.pct_acumulado }}%</td>
              <td class="px-4 py-2 text-center">
                <span class="inline-block text-[10px] px-2 py-0.5 rounded-full {{ badge[i.classe] }}">{{ i.classe }}</span>
              </td>
            </tr>
            {% else %}
            <tr><td colspan="7" class="px-4 py-6 text-center text-[#555] text-xs">Sem dados neste recorte.</td></tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </div>
  {% endfor %}

  <script>
    (function () {
      const CRITERIO = {{ dados.criterio | tojson }};
      const PANELS = {
        produtos: {{ dados.produtos.itens | tojson }},
        representadas: {{ dados.representadas.itens | tojson }},
      };

      function corClasse(c) {
        if (c === 'A') return 'rgba(34,197,94,0.7)';
        if (c === 'B') return 'rgba(249,115,22,0.7)';
        return 'rgba(120,120,120,0.55)';
      }

      function montarGrafico(aba) {
        const itens = PANELS[aba] || [];
        const el = document.getElementById('chart_' + aba);
        if (!el || !window.Chart) return;
        if (el._chart) el._chart.destroy();
        Chart.defaults.color = '#888';
        Chart.defaults.borderColor = '#2e2e2e';
        const valores = itens.map(i => CRITERIO === 'receita' ? i.receita : i.quantidade);
        el._chart = new Chart(el, {
          data: {
            labels: itens.map(i => i.nome),
            datasets: [
              { type: 'bar', label: CRITERIO === 'receita' ? 'Receita' : 'Quantidade', yAxisID: 'y',
                data: valores, backgroundColor: itens.map(i => corClasse(i.classe)), borderRadius: 3 },
              { type: 'line', label: '% acumulado', yAxisID: 'y2',
                data: itens.map(i => i.pct_acumulado), borderColor: '#60a5fa',
                backgroundColor: 'transparent', pointRadius: 0, tension: 0.2 },
            ],
          },
          options: {
            maintainAspectRatio: false,
            scales: {
              y:  { position: 'left' },
              y2: { position: 'right', min: 0, max: 100, grid: { drawOnChartArea: false },
                    ticks: { callback: v => v + '%' } },
              x:  { ticks: { display: false } },
            },
            plugins: { legend: { display: true } },
          },
        });
      }

      const criados = {};
      function ativarAba(aba) {
        document.querySelectorAll('[data-aba-painel]').forEach(p => {
          p.classList.toggle('hidden', p.dataset.abaPainel !== aba);
        });
        document.querySelectorAll('[data-aba-btn]').forEach(b => {
          const ativo = b.dataset.abaBtn === aba;
          b.classList.toggle('text-orange-500', ativo);
          b.classList.toggle('border-orange-500', ativo);
          b.classList.toggle('text-white', false);
          b.classList.toggle('text-[#888]', !ativo);
          b.classList.toggle('border-transparent', !ativo);
        });
        if (!criados[aba]) { montarGrafico(aba); criados[aba] = true; }
      }

      function filtrarClasse(painel, classe, chipAtivo) {
        painel.querySelectorAll('[data-chip]').forEach(c => {
          const ativo = c === chipAtivo;
          c.classList.toggle('bg-orange-500/20', ativo);
          c.classList.toggle('text-orange-400', ativo);
          c.classList.toggle('border-orange-500/40', ativo);
        });
        painel.querySelectorAll('tr[data-classe]').forEach(tr => {
          tr.classList.toggle('hidden', classe !== 'todas' && tr.dataset.classe !== classe);
        });
      }

      document.querySelectorAll('[data-aba-btn]').forEach(b => {
        b.addEventListener('click', () => ativarAba(b.dataset.abaBtn));
      });
      document.querySelectorAll('[data-chip]').forEach(chip => {
        chip.addEventListener('click', () => {
          filtrarClasse(chip.closest('[data-aba-painel]'), chip.dataset.chip, chip);
        });
      });

      // Estado inicial: aba Produtos + filtro na classe A em cada painel.
      ativarAba('produtos');
      document.querySelectorAll('[data-aba-painel]').forEach(p => {
        const chipA = p.querySelector('[data-chip="A"]');
        if (chipA) filtrarClasse(p, 'A', chipA);
      });
    })();
  </script>
</div>
```

- [ ] **Step 2: Verificação (parcial não tem teste unitário próprio — validação na Task 11)**

Sem comando aqui; a renderização será validada no smoke da Task 11.

- [ ] **Step 3: Commit**

```bash
git add app/templates/partials/analise_paineis.html
git commit -m "feat: parcial de paineis da analise (abas, Pareto, tabela)"
```

---

## Task 9: Página `analise.html`

**Files:**
- Create: `app/templates/analise.html`

- [ ] **Step 1: Criar a página**

Criar `app/templates/analise.html` (espelha `dashboard.html`, mas define `acao`/`alvo`/`mostrar_abc`
antes do include — no Jinja2 o `{% include %}` herda o contexto do bloco, então as variáveis
definidas com `{% set %}` chegam ao parcial de filtros):

```html
{% extends "base.html" %}

{% block head_extra %}
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
{% endblock %}

{% block title %}Análise de Vendas{% endblock %}

{% block content %}
{% set acao = "/dashboard/analise" %}
{% set alvo = "#paineis" %}
{% set mostrar_abc = True %}
{% include "partials/dashboard_filtros.html" %}
<div class="p-5">
  {% include "partials/analise_paineis.html" %}
</div>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/analise.html
git commit -m "feat: pagina analise.html com Chart.js e filtros ABC"
```

---

## Task 10: Hub de Dashboards — card "Disponível"

**Files:**
- Modify: `app/templates/dashboards.html`

- [ ] **Step 1: Trocar o card "Em breve" por link ativo**

Substituir o bloco do card de Análise de Vendas (a `<div>` com `opacity-60 cursor-not-allowed`):

```html
    <div class="bg-[#171717] border border-[#2e2e2e] rounded-xl p-5 opacity-60 cursor-not-allowed">
      <div class="text-2xl">📈</div>
      <div class="text-white font-semibold mt-2">Análise de Vendas</div>
      <div class="text-[#888] text-xs mt-1 leading-relaxed">Curva ABC de produtos, representadas, mix e sazonalidade.</div>
      <span class="inline-block mt-3 text-[9px] px-2 py-0.5 rounded-full bg-yellow-500/10 text-yellow-400">Em breve</span>
    </div>
```

por:

```html
    <a href="/dashboard/analise" class="bg-[#171717] border border-[#2e2e2e] rounded-xl p-5 hover:border-orange-500 hover:-translate-y-0.5 transition-all group">
      <div class="text-2xl">📈</div>
      <div class="text-white font-semibold mt-2 group-hover:text-orange-500">Análise de Vendas</div>
      <div class="text-[#888] text-xs mt-1 leading-relaxed">Curva ABC de produtos e representadas, por receita ou quantidade.</div>
      <span class="inline-block mt-3 text-[9px] px-2 py-0.5 rounded-full bg-green-500/12 text-green-400">Disponível</span>
    </a>
```

- [ ] **Step 2: Commit**

```bash
git add app/templates/dashboards.html
git commit -m "feat: card Analise de Vendas como Disponivel no hub"
```

---

## Task 11: Suite completa + smoke manual

**Files:** nenhum (verificação).

- [ ] **Step 1: Rodar a suite inteira**

Run: `cd app && python -m pytest tests/ -v`
Expected: PASS — todos os testes (suite anterior + novos do `test_analise_service.py` e o de cache da análise).

- [ ] **Step 2: Subir a aplicação**

Run: `docker compose up -d`
Expected: containers `web` e `db` saudáveis (checar `docker compose ps`).

- [ ] **Step 3: Smoke manual no navegador**

1. Login em `http://localhost:8000` (admin@sbr.local / senha local).
2. Menu lateral → **Dashboards** → card **Análise de Vendas** agora *Disponível* → abrir.
3. Conferir:
   - Abas **Produtos** / **Representadas** alternam e cada uma desenha o gráfico de Pareto (barras coloridas por classe + linha de % acumulado).
   - Cards-resumo A/B/C mostram % do critério, receita e quantidade.
   - Tabela inicia filtrada na **classe A**; chips A/B/C/Todas filtram as linhas.
   - Trocar **Classificar por** (Receita ↔ Quantidade) e **Cortes ABC** refaz a tela via HTMX e atualiza a URL.
   - Trocar **período/vendedor/representada/situação** também refaz e mantém o estado na URL.
4. Recarregar a página com filtros na URL (ex.: `?criterio=quantidade&cortes=70-20-10`) → estado preservado.

- [ ] **Step 4: Atualizar o estado do projeto**

Editar `docs/CLAUDE.md` (seção "Estado Atual"): registrar que o dashboard de Análise de Vendas
(Fase 2 / B — curvas ABC de produtos e representadas) está concluído, e que a próxima frente é a
Fase 3 (Realizado vs. meta) — conforme `memory/project_cockpit_comercial.md`.

- [ ] **Step 5: Commit final**

```bash
git add docs/CLAUDE.md
git commit -m "docs: registra conclusao do dashboard de Analise de Vendas (ABC)"
git push origin main
```

> Os commits anteriores (Tasks 1–10) podem ser enviados em lote aqui com `git push origin main`
> caso ainda não tenham sido empurrados.

---

## Notas de verificação / armadilhas

- **Canvas oculto no Chart.js:** o gráfico da aba não-ativa só é criado quando a aba é exibida
  pela primeira vez (`criados[aba]`). Isso evita o bug de canvas com altura 0 ao renderizar escondido.
- **Re-execução de script em swap HTMX:** o `<script>` do parcial roda a cada swap (HTMX executa
  scripts inline do conteúdo trocado). A IIFE re-vincula handlers e recria os charts — sem vazamento
  porque `el._chart.destroy()` é chamado antes de recriar.
- **Consistência de receita:** a receita de representada vem do nível do pedido (igual ao cockpit);
  não somar itens para receita, senão diverge por causa dos descontos de pedido.
- **Cache:** a chave inclui `criterio` e `cortes_str`; recortes diferentes não se misturam (Task 6).
- **Cockpit intacto:** `dashboard_filtros.html` usa defaults (`/dashboard`, `#paineis`, `mostrar_abc`
  ausente), então a tela do cockpit não muda (garantido pela suite na Task 7).
```
