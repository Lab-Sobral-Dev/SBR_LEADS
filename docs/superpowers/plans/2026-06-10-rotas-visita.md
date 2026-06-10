# Rotas de Visita — Plano de Implementação

> **Para workers agênticos:** SUB-SKILL OBRIGATÓRIA: use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para implementar este plano tarefa a tarefa. Os passos usam checkbox (`- [ ]`) para acompanhamento.

**Goal:** Adicionar a feature "Rotas de Visita" ao SBR Leads — o gestor monta, ordena (vizinho mais próximo) e salva rotas nomeadas de clientes + prospectos por vendedor, com handoff pro Google Maps.

**Arquitetura:** Um novo módulo `app/rotas_service.py` concentra funções puras testáveis (haversine, ordenação NN, montagem de URLs do Maps) + helpers de banco (candidatos, clientes em risco, CRUD das rotas). Um novo router `app/routers/rotas.py` expõe as telas e endpoints, reusando `require_login`, `get_db`, `dashboard_service.opcoes_filtro` e o segmento fixo `farmacia` de `service.py`. Frontend em Jinja2 + HTMX + Leaflet + SortableJS, com geocodificação client-side reusando o mesmo cache `localStorage` do Mapa.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy Core (`text()`), PostgreSQL, Jinja2, HTMX, Leaflet, SortableJS, pytest.

**Spec:** `docs/superpowers/specs/2026-06-10-rotas-visita-design.md`

---

## Estrutura de arquivos

| Arquivo | Responsabilidade | Ação |
|---------|------------------|------|
| `app/rotas_service.py` | Funções puras (NN, haversine, URLs Maps) + helpers DB (candidatos, risco, CRUD) | Criar |
| `app/routers/rotas.py` | Endpoints das telas e ações de rota | Criar |
| `app/schemas.py` | Modelos Pydantic dos payloads JSON (ParadaIn, OrdenarRequest, SalvarRotaRequest) | Modificar |
| `app/main.py` | Bootstrap das tabelas `rota`/`rota_parada` + registrar router | Modificar |
| `app/tests/conftest.py` | DDL de teste das tabelas novas + `estabelecimento`/`empresa`/`municipio` mínimas | Modificar |
| `app/tests/test_rotas_service.py` | Testes do `rotas_service` (puras + DB + CRUD) | Criar |
| `app/templates/rotas.html` | Tela "Minhas rotas" (lista) | Criar |
| `app/templates/rota_montar.html` | Tela de montagem (3 colunas) | Criar |
| `app/templates/partials/rota_candidatos.html` | Lista de candidatos (HTMX) | Criar |
| `app/templates/partials/sidebar.html` | Item "Rotas" no menu | Modificar |

**Convenção de comandos:** os testes rodam de dentro de `app/` (onde está `pytest.ini` com `testpaths = tests`). Todos os `pytest …` abaixo assumem o diretório de trabalho `C:\Users\dbarbosa\Documents\PROJETOS\SBR_LEEDS\app`.

---

## Task 1: Tabelas `rota` / `rota_parada` + DDL de teste

**Files:**
- Modify: `app/main.py` (função `_bootstrap_usuarios`, antes do `conn.commit()` da linha ~119)
- Modify: `app/tests/conftest.py` (constante `DDL`, linha ~18-61)

- [ ] **Step 1: Adicionar o bootstrap das tabelas em `app/main.py`**

Dentro de `_bootstrap_usuarios`, logo após o bloco `CREATE INDEX … idx_pm_item_pedido` (linha ~118) e ANTES de `conn.commit()`, inserir:

```python
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rota (
                id             SERIAL PRIMARY KEY,
                nome           TEXT NOT NULL,
                vendedor       TEXT NOT NULL,
                municipio      TEXT NOT NULL,
                uf             TEXT NOT NULL,
                criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS rota_parada (
                id          SERIAL PRIMARY KEY,
                rota_id     INTEGER NOT NULL REFERENCES rota(id) ON DELETE CASCADE,
                ordem       INTEGER NOT NULL,
                documento   TEXT NOT NULL,
                nome_cache  TEXT NOT NULL,
                eh_cliente  BOOLEAN NOT NULL DEFAULT FALSE,
                cep_cache   TEXT,
                lat_cache   DOUBLE PRECISION,
                lng_cache   DOUBLE PRECISION
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_rota_parada_rota ON rota_parada(rota_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_rota_vendedor ON rota(vendedor)
        """))
```

- [ ] **Step 2: Adicionar DDL de teste em `app/tests/conftest.py`**

Acrescentar ao FINAL da string `DDL` (antes das `"""` de fechamento, depois do bloco `pedido_mobile_item`) o DDL das tabelas novas E das tabelas de leads mínimas que a query de candidatos usa:

```sql
CREATE TABLE IF NOT EXISTS rota (
    id             SERIAL PRIMARY KEY,
    nome           TEXT NOT NULL,
    vendedor       TEXT NOT NULL,
    municipio      TEXT NOT NULL,
    uf             TEXT NOT NULL,
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS rota_parada (
    id          SERIAL PRIMARY KEY,
    rota_id     INTEGER NOT NULL REFERENCES rota(id) ON DELETE CASCADE,
    ordem       INTEGER NOT NULL,
    documento   TEXT NOT NULL,
    nome_cache  TEXT NOT NULL,
    eh_cliente  BOOLEAN NOT NULL DEFAULT FALSE,
    cep_cache   TEXT,
    lat_cache   DOUBLE PRECISION,
    lng_cache   DOUBLE PRECISION
);
CREATE TABLE IF NOT EXISTS empresa (
    cnpj_basico   VARCHAR(8) PRIMARY KEY,
    razao_social  VARCHAR(200),
    porte         VARCHAR(2),
    capital_social NUMERIC
);
CREATE TABLE IF NOT EXISTS municipio (
    codigo    VARCHAR(7) PRIMARY KEY,
    descricao VARCHAR(120)
);
CREATE TABLE IF NOT EXISTS estabelecimento (
    cnpj_basico            VARCHAR(8),
    cnpj_ordem             VARCHAR(4),
    cnpj_dv                VARCHAR(2),
    nome_fantasia          VARCHAR(200),
    cnae_fiscal_principal  VARCHAR(7),
    situacao_cadastral     VARCHAR(2),
    cep                    VARCHAR(8),
    tipo_logradouro        VARCHAR(40),
    logradouro             VARCHAR(200),
    numero                 VARCHAR(20),
    bairro                 VARCHAR(100),
    municipio              VARCHAR(7),
    uf                     VARCHAR(2)
);
```

> Nota: o DDL de teste replica apenas as colunas usadas por `rotas_service`. As tabelas reais (`estabelecimento`/`empresa`/`municipio`) vêm do ETL e têm muito mais colunas — aqui só precisamos do subconjunto consultado.

- [ ] **Step 3: Rodar a suíte existente para garantir que nada quebrou**

Run: `pytest -q`
Expected: PASS (todos os testes atuais continuam verdes; o banco de teste recria as tabelas via DDL sem erro).

- [ ] **Step 4: Commit**

```bash
git add app/main.py app/tests/conftest.py
git commit -m "feat: tabelas rota e rota_parada (bootstrap + DDL de teste)"
```

---

## Task 2: Funções puras — haversine, ordenação NN, URLs do Google Maps

**Files:**
- Create: `app/rotas_service.py`
- Create: `app/tests/test_rotas_service.py`

