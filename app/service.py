import math
from datetime import date

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from schemas import BuscarRequest, BuscarResponse, Lead

# ---------------------------------------------------------------------------
# Dados de domínio compartilhados entre api.py e frontend.py
# ---------------------------------------------------------------------------

ATALHOS: list[dict] = [
    {"segmento": "farmacia",      "descricao": "Farmácias e drogarias",         "cnaes": ["4771701", "4771702", "4771703"]},
    {"segmento": "restaurante",   "descricao": "Restaurantes e lanchonetes",    "cnaes": ["5611201", "5611203", "5611204", "5611205"]},
    {"segmento": "oficina",       "descricao": "Oficinas mecânicas",            "cnaes": ["4520001", "4520002", "4520003", "4520004", "4520005"]},
    {"segmento": "supermercado",  "descricao": "Supermercados e mercados",      "cnaes": ["4711301", "4711302"]},
    {"segmento": "padaria",       "descricao": "Padarias e confeitarias",       "cnaes": ["1091102", "4721102"]},
    {"segmento": "salao",         "descricao": "Salões de beleza e barbearias", "cnaes": ["9602501", "9602502"]},
    {"segmento": "clinica",       "descricao": "Clínicas médicas",              "cnaes": ["8630501", "8630502", "8630503"]},
    {"segmento": "academia",      "descricao": "Academias de ginástica",        "cnaes": ["9313100"]},
    {"segmento": "advocacia",     "descricao": "Escritórios de advocacia",      "cnaes": ["6911701"]},
    {"segmento": "contabilidade", "descricao": "Contabilidade e auditoria",     "cnaes": ["6920601", "6920602"]},
]

_ATALHOS_MAP: dict[str, list[str]] = {a["segmento"]: a["cnaes"] for a in ATALHOS}

PORTES: dict[str, str] = {
    "00": "Não informado",
    "01": "MEI",
    "03": "ME",
    "05": "EPP",
    "99": "Demais",
}

_FROM_LEADS = """
    FROM estabelecimento e
    LEFT JOIN empresa    emp ON emp.cnpj_basico = e.cnpj_basico
    LEFT JOIN municipio  m   ON m.codigo        = e.municipio
    LEFT JOIN cnae       c   ON c.codigo        = e.cnae_fiscal_principal
    LEFT JOIN cliente_pedido_mobile pm
           ON pm.documento = e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv
          AND pm.inativo = FALSE
"""

SELECT_LEADS = f"""
    SELECT
        e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj,
        emp.razao_social,
        e.nome_fantasia,
        e.cnae_fiscal_principal,
        c.descricao   AS cnae_descricao,
        e.tipo_logradouro,
        e.logradouro,
        e.numero,
        e.complemento,
        e.bairro,
        e.cep,
        e.uf,
        m.descricao   AS municipio,
        e.ddd_1,
        e.telefone_1,
        e.ddd_2,
        e.telefone_2,
        e.correio_eletronico,
        e.situacao_cadastral,
        emp.porte,
        emp.capital_social,
        pm.documento IS NOT NULL AS eh_cliente,
        pm.vendedor          AS vendedor,
        pm.ultima_compra_em  AS ultima_compra_em
    {_FROM_LEADS}
"""

_COUNT_SQL = f"SELECT COUNT(*) {_FROM_LEADS} WHERE {{where}}"

ORDENACOES: dict[str, str] = {
    "razao_social_asc":    "emp.razao_social ASC",
    "razao_social_desc":   "emp.razao_social DESC",
    "capital_desc":        "emp.capital_social DESC NULLS LAST",
    "capital_asc":         "emp.capital_social ASC NULLS LAST",
    "ultima_compra_desc":  "pm.ultima_compra_em DESC NULLS LAST",
    "ultima_compra_asc":   "pm.ultima_compra_em ASC NULLS LAST",
    "clientes_primeiro":   "(pm.documento IS NOT NULL) DESC, emp.razao_social ASC",
    "prospectos_primeiro": "(pm.documento IS NULL) DESC, emp.razao_social ASC",
}

_ORDENACAO_PADRAO = "emp.razao_social ASC"


def build_order_by(req: BuscarRequest) -> str:
    return ORDENACOES.get(req.ordenar or "", _ORDENACAO_PADRAO)

_STATS_FILTRO_SQL = f"""
    SELECT
        COUNT(DISTINCT e.cnpj_basico)                                   AS empresas,
        COUNT(CASE WHEN pm.documento IS NOT NULL THEN 1 END)            AS clientes
    {_FROM_LEADS}
    WHERE {{where}}
"""