- [ ] **Step 1: Escrever os testes das funções puras**

Criar `app/tests/test_rotas_service.py`:

```python
import math

import rotas_service as svc


# ---- haversine ----

def test_haversine_zero_quando_mesmo_ponto():
    assert svc.haversine_km(-9.0, -45.0, -9.0, -45.0) == 0.0


def test_haversine_distancia_conhecida_aproximada():
    # ~111 km por grau de latitude no equador (tolerância ampla).
    d = svc.haversine_km(0.0, 0.0, 1.0, 0.0)
    assert 110 < d < 112


# ---- ordenação vizinho mais próximo ----

def _p(doc, lat, lng):
    return {"documento": doc, "lat": lat, "lng": lng}


def test_ordenar_comeca_na_partida():
    paradas = [_p("A", 0.0, 0.0), _p("B", 0.0, 5.0), _p("C", 0.0, 1.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=0)
    assert [p["documento"] for p in saida] == ["A", "C", "B"]


def test_ordenar_partida_no_meio():
    paradas = [_p("A", 0.0, 0.0), _p("B", 0.0, 5.0), _p("C", 0.0, 6.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=1)
    # Começa em B(5); mais próximo é C(6), depois A(0).
    assert [p["documento"] for p in saida] == ["B", "C", "A"]


def test_ordenar_paradas_sem_coords_vao_para_o_fim():
    paradas = [_p("A", 0.0, 0.0), {"documento": "X", "lat": None, "lng": None}, _p("B", 0.0, 1.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=0)
    assert [p["documento"] for p in saida] == ["A", "B", "X"]


def test_ordenar_listas_pequenas_nao_quebram():
    assert svc.ordenar_vizinho_mais_proximo([], partida_idx=0) == []
    um = [_p("A", 1.0, 1.0)]
    assert svc.ordenar_vizinho_mais_proximo(um, partida_idx=0) == um


def test_ordenar_partida_idx_invalido_usa_zero():
    paradas = [_p("A", 0.0, 0.0), _p("B", 0.0, 1.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=99)
    assert saida[0]["documento"] == "A"


# ---- URLs do Google Maps ----

def test_maps_um_trecho_ate_10_paradas():
    paradas = [_p(str(i), 0.0, float(i)) for i in range(3)]
    urls = svc.montar_urls_google_maps(paradas)
    assert len(urls) == 1
    assert urls[0].startswith("https://www.google.com/maps/dir/?api=1")
    assert "origin=0.0%2C0.0" in urls[0]
    assert "destination=0.0%2C2.0" in urls[0]
    assert "travelmode=driving" in urls[0]


def test_maps_quebra_em_trechos_com_fronteira_compartilhada():
    paradas = [_p(str(i), 0.0, float(i)) for i in range(14)]  # 14 paradas, max 10
    urls = svc.montar_urls_google_maps(paradas, max_por_trecho=10)
    assert len(urls) == 2
    # Trecho 1: paradas 0..9 (origin 0, destination 9).
    assert "origin=0.0%2C0.0" in urls[0]
    assert "destination=0.0%2C9.0" in urls[0]
    # Trecho 2 começa onde o 1 terminou: parada 9 (origin), 13 (destination).
    assert "origin=0.0%2C9.0" in urls[1]
    assert "destination=0.0%2C13.0" in urls[1]


def test_maps_ignora_paradas_sem_coords():
    paradas = [_p("A", 0.0, 0.0), {"documento": "X", "lat": None, "lng": None}, _p("B", 0.0, 1.0)]
    urls = svc.montar_urls_google_maps(paradas)
    assert len(urls) == 1
    assert "origin=0.0%2C0.0" in urls[0]
    assert "destination=0.0%2C1.0" in urls[0]


def test_maps_lista_vazia_ou_um_ponto():
    assert svc.montar_urls_google_maps([]) == []
    assert svc.montar_urls_google_maps([_p("A", 0.0, 0.0)]) == []
```

- [ ] **Step 2: Rodar os testes para vê-los falhar**

Run: `pytest tests/test_rotas_service.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'rotas_service'`.

- [ ] **Step 3: Criar `app/rotas_service.py` com as funções puras**

```python
"""Serviço das Rotas de Visita.

Funções puras (haversine, ordenação por vizinho mais próximo, URLs do Google
Maps) são testáveis sem banco. Os helpers de banco (candidatos, risco, CRUD)
ficam mais abaixo no arquivo.
"""

import math
from urllib.parse import urlencode

from sqlalchemy import text
from sqlalchemy.orm import Session

from dashboard_filters import FiltrosDashboard  # noqa: F401  (usado pelos helpers de DB)
from service import ATALHOS, SEGMENTO_FIXO

# CNAEs do segmento fixo (farmácia) — a base só contém esse segmento.
CNAES_SEGMENTO = next(a["cnaes"] for a in ATALHOS if a["segmento"] == SEGMENTO_FIXO)

_MAPS_BASE = "https://www.google.com/maps/dir/"
_MAX_POR_TRECHO_PADRAO = 10


# --------------------------------------------------------------------------- puras

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em km entre dois pontos (linha reta sobre a esfera)."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * r * math.asin(math.sqrt(a))


def _tem_coords(p: dict) -> bool:
    return p.get("lat") is not None and p.get("lng") is not None


def ordenar_vizinho_mais_proximo(paradas: list[dict], partida_idx: int = 0) -> list[dict]:
    """Reordena as paradas pelo vizinho mais próximo (haversine) a partir de
    `partida_idx`. Paradas sem lat/lng vão para o fim, na ordem original.
    Não muta a entrada."""
    com = [p for p in paradas if _tem_coords(p)]
    sem = [p for p in paradas if not _tem_coords(p)]
    if len(com) <= 1:
        return com + sem

    # Localiza a partida entre as que têm coords; se inválida, usa a primeira.
    partida = paradas[partida_idx] if 0 <= partida_idx < len(paradas) else None
    if partida is None or not _tem_coords(partida):
        atual = com[0]
    else:
        atual = partida

    restantes = [p for p in com if p is not atual]
    ordenado = [atual]
    while restantes:
        prox = min(restantes, key=lambda p: haversine_km(atual["lat"], atual["lng"], p["lat"], p["lng"]))
        ordenado.append(prox)
        restantes.remove(prox)
        atual = prox
    return ordenado + sem


def _url_trecho(pontos: list[dict]) -> str:
    origem = pontos[0]
    destino = pontos[-1]
    meio = pontos[1:-1]
    params = {
        "api": "1",
        "origin": f'{origem["lat"]},{origem["lng"]}',
        "destination": f'{destino["lat"]},{destino["lng"]}',
        "travelmode": "driving",
    }
    if meio:
        params["waypoints"] = "|".join(f'{p["lat"]},{p["lng"]}' for p in meio)
    return _MAPS_BASE + "?" + urlencode(params)


def montar_urls_google_maps(paradas: list[dict],
                            max_por_trecho: int = _MAX_POR_TRECHO_PADRAO) -> list[str]:
    """URLs de direções do Google Maps na ordem das paradas. Quebra em trechos
    de até `max_por_trecho` pontos; cada trecho começa na última parada do
    anterior (continuidade). Ignora paradas sem coords. Vazio se < 2 pontos."""
    com = [p for p in paradas if _tem_coords(p)]
    if len(com) < 2:
        return []
    urls = []
    passo = max(1, max_por_trecho - 1)  # sobreposição de 1 ponto entre trechos
    i = 0
    while i < len(com) - 1:
        trecho = com[i:i + max_por_trecho]
        urls.append(_url_trecho(trecho))
        i += passo
    return urls
```

- [ ] **Step 4: Rodar os testes para vê-los passar**

Run: `pytest tests/test_rotas_service.py -q`
Expected: PASS (todos os testes das funções puras verdes).

- [ ] **Step 5: Commit**

```bash
git add app/rotas_service.py app/tests/test_rotas_service.py
git commit -m "feat: funcoes puras de rota (haversine, NN, urls do maps)"
```

---

## Task 3: Helpers de banco — candidatos e clientes em risco

**Files:**
- Modify: `app/rotas_service.py`
- Modify: `app/tests/test_rotas_service.py`

- [ ] **Step 1: Escrever os testes dos helpers de banco**

Acrescentar ao final de `app/tests/test_rotas_service.py`:

```python
from datetime import date

from sqlalchemy import text


def _seed_estab(db, *, doc, cnpj=("11111111", "0001", "11"), cnae="4771701",
                municipio="2603900", uf="PE", cep="55000000", nome="Farmácia X"):
    db.execute(text("""
        INSERT INTO empresa (cnpj_basico, razao_social) VALUES (:b, :rs)
        ON CONFLICT DO NOTHING
    """), {"b": cnpj[0], "rs": nome})
    db.execute(text("""
        INSERT INTO municipio (codigo, descricao) VALUES (:c, 'Floriano')
        ON CONFLICT DO NOTHING
    """), {"c": municipio})
    db.execute(text("""
        INSERT INTO estabelecimento
            (cnpj_basico, cnpj_ordem, cnpj_dv, nome_fantasia, cnae_fiscal_principal,
             situacao_cadastral, cep, logradouro, numero, municipio, uf)
        VALUES (:b, :o, :d, :nf, :cnae, '02', :cep, 'Rua A', '10', :mun, :uf)
    """), {"b": cnpj[0], "o": cnpj[1], "d": cnpj[2], "nf": nome, "cnae": cnae,
           "cep": cep, "mun": municipio, "uf": uf})


def test_candidatos_traz_cliente_do_vendedor_e_prospecto(db):
    # Cliente do João (documento 1111111100011 = basico+ordem+dv).
    _seed_estab(db, doc="cli", cnpj=("11111111", "0001", "11"), nome="Cliente João")
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, vendedor, inativo)
        VALUES ('1111111100011', 'Joao', FALSE)
    """))
    # Prospecto (não-cliente) na mesma cidade.
    _seed_estab(db, doc="pro", cnpj=("22222222", "0001", "22"), nome="Prospecto")

    itens = svc.candidatos(db, vendedor="Joao", municipio_codigo="2603900", hoje=date(2026, 6, 10))
    por_doc = {i["documento"]: i for i in itens}
    assert por_doc["1111111100011"]["eh_cliente"] is True
    assert por_doc["2222222200022"]["eh_cliente"] is False
    assert por_doc["1111111100011"]["cep"] == "55000000"


def test_candidatos_nao_traz_cliente_de_outro_vendedor(db):
    _seed_estab(db, doc="cli", cnpj=("33333333", "0001", "33"), nome="Cliente Maria")
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, vendedor, inativo)
        VALUES ('3333333300033', 'Maria', FALSE)
    """))
    itens = svc.candidatos(db, vendedor="Joao", municipio_codigo="2603900", hoje=date(2026, 6, 10))
    # Cliente da Maria não aparece (nem como prospecto, pois é cliente).
    assert all(i["documento"] != "3333333300033" for i in itens)


def test_candidatos_marca_em_risco(db):
    _seed_estab(db, doc="cli", cnpj=("44444444", "0001", "44"), nome="Cliente Atrasado")
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, vendedor, inativo)
        VALUES ('4444444400044', 'Joao', FALSE)
    """))
    # Última compra há muito tempo -> em risco.
    db.execute(text("""
        INSERT INTO pedido_mobile_pedido (pedido_numero, cliente_documento, vendedor, emissao, total_liquido)
        VALUES (901, '4444444400044', 'Joao', '2026-01-01', 100)
    """))
    itens = svc.candidatos(db, vendedor="Joao", municipio_codigo="2603900", hoje=date(2026, 6, 10))
    por_doc = {i["documento"]: i for i in itens}
    assert por_doc["4444444400044"]["em_risco"] is True


def test_documentos_em_risco_respeita_limite_de_dias(db):
    db.execute(text("""
        INSERT INTO pedido_mobile_pedido (pedido_numero, cliente_documento, vendedor, emissao, total_liquido)
        VALUES
            (801, 'doc_antigo', 'Joao', '2026-01-01', 100),
            (802, 'doc_recente', 'Joao', '2026-06-09', 100)
    """))
    risco = svc.documentos_em_risco(db, vendedor="Joao", hoje=date(2026, 6, 10))
    assert "doc_antigo" in risco       # > 30 dias
    assert "doc_recente" not in risco  # < 30 dias
```

- [ ] **Step 2: Rodar os testes para vê-los falhar**

Run: `pytest tests/test_rotas_service.py -k "candidatos or risco" -q`
Expected: FAIL com `AttributeError: module 'rotas_service' has no attribute 'candidatos'`.

- [ ] **Step 3: Implementar os helpers em `app/rotas_service.py`**

Acrescentar ao final de `app/rotas_service.py`:

```python
# ----------------------------------------------------------------- helpers de DB

def documentos_em_risco(db: Session, *, vendedor: str, hoje, dias_min: int = 30) -> set[str]:
    """Conjunto de documentos (CNPJ) de clientes do vendedor cuja última compra
    foi há `dias_min` dias ou mais. Espelha a regra de risco do cockpit."""
    rows = db.execute(text("""
        SELECT ped.cliente_documento AS documento
        FROM pedido_mobile_pedido ped
        LEFT JOIN cliente_pedido_mobile pm ON pm.documento = ped.cliente_documento
        WHERE COALESCE(NULLIF(TRIM(ped.vendedor), ''), '') = :vendedor
          AND (pm.inativo = FALSE OR pm.inativo IS NULL)
        GROUP BY ped.cliente_documento
        HAVING (:hoje - MAX(ped.emissao)) >= :dias_min
    """), {"vendedor": vendedor, "hoje": hoje, "dias_min": dias_min}).scalars().all()
    return set(rows)


def candidatos(db: Session, *, vendedor: str, municipio_codigo: str, hoje) -> list[dict]:
    """Clientes do vendedor + prospectos (não-clientes) no município (segmento
    fixo farmácia, situação ativa). Marca `em_risco` reusando a regra do cockpit."""
    rows = db.execute(text("""
        SELECT
            e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv          AS documento,
            COALESCE(NULLIF(TRIM(e.nome_fantasia), ''),
                     emp.razao_social, '—')                     AS nome,
            e.cep, e.tipo_logradouro, e.logradouro, e.numero, e.bairro,
            m.descricao                                         AS municipio,
            e.uf,
            (pm.documento IS NOT NULL)                          AS eh_cliente,
            pm.vendedor                                         AS vendedor
        FROM estabelecimento e
        LEFT JOIN empresa    emp ON emp.cnpj_basico = e.cnpj_basico
        LEFT JOIN municipio  m   ON m.codigo        = e.municipio
        LEFT JOIN cliente_pedido_mobile pm
               ON pm.documento = e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv
              AND pm.inativo = FALSE
        WHERE e.municipio = :municipio
          AND e.cnae_fiscal_principal = ANY(:cnaes)
          AND e.situacao_cadastral = '02'
          AND (pm.vendedor = :vendedor OR pm.documento IS NULL)
        ORDER BY (pm.documento IS NOT NULL) DESC, nome ASC
    """), {"municipio": municipio_codigo, "cnaes": CNAES_SEGMENTO, "vendedor": vendedor}).fetchall()

    risco = documentos_em_risco(db, vendedor=vendedor, hoje=hoje)
    return [{
        "documento": r.documento,
        "nome": r.nome,
        "cep": r.cep,
        "tipo_logradouro": r.tipo_logradouro,
        "logradouro": r.logradouro,
        "numero": r.numero,
        "bairro": r.bairro,
        "municipio": r.municipio,
        "uf": r.uf,
        "eh_cliente": bool(r.eh_cliente),
        "vendedor": r.vendedor,
        "em_risco": r.documento in risco,
    } for r in rows]
```