# ---------------------------------------------------------------------------
# Funções de negócio
# ---------------------------------------------------------------------------

def resolve_cnaes(req: BuscarRequest) -> list[str] | None:
    if req.segmento:
        cnaes = _ATALHOS_MAP.get(req.segmento)
        if not cnaes:
            raise HTTPException(400, f"Segmento desconhecido: {req.segmento}")
        return cnaes
    return req.cnaes or None


def build_where(req: BuscarRequest, cnaes: list[str] | None) -> tuple[str, dict]:
    conditions = ["1=1"]
    params: dict = {}

    if req.uf:
        conditions.append("e.uf = :uf")
        params["uf"] = req.uf.upper()

    if req.municipio_codigo:
        conditions.append("e.municipio = :municipio")
        params["municipio"] = req.municipio_codigo

    if cnaes:
        conditions.append("e.cnae_fiscal_principal = ANY(:cnaes)")
        params["cnaes"] = cnaes

    if req.apenas_ativas:
        conditions.append("e.situacao_cadastral = '02'")

    if req.porte:
        conditions.append("emp.porte = :porte")
        params["porte"] = req.porte

    if req.status_cliente == "cliente":
        conditions.append("pm.documento IS NOT NULL")
    elif req.status_cliente == "prospect":
        conditions.append("pm.documento IS NULL")

    return " AND ".join(conditions), params


def row_to_lead(row) -> Lead:
    return Lead(
        cnpj=row.cnpj or "",
        razao_social=row.razao_social,
        nome_fantasia=row.nome_fantasia,
        cnae_principal=row.cnae_fiscal_principal,
        cnae_descricao=row.cnae_descricao,
        tipo_logradouro=row.tipo_logradouro,
        logradouro=row.logradouro,
        numero=row.numero,
        complemento=row.complemento,
        bairro=row.bairro,
        cep=row.cep,
        uf=row.uf,
        municipio=row.municipio,
        ddd_1=row.ddd_1,
        telefone_1=row.telefone_1,
        ddd_2=row.ddd_2,
        telefone_2=row.telefone_2,
        email=row.correio_eletronico,
        situacao=row.situacao_cadastral,
        porte=row.porte,
        capital_social=float(row.capital_social) if row.capital_social else None,
        eh_cliente=bool(row.eh_cliente),
        vendedor=row.vendedor,
        ultima_compra_em=row.ultima_compra_em,
        dias_sem_compra=(date.today() - row.ultima_compra_em).days if row.ultima_compra_em else None,
    )


def buscar(req: BuscarRequest, db: Session) -> BuscarResponse:
    cnaes = resolve_cnaes(req)
    where, params = build_where(req, cnaes)

    total = db.execute(
        text(_COUNT_SQL.format(where=where)), params
    ).scalar() or 0

    page_size = max(1, min(req.page_size, 200))
    page = max(1, req.page)
    offset = (page - 1) * page_size

    rows = db.execute(
        text(f"{SELECT_LEADS} WHERE {where} ORDER BY {build_order_by(req)} LIMIT :limit OFFSET :offset"),
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    return BuscarResponse(
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
        items=[row_to_lead(r) for r in rows],
    )


def contar(req: BuscarRequest, db: Session) -> int:
    cnaes = resolve_cnaes(req)
    where, params = build_where(req, cnaes)
    return db.execute(
        text(_COUNT_SQL.format(where=where)), params
    ).scalar() or 0


def buscar_stats(req: BuscarRequest, db: Session, total: int) -> dict:
    """Retorna contagens derivadas do filtro atual para exibição nos cards."""
    cnaes = resolve_cnaes(req)
    where, params = build_where(req, cnaes)
    row = db.execute(
        text(_STATS_FILTRO_SQL.format(where=where)), params
    ).fetchone()
    clientes = row.clientes or 0
    return {
        "estabelecimentos": total,
        "empresas": row.empresas or 0,
        "clientes": clientes,
        "prospectos": total - clientes,
    }


def buscar_para_mapa(req: BuscarRequest, db: Session, limite: int = 5000) -> list[Lead]:
    """Retorna leads ignorando paginação — usado para alimentar o mapa
    com todos os resultados do filtro, não só a página atual."""
    cnaes = resolve_cnaes(req)
    where, params = build_where(req, cnaes)
    rows = db.execute(
        text(f"{SELECT_LEADS} WHERE {where} ORDER BY {build_order_by(req)} LIMIT :limit"),
        {**params, "limit": limite},
    ).fetchall()
    return [row_to_lead(r) for r in rows]