- [ ] **Step 4: Rodar os testes para vê-los passar**

Run: `pytest tests/test_rotas_service.py -k "candidatos or risco" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/rotas_service.py app/tests/test_rotas_service.py
git commit -m "feat: helpers de candidatos e clientes em risco da rota"
```

---

## Task 4: CRUD das rotas no `rotas_service`

**Files:**
- Modify: `app/rotas_service.py`
- Modify: `app/tests/test_rotas_service.py`

- [ ] **Step 1: Escrever os testes do CRUD**

Acrescentar ao final de `app/tests/test_rotas_service.py`:

```python
def _paradas_exemplo():
    return [
        {"documento": "111", "nome": "A", "eh_cliente": True,  "cep": "55000000", "lat": -6.7, "lng": -43.0},
        {"documento": "222", "nome": "B", "eh_cliente": False, "cep": None,       "lat": None, "lng": None},
    ]


def test_criar_e_carregar_rota_preserva_ordem(db):
    rid = svc.criar_rota(db, nome="Segunda Centro", vendedor="Joao",
                         municipio="Floriano", uf="PI", paradas=_paradas_exemplo())
    assert isinstance(rid, int)
    rota = svc.carregar_rota(db, rid)
    assert rota["nome"] == "Segunda Centro"
    assert rota["vendedor"] == "Joao"
    assert [p["documento"] for p in rota["paradas"]] == ["111", "222"]
    assert rota["paradas"][0]["ordem"] == 1
    assert rota["paradas"][0]["lat"] == -6.7
    assert rota["paradas"][0]["eh_cliente"] is True
    assert rota["paradas"][1]["lat"] is None


def test_listar_rotas_traz_contagem_de_paradas(db):
    svc.criar_rota(db, nome="R1", vendedor="Joao", municipio="Floriano", uf="PI",
                   paradas=_paradas_exemplo())
    lista = svc.listar_rotas(db)
    assert len(lista) == 1
    assert lista[0]["nome"] == "R1"
    assert lista[0]["n_paradas"] == 2


def test_atualizar_rota_substitui_paradas(db):
    rid = svc.criar_rota(db, nome="R", vendedor="Joao", municipio="Floriano", uf="PI",
                         paradas=_paradas_exemplo())
    svc.atualizar_rota(db, rid, nome="R editada", paradas=[
        {"documento": "999", "nome": "Z", "eh_cliente": False, "cep": None, "lat": 1.0, "lng": 2.0},
    ])
    rota = svc.carregar_rota(db, rid)
    assert rota["nome"] == "R editada"
    assert [p["documento"] for p in rota["paradas"]] == ["999"]


def test_excluir_rota_remove_paradas_em_cascata(db):
    rid = svc.criar_rota(db, nome="R", vendedor="Joao", municipio="Floriano", uf="PI",
                         paradas=_paradas_exemplo())
    svc.excluir_rota(db, rid)
    assert svc.carregar_rota(db, rid) is None
    n = db.execute(text("SELECT COUNT(*) FROM rota_parada WHERE rota_id = :r"), {"r": rid}).scalar()
    assert n == 0


def test_carregar_rota_inexistente_retorna_none(db):
    assert svc.carregar_rota(db, 999999) is None
```

- [ ] **Step 2: Rodar os testes para vê-los falhar**

Run: `pytest tests/test_rotas_service.py -k "rota" -q`
Expected: FAIL com `AttributeError: module 'rotas_service' has no attribute 'criar_rota'`.

- [ ] **Step 3: Implementar o CRUD em `app/rotas_service.py`**

Acrescentar ao final de `app/rotas_service.py`:

```python
# ----------------------------------------------------------------------- CRUD

def _inserir_paradas(db: Session, rota_id: int, paradas: list[dict]) -> None:
    for ordem, p in enumerate(paradas, start=1):
        db.execute(text("""
            INSERT INTO rota_parada
                (rota_id, ordem, documento, nome_cache, eh_cliente, cep_cache, lat_cache, lng_cache)
            VALUES (:rid, :ordem, :doc, :nome, :cli, :cep, :lat, :lng)
        """), {
            "rid": rota_id, "ordem": ordem,
            "doc": p["documento"], "nome": p.get("nome") or "—",
            "cli": bool(p.get("eh_cliente")),
            "cep": p.get("cep"), "lat": p.get("lat"), "lng": p.get("lng"),
        })


def criar_rota(db: Session, *, nome: str, vendedor: str, municipio: str, uf: str,
               paradas: list[dict]) -> int:
    rid = db.execute(text("""
        INSERT INTO rota (nome, vendedor, municipio, uf)
        VALUES (:nome, :vend, :mun, :uf) RETURNING id
    """), {"nome": nome, "vend": vendedor, "mun": municipio, "uf": uf}).scalar()
    _inserir_paradas(db, rid, paradas)
    return rid


def atualizar_rota(db: Session, rota_id: int, *, nome: str, paradas: list[dict]) -> None:
    db.execute(text("""
        UPDATE rota SET nome = :nome, atualizado_em = NOW() WHERE id = :id
    """), {"nome": nome, "id": rota_id})
    db.execute(text("DELETE FROM rota_parada WHERE rota_id = :id"), {"id": rota_id})
    _inserir_paradas(db, rota_id, paradas)


def listar_rotas(db: Session) -> list[dict]:
    rows = db.execute(text("""
        SELECT r.id, r.nome, r.vendedor, r.municipio, r.uf, r.atualizado_em,
               COUNT(p.id) AS n_paradas
        FROM rota r
        LEFT JOIN rota_parada p ON p.rota_id = r.id
        GROUP BY r.id
        ORDER BY r.atualizado_em DESC
    """)).fetchall()
    return [{
        "id": r.id, "nome": r.nome, "vendedor": r.vendedor,
        "municipio": r.municipio, "uf": r.uf,
        "atualizado_em": r.atualizado_em, "n_paradas": int(r.n_paradas or 0),
    } for r in rows]


def carregar_rota(db: Session, rota_id: int) -> dict | None:
    r = db.execute(text("""
        SELECT id, nome, vendedor, municipio, uf FROM rota WHERE id = :id
    """), {"id": rota_id}).fetchone()
    if r is None:
        return None
    paradas = db.execute(text("""
        SELECT ordem, documento, nome_cache, eh_cliente, cep_cache, lat_cache, lng_cache
        FROM rota_parada WHERE rota_id = :id ORDER BY ordem
    """), {"id": rota_id}).fetchall()
    return {
        "id": r.id, "nome": r.nome, "vendedor": r.vendedor,
        "municipio": r.municipio, "uf": r.uf,
        "paradas": [{
            "ordem": p.ordem, "documento": p.documento, "nome": p.nome_cache,
            "eh_cliente": bool(p.eh_cliente), "cep": p.cep_cache,
            "lat": p.lat_cache, "lng": p.lng_cache,
        } for p in paradas],
    }


def excluir_rota(db: Session, rota_id: int) -> None:
    db.execute(text("DELETE FROM rota WHERE id = :id"), {"id": rota_id})
```

> **Por que os serviços NÃO chamam `db.commit()`:** o `get_db` do projeto não commita no encerramento, então o **router** é quem commita (Task 6). Isso mantém o isolamento dos testes: a fixture `db` roda dentro de uma transação externa revertida ao final, e como o serviço só executa (INSERT/DELETE são visíveis na mesma transação/sessão sem commit), os testes leem os dados via `carregar_rota`/`listar_rotas` na mesma sessão e nada persiste de verdade. Um `db.commit()` no serviço comitaria a transação externa da fixture e vazaria dados entre testes.

- [ ] **Step 4: Rodar os testes para vê-los passar**

Run: `pytest tests/test_rotas_service.py -q`
Expected: PASS (todos os testes do módulo, incluindo puras + DB + CRUD).

- [ ] **Step 5: Commit**

```bash
git add app/rotas_service.py app/tests/test_rotas_service.py
git commit -m "feat: CRUD de rotas (criar, listar, carregar, atualizar, excluir)"
```

---

## Task 5: Modelos Pydantic dos payloads

**Files:**
- Modify: `app/schemas.py` (acrescentar ao final)

- [ ] **Step 1: Adicionar os modelos em `app/schemas.py`**

No final de `app/schemas.py`, acrescentar:

```python
class ParadaIn(BaseModel):
    documento: str
    nome: str = "—"
    eh_cliente: bool = False
    cep: str | None = None
    lat: float | None = None
    lng: float | None = None


class OrdenarRequest(BaseModel):
    partida_idx: int = 0
    paradas: list[ParadaIn] = []


class MapsUrlsRequest(BaseModel):
    paradas: list[ParadaIn] = []


class SalvarRotaRequest(BaseModel):
    nome: str
    vendedor: str
    municipio: str
    uf: str
    paradas: list[ParadaIn] = []
```

> Verifique no topo de `schemas.py` que `from pydantic import BaseModel` já existe (todos os schemas atuais o usam). Se não estiver importado, adicione.

- [ ] **Step 2: Verificar que importa sem erro**

Run: `python -c "import schemas; schemas.SalvarRotaRequest(nome='x', vendedor='y', municipio='z', uf='PI')"`
Expected: sem saída e exit 0 (modelo válido com `paradas` default vazio).

- [ ] **Step 3: Commit**

```bash
git add app/schemas.py
git commit -m "feat: schemas dos payloads de rota"
```

---

## Task 6: Router `app/routers/rotas.py` + registro no main

**Files:**
- Create: `app/routers/rotas.py`
- Modify: `app/main.py` (import + `app.include_router`)

- [ ] **Step 1: Criar `app/routers/rotas.py`**

```python
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import rotas_service as svc
from auth import require_login
from config import BRT
from database import get_db
from dashboard_service import opcoes_filtro
from schemas import MapsUrlsRequest, OrdenarRequest, SalvarRotaRequest

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/rotas", response_class=HTMLResponse)
def listar(request: Request, current_user: dict = Depends(require_login), db: Session = Depends(get_db)):
    return templates.TemplateResponse("rotas.html", {
        "request": request, "user": current_user,
        "rotas": svc.listar_rotas(db),
    })


@router.get("/rotas/nova", response_class=HTMLResponse)
def nova(request: Request, current_user: dict = Depends(require_login), db: Session = Depends(get_db)):
    return templates.TemplateResponse("rota_montar.html", {
        "request": request, "user": current_user,
        "vendedores": opcoes_filtro(db).get("vendedores", []),
        "rota": None, "trechos": [],
    })


@router.get("/rotas/{rota_id}", response_class=HTMLResponse)
def editar(rota_id: int, request: Request, current_user: dict = Depends(require_login),
           db: Session = Depends(get_db)):
    rota = svc.carregar_rota(db, rota_id)
    if rota is None:
        return RedirectResponse(url="/rotas", status_code=302)
    return templates.TemplateResponse("rota_montar.html", {
        "request": request, "user": current_user,
        "vendedores": opcoes_filtro(db).get("vendedores", []),
        "rota": rota, "trechos": svc.montar_urls_google_maps(rota["paradas"]),
    })


@router.get("/rotas/candidatos", response_class=HTMLResponse)
def candidatos(request: Request, vendedor: str = "", municipio: str = "",
               current_user: dict = Depends(require_login), db: Session = Depends(get_db)):
    itens = []
    if vendedor and municipio:
        hoje = datetime.now(BRT).date()
        itens = svc.candidatos(db, vendedor=vendedor, municipio_codigo=municipio, hoje=hoje)
    return templates.TemplateResponse("partials/rota_candidatos.html", {
        "request": request, "candidatos": itens,
    })


@router.post("/rotas/ordenar")
def ordenar(req: OrdenarRequest, current_user: dict = Depends(require_login)):
    paradas = [p.model_dump() for p in req.paradas]
    ordenado = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=req.partida_idx)
    return JSONResponse({"paradas": ordenado})


@router.post("/rotas/maps-urls")
def maps_urls(req: MapsUrlsRequest, current_user: dict = Depends(require_login)):
    paradas = [p.model_dump() for p in req.paradas]
    return JSONResponse({"trechos": svc.montar_urls_google_maps(paradas)})


@router.post("/rotas")
def criar(req: SalvarRotaRequest, current_user: dict = Depends(require_login),
          db: Session = Depends(get_db)):
    rid = svc.criar_rota(db, nome=req.nome, vendedor=req.vendedor, municipio=req.municipio,
                         uf=req.uf, paradas=[p.model_dump() for p in req.paradas])
    db.commit()
    return JSONResponse({"id": rid})


@router.post("/rotas/{rota_id}")
def atualizar(rota_id: int, req: SalvarRotaRequest, current_user: dict = Depends(require_login),
              db: Session = Depends(get_db)):
    svc.atualizar_rota(db, rota_id, nome=req.nome, paradas=[p.model_dump() for p in req.paradas])
    db.commit()
    return JSONResponse({"id": rota_id})


@router.post("/rotas/{rota_id}/excluir")
def excluir(rota_id: int, current_user: dict = Depends(require_login), db: Session = Depends(get_db)):
    svc.excluir_rota(db, rota_id)
    db.commit()
    return RedirectResponse(url="/rotas", status_code=302)
```

> Atenção à ordem das rotas: `/rotas/nova` e `/rotas/candidatos` são declaradas ANTES de `/rotas/{rota_id}` para não serem capturadas pelo path param. O FastAPI casa por ordem de declaração — mantenha `nova`/`candidatos` acima de `{rota_id}`. (`candidatos` começa com `/rotas/` mas tem segmento fixo, então declará-la antes evita ambiguidade.)

- [ ] **Step 2: Registrar o router em `app/main.py`**

Adicionar o import junto aos outros (após a linha `from routers.navegacao import router as navegacao_router`):

```python
from routers.rotas import router as rotas_router
```

E registrar (após `app.include_router(navegacao_router)`):

```python
app.include_router(rotas_router)
```

- [ ] **Step 3: Verificar que o app importa sem erro**

Run: `python -c "import main; print('ok')"`
Expected: imprime `ok` (sem ImportError; o router foi registrado).

- [ ] **Step 4: Commit**

```bash
git add app/routers/rotas.py app/main.py
git commit -m "feat: router de rotas e registro no app"
```

---

## Task 7: Item no menu + tela "Minhas rotas"

**Files:**
- Modify: `app/templates/partials/sidebar.html`
- Create: `app/templates/rotas.html`

- [ ] **Step 1: Adicionar o item "Rotas" no menu**

Em `app/templates/partials/sidebar.html`, após a linha do item Dashboards (linha ~22, `{{ item('/dashboards', …) }}`), inserir:

```html
    {{ item('/rotas', '🧭', 'Rotas', path.startswith('/rotas')) }}
```

- [ ] **Step 2: Criar `app/templates/rotas.html`**

```html
{% extends "base.html" %}
{% block title %}SBR Leads — Rotas{% endblock %}

{% block content %}
<div class="space-y-4">
  <div class="flex items-center justify-between">
    <div>
      <h1 class="text-xl font-semibold text-white">Rotas de visita</h1>
      <p class="text-sm text-[#888]">Monte e salve rotas de visita por vendedor.</p>
    </div>
    <a href="/rotas/nova"
       class="text-sm px-4 py-2 rounded-lg bg-orange-500 text-white font-semibold hover:bg-orange-600 transition-colors">
      + Nova rota
    </a>
  </div>

  {% if rotas %}
  <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] overflow-hidden">
    <table class="w-full text-sm">
      <thead class="text-[#888] border-b border-[#2e2e2e]">
        <tr>
          <th class="text-left px-4 py-3 font-medium">Nome</th>
          <th class="text-left px-4 py-3 font-medium">Vendedor</th>
          <th class="text-left px-4 py-3 font-medium">Cidade</th>
          <th class="text-right px-4 py-3 font-medium">Paradas</th>
          <th class="text-right px-4 py-3 font-medium">Atualizada</th>
          <th class="px-4 py-3"></th>
        </tr>
      </thead>
      <tbody>
        {% for r in rotas %}
        <tr class="border-b border-[#1e1e1e] hover:bg-[#1a1a1a]">
          <td class="px-4 py-3"><a href="/rotas/{{ r.id }}" class="text-orange-500 hover:underline">{{ r.nome }}</a></td>
          <td class="px-4 py-3 text-[#ccc]">{{ r.vendedor }}</td>
          <td class="px-4 py-3 text-[#ccc]">{{ r.municipio }}/{{ r.uf }}</td>
          <td class="px-4 py-3 text-right text-[#ccc]">{{ r.n_paradas }}</td>
          <td class="px-4 py-3 text-right text-[#777]">{{ r.atualizado_em.strftime('%d/%m/%Y') if r.atualizado_em else '—' }}</td>
          <td class="px-4 py-3 text-right">
            <form method="post" action="/rotas/{{ r.id }}/excluir"
                  onsubmit="return confirm('Excluir a rota “{{ r.nome }}”?')">
              <button type="submit" class="text-xs text-[#666] hover:text-red-400">excluir</button>
            </form>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% else %}
  <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-12 text-center text-[#555]">
    <p class="font-medium text-[#666]">Nenhuma rota salva ainda. Clique em “+ Nova rota” para montar a primeira.</p>
  </div>
  {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: Verificação manual da lista**

Run (subir o app): `docker compose up -d` (ou o comando de dev do projeto) e abrir `http://localhost:8000/rotas` logado (admin@sbr.local).
Expected: menu mostra "Rotas"; a página abre com o estado vazio ("Nenhuma rota salva ainda") e o botão "+ Nova rota".

- [ ] **Step 4: Commit**

```bash
git add app/templates/partials/sidebar.html app/templates/rotas.html
git commit -m "feat: menu Rotas e tela Minhas rotas"
```

---

## Task 8: Tela de montagem (3 colunas) + parcial de candidatos

**Files:**
- Create: `app/templates/partials/rota_candidatos.html`
- Create: `app/templates/rota_montar.html`

- [ ] **Step 1: Criar o parcial `app/templates/partials/rota_candidatos.html`**

```html
{% if candidatos %}
<ul class="divide-y divide-[#1e1e1e]">
  {% for c in candidatos %}
  <li class="flex items-start gap-2 px-2 py-2 text-sm">
    <input type="checkbox" class="mt-1 cand-check"
           data-documento="{{ c.documento }}"
           data-nome="{{ c.nome }}"
           data-cep="{{ c.cep or '' }}"
           data-eh-cliente="{{ '1' if c.eh_cliente else '0' }}"
           data-logradouro="{{ c.logradouro or '' }}"
           data-tipo="{{ c.tipo_logradouro or '' }}"
           data-numero="{{ c.numero or '' }}"
           data-municipio="{{ c.municipio or '' }}"
           data-uf="{{ c.uf or '' }}"
           onclick="window.toggleCandidato && window.toggleCandidato(this)">
    <div class="min-w-0">
      <div class="text-[#ddd] truncate">
        {{ c.nome }}
        {% if c.em_risco %}<span class="ml-1 text-xs text-red-400">🔴 em risco</span>{% endif %}
      </div>
      <div class="text-xs text-[#777]">
        {% if c.eh_cliente %}Cliente{% if c.vendedor %} · {{ c.vendedor }}{% endif %}{% else %}Prospecto{% endif %}
        {% if c.bairro %} · {{ c.bairro }}{% endif %}
      </div>
    </div>
  </li>
  {% endfor %}
</ul>
{% else %}
<p class="text-sm text-[#666] px-2 py-4 text-center">Escolha vendedor e cidade para listar os candidatos.</p>
{% endif %}
```

- [ ] **Step 2: Criar a tela `app/templates/rota_montar.html`**

```html
{% extends "base.html" %}
{% block title %}SBR Leads — Montar rota{% endblock %}

{% block head_extra %}
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"
        integrity="sha384-1nUgmAum2HUv5+lQqJ8s9wXjsZ7uX4dr96H+7Aw9Cw2vQz4xKkVTr8fG3X3p+B2k"
        crossorigin="anonymous"></script>
{% endblock %}

{% block content %}
{% set rota_json = (rota | tojson) if rota else 'null' %}
<div class="space-y-4" id="rota-app" data-rota='{{ rota_json }}'>
  <div class="flex items-center justify-between">
    <h1 class="text-xl font-semibold text-white">{{ 'Editar rota' if rota else 'Nova rota' }}</h1>
    <a href="/rotas" class="text-sm text-[#888] hover:text-[#ccc]">← Minhas rotas</a>
  </div>

  <!-- Filtros -->
  <div class="bg-[#171717] rounded-xl border border-[#2e2e2e] p-4 flex flex-wrap gap-3 items-end">
    <label class="text-xs text-[#888]">Vendedor
      <select id="f-vendedor" class="block mt-1 bg-[#222] border border-[#3a3a3a] rounded-lg px-3 py-2 text-sm text-[#ddd]">
        <option value="">Selecione…</option>
        {% for v in vendedores %}
        <option value="{{ v }}" {{ 'selected' if rota and rota.vendedor == v else '' }}>{{ v }}</option>
        {% endfor %}
      </select>
    </label>
    <label class="text-xs text-[#888]">UF
      <input id="f-uf" maxlength="2" value="{{ rota.uf if rota else '' }}"
             class="block mt-1 w-16 bg-[#222] border border-[#3a3a3a] rounded-lg px-3 py-2 text-sm text-[#ddd] uppercase">
    </label>
    <label class="text-xs text-[#888]">Cidade (código IBGE)
      <input id="f-municipio" value="{{ rota.municipio if rota else '' }}"
             class="block mt-1 bg-[#222] border border-[#3a3a3a] rounded-lg px-3 py-2 text-sm text-[#ddd]">
    </label>
    <button type="button" id="btn-carregar"
            hx-get="/rotas/candidatos" hx-include="#f-vendedor,#f-municipio" hx-target="#lista-candidatos"
            hx-vals='js:{vendedor: document.getElementById("f-vendedor").value, municipio: document.getElementById("f-municipio").value}'
            class="text-sm px-4 py-2 rounded-lg border border-[#3a3a3a] text-[#ccc] hover:border-orange-500 hover:text-orange-500">
      Carregar candidatos
    </button>
  </div>

  <!-- 3 colunas -->
  <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
    <!-- Candidatos -->
    <div class="lg:col-span-3 bg-[#171717] rounded-xl border border-[#2e2e2e] p-2 max-h-[70vh] overflow-y-auto">
      <div class="text-[9px] uppercase tracking-wider text-[#444] px-2 py-1">Candidatos</div>
      <div id="lista-candidatos">
        {% include "partials/rota_candidatos.html" %}
      </div>
    </div>

    <!-- Mapa -->
    <div class="lg:col-span-6 bg-[#171717] rounded-xl border border-[#2e2e2e] overflow-hidden">
      <div id="mapa"></div>
    </div>

    <!-- Rota -->
    <div class="lg:col-span-3 bg-[#171717] rounded-xl border border-[#2e2e2e] p-3 flex flex-col max-h-[70vh]">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[9px] uppercase tracking-wider text-[#444]">Rota (<span id="conta-paradas">0</span>)</span>
      </div>
      <ul id="lista-rota" class="flex-1 overflow-y-auto space-y-1 text-sm"></ul>
      <div class="mt-3 space-y-2">
        <button type="button" id="btn-ordenar"
                class="w-full text-sm px-3 py-2 rounded-lg border border-[#3a3a3a] text-[#ccc] hover:border-orange-500 hover:text-orange-500">
          Ordenar automaticamente
        </button>
        <button type="button" id="btn-maps"
                class="w-full text-sm px-3 py-2 rounded-lg border border-[#3a3a3a] text-[#ccc] hover:border-orange-500 hover:text-orange-500">
          Abrir no Google Maps
        </button>
        <button type="button" id="btn-salvar"
                class="w-full text-sm px-3 py-2 rounded-lg bg-orange-500 text-white font-semibold hover:bg-orange-600">
          Salvar rota
        </button>
        <div id="trechos-maps" class="space-y-1"></div>
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
{% include "partials/rota_montar_js.html" %}
</script>
{% endblock %}
```

- [ ] **Step 3: Commit (templates ainda sem o JS — vem na próxima task)**

```bash
git add app/templates/partials/rota_candidatos.html app/templates/rota_montar.html
git commit -m "feat: tela de montagem de rota (markup das 3 colunas)"
```

---

## Task 9: JavaScript da montagem (estado, geocode, mapa, ações)

**Files:**
- Create: `app/templates/partials/rota_montar_js.html`

- [ ] **Step 1: Criar `app/templates/partials/rota_montar_js.html`**

> Geocodifica por CEP (AwesomeAPI) reusando as MESMAS chaves de cache do Mapa (`pm2_cep_…`), depois por endereço (Photon) como fallback. Mantém o estado da rota em memória; arrastar reordena sem roundtrip; "Ordenar" e "Abrir no Maps" chamam o backend (funções puras testadas).

```html
(function () {
  const appEl = document.getElementById('rota-app');
  if (!appEl) return;
  const rotaSalva = JSON.parse(appEl.dataset.rota || 'null');

  let paradas = [];          // [{documento, nome, eh_cliente, cep, lat, lng, logradouro,...}]
  let partidaIdx = 0;

  // ---------- geocode (reusa cache do Mapa) ----------
  function cacheGet(k) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch (_) { return null; } }
  function cacheSet(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (_) {} }

  async function coordsPorCep(cep) {
    const limpo = (cep || '').replace(/\D/g, '');
    if (limpo.length !== 8) return null;
    const chave = 'pm2_cep_' + limpo;
    const c = cacheGet(chave);
    if (c !== null) return c.lat ? c : null;
    try {
      const r = await fetch('https://cep.awesomeapi.com.br/json/' + limpo);
      if (!r.ok) { cacheSet(chave, { lat: null }); return null; }
      const d = await r.json();
      if (!d.lat || !d.lng) { cacheSet(chave, { lat: null }); return null; }
      const coords = { lat: parseFloat(d.lat), lng: parseFloat(d.lng) };
      cacheSet(chave, coords);
      return coords;
    } catch (_) { return null; }
  }

  async function geocodeParada(p) {
    if (p.lat != null && p.lng != null) return;
    const c = await coordsPorCep(p.cep);
    if (c) { p.lat = c.lat; p.lng = c.lng; }
  }

  // ---------- render ----------
  function render() {
    document.getElementById('conta-paradas').textContent = paradas.length;
    const ul = document.getElementById('lista-rota');
    ul.innerHTML = '';
    paradas.forEach((p, i) => {
      const li = document.createElement('li');
      li.className = 'flex items-center gap-2 px-2 py-1.5 rounded bg-[#1c1c1c] border border-[#2a2a2a]';
      li.dataset.documento = p.documento;
      li.innerHTML =
        '<span class="cursor-move text-[#555]">⠿</span>' +
        '<span class="text-[#888] w-5 text-center">' + (i + 1) + '</span>' +
        '<span class="flex-1 truncate text-[#ddd]">' + (i === partidaIdx ? '🏁 ' : '') + (p.nome || '') + '</span>' +
        '<button class="text-[#666] hover:text-orange-500 text-xs" title="Definir como partida">↑</button>' +
        '<button class="text-[#666] hover:text-red-400 text-xs" title="Remover">✕</button>';
      const [, , , btnPart, btnRem] = li.children;
      btnPart.onclick = () => { partidaIdx = i; render(); };
      btnRem.onclick = () => { paradas.splice(i, 1); if (partidaIdx >= paradas.length) partidaIdx = 0; render(); desenharMapa(); };
      ul.appendChild(li);
    });
    sincronizarChecks();
  }

  function sincronizarChecks() {
    const docs = new Set(paradas.map(p => p.documento));
    document.querySelectorAll('.cand-check').forEach(ch => { ch.checked = docs.has(ch.dataset.documento); });
  }

  // ---------- candidatos ----------
  window.toggleCandidato = async function (ch) {
    const doc = ch.dataset.documento;
    const idx = paradas.findIndex(p => p.documento === doc);
    if (idx >= 0) { paradas.splice(idx, 1); if (partidaIdx >= paradas.length) partidaIdx = 0; }
    else {
      const p = {
        documento: doc, nome: ch.dataset.nome, cep: ch.dataset.cep,
        eh_cliente: ch.dataset.ehCliente === '1', lat: null, lng: null,
      };
      await geocodeParada(p);
      paradas.push(p);
    }
    render();
    desenharMapa();
  };

  // ---------- mapa ----------
  let mapa, camada;
  function desenharMapa() {
    if (!window.L) return;
    if (!mapa) {
      mapa = L.map('mapa').setView([-15.77, -47.93], 5);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
        { attribution: '© OpenStreetMap contributors', maxZoom: 19 }).addTo(mapa);
    }
    if (camada) mapa.removeLayer(camada);
    camada = L.layerGroup().addTo(mapa);
    const pts = [];
    paradas.forEach((p, i) => {
      if (p.lat == null || p.lng == null) return;
      const icon = L.divIcon({
        html: '<div style="background:#f97316;color:#fff;width:22px;height:22px;border-radius:50%;border:2px solid #fff;text-align:center;line-height:22px;font-size:11px;font-weight:700">' + (i + 1) + '</div>',
        className: 'rota-pin', iconSize: [26, 26], iconAnchor: [13, 13],
      });
      L.marker([p.lat, p.lng], { icon }).addTo(camada);
      pts.push([p.lat, p.lng]);
    });
    if (pts.length) {
      L.polyline(pts, { color: '#f97316', weight: 2, opacity: 0.6 }).addTo(camada);
      mapa.fitBounds(pts, { padding: [40, 40], maxZoom: 15 });
    }
    setTimeout(() => mapa.invalidateSize(), 100);
  }

  // ---------- ações (backend) ----------
  async function postJson(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return r.ok ? r.json() : null;
  }

  document.getElementById('btn-ordenar').onclick = async () => {
    const d = await postJson('/rotas/ordenar', { partida_idx: partidaIdx, paradas });
    if (d && d.paradas) { paradas = d.paradas; partidaIdx = 0; render(); desenharMapa(); }
  };

  document.getElementById('btn-maps').onclick = async () => {
    const d = await postJson('/rotas/maps-urls', { paradas });
    const cont = document.getElementById('trechos-maps');
    cont.innerHTML = '';
    if (!d || !d.trechos || !d.trechos.length) { cont.innerHTML = '<p class="text-xs text-[#666]">Adicione ao menos 2 paradas com endereço.</p>'; return; }
    if (d.trechos.length === 1) { window.open(d.trechos[0], '_blank'); return; }
    d.trechos.forEach((u, i) => {
      const a = document.createElement('a');
      a.href = u; a.target = '_blank';
      a.className = 'block text-xs text-orange-500 hover:underline';
      a.textContent = 'Abrir trecho ' + (i + 1);
      cont.appendChild(a);
    });
  };

  document.getElementById('btn-salvar').onclick = async () => {
    const vendedor = document.getElementById('f-vendedor').value;
    const uf = document.getElementById('f-uf').value.toUpperCase();
    const municipio = document.getElementById('f-municipio').value;
    if (!vendedor || !municipio || !paradas.length) { alert('Escolha vendedor, cidade e ao menos uma parada.'); return; }
    const nome = prompt('Nome da rota:', (rotaSalva && rotaSalva.nome) || '');
    if (!nome) return;
    const body = { nome, vendedor, municipio, uf, paradas };
    const url = rotaSalva ? '/rotas/' + rotaSalva.id : '/rotas';
    const d = await postJson(url, body);
    if (d && d.id) window.location.href = '/rotas';
  };

  // ---------- drag & drop ----------
  if (window.Sortable) {
    new Sortable(document.getElementById('lista-rota'), {
      handle: '.cursor-move', animation: 150,
      onEnd: () => {
        const ordem = Array.from(document.getElementById('lista-rota').children).map(li => li.dataset.documento);
        paradas.sort((a, b) => ordem.indexOf(a.documento) - ordem.indexOf(b.documento));
        partidaIdx = 0;
        render(); desenharMapa();
      },
    });
  }

  // ---------- init (rota salva) ----------
  if (rotaSalva && rotaSalva.paradas) {
    paradas = rotaSalva.paradas.map(p => ({
      documento: p.documento, nome: p.nome, cep: p.cep,
      eh_cliente: p.eh_cliente, lat: p.lat, lng: p.lng,
    }));
  }
  render();
  desenharMapa();
})();
```

- [ ] **Step 2: Verificação manual ponta a ponta**

Subir o app e abrir `http://localhost:8000/rotas/nova` logado. Verificar:
1. Selecionar um vendedor, digitar UF (ex.: `PI`) e código IBGE de uma cidade (ex.: Floriano `2211001`), clicar **Carregar candidatos** → lista aparece com selos 🔴 nos clientes em risco.
2. Marcar candidatos → entram na coluna Rota e aparecem pinos numerados no mapa.
3. Definir uma parada como 🏁 e clicar **Ordenar automaticamente** → ordem muda; números/pinos atualizam.
4. Arrastar para reordenar → ordem persiste na UI.
5. **Abrir no Google Maps** → abre 1 aba (≤10 paradas) ou lista links de trechos (>10).
6. **Salvar rota** (dar nome) → volta para `/rotas` com a rota na lista.
7. Reabrir a rota salva (`/rotas/{id}`) → paradas carregam na ordem, pinos no mapa sem regeocodificar.

Expected: todos os passos funcionam; nenhum erro no console do navegador.

- [ ] **Step 3: Rodar a suíte completa**

Run: `pytest -q`
Expected: PASS (suíte inteira verde, incluindo os novos testes de `rotas_service`).

- [ ] **Step 4: Commit**

```bash
git add app/templates/partials/rota_montar_js.html
git commit -m "feat: javascript da montagem de rota (estado, geocode, mapa, acoes)"
```

---

## Verificação final

- [ ] `pytest -q` — suíte inteira verde.
- [ ] App sobe (`docker compose up`) e o fluxo manual da Task 9 funciona ponta a ponta.
- [ ] Menu mostra "Rotas"; criar, ordenar, salvar, reabrir e excluir rota funcionam.
- [ ] Atualizar `docs/CLAUDE.md` (estado do projeto) e a memória do brainstorm marcando a feature como implementada.

## Notas e riscos

- **Geocodificação client-side:** a precisão depende do CEP retornar lat/lng na AwesomeAPI (limite 1.000/dia/IP, mitigado pelo cache `localStorage` compartilhado com o Mapa). Paradas sem coords não entram na ordenação nem nas URLs do Maps — vão para o fim da lista.
- **SortableJS via CDN:** o hash SRI no `head_extra` é um placeholder de exemplo. Ao implementar, gere o SRI real da versão `1.15.2` (ou remova o `integrity` se preferir, seguindo a política de SRI do projeto) — **não** use o hash de exemplo em produção.
- **Cidade por código IBGE:** o MVP usa input de código IBGE do município (alinhado a `estabelecimento.municipio`). Uma evolução simples é trocar por um autocomplete reusando `/api/municipios` (já existente), fora do escopo deste plano.
- **Limite de 10 waypoints:** o corte é configurável (`max_por_trecho`); o padrão 10 é conservador para a URL pública do Google Maps.
```
