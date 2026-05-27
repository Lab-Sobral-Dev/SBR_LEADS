import csv
import io
from collections.abc import Iterator

import openpyxl
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from schemas import AtalhosCnae, BuscarRequest, BuscarResponse, Cnae, Lead, Municipio, Stats, UF
from service import ATALHOS, PORTES, SELECT_LEADS, build_order_by, build_where, buscar, contar, resolve_cnaes, row_to_lead

LIMITE_EXPORTACAO = 50_000


def _execute_streaming(db: Session, sql: str, params: dict):
    """psycopg2 + SQLAlchemy bufferam tudo por padrão; stream_results força
    cursor server-side para iterar linha a linha sem carregar 50k em RAM."""
    return db.connection().execution_options(stream_results=True).execute(text(sql), params)

router = APIRouter(prefix="/api")

_UFS = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapá"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceará"), ("DF", "Distrito Federal"),
    ("ES", "Espírito Santo"), ("GO", "Goiás"), ("MA", "Maranhão"),
    ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"), ("MG", "Minas Gerais"),
    ("PA", "Pará"), ("PB", "Paraíba"), ("PR", "Paraná"), ("PE", "Pernambuco"),
    ("PI", "Piauí"), ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondônia"), ("RR", "Roraima"),
    ("SC", "Santa Catarina"), ("SP", "São Paulo"), ("SE", "Sergipe"),
    ("TO", "Tocantins"),
]


_HEADER_EXPORT = [
    "CNPJ", "Razão Social", "Nome Fantasia", "CNAE", "Descrição CNAE",
    "Logradouro", "Número", "Complemento", "Bairro", "CEP",
    "UF", "Município", "DDD 1", "Telefone 1", "DDD 2", "Telefone 2",
    "E-mail", "Situação", "Porte", "Capital Social",
    "Já é Cliente", "Vendedor",
]


def _lead_to_row(lead: Lead) -> list:
    logradouro = f"{lead.tipo_logradouro or ''} {lead.logradouro or ''}".strip()
    return [
        lead.cnpj, lead.razao_social, lead.nome_fantasia,
        lead.cnae_principal, lead.cnae_descricao,
        logradouro, lead.numero, lead.complemento, lead.bairro, lead.cep,
        lead.uf, lead.municipio,
        lead.ddd_1, lead.telefone_1, lead.ddd_2, lead.telefone_2,
        lead.email, lead.situacao, PORTES.get(lead.porte or "", lead.porte),
        lead.capital_social,
        "Sim" if lead.eh_cliente else "Não",
        lead.vendedor,
    ]


def _stream_csv(req: BuscarRequest, db: Session) -> Iterator[bytes]:
    cnaes = resolve_cnaes(req)
    where, params = build_where(req, cnaes)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")

    writer.writerow(_HEADER_EXPORT)
    yield buf.getvalue().encode("utf-8-sig")

    result = _execute_streaming(
        db,
        f"{SELECT_LEADS} WHERE {where} ORDER BY {build_order_by(req)} LIMIT :limit",
        {**params, "limit": LIMITE_EXPORTACAO},
    )
    for row in result:
        lead = row_to_lead(row)
        buf.seek(0)
        buf.truncate()
        writer.writerow(_lead_to_row(lead))
        yield buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# Endpoints de referência
# ---------------------------------------------------------------------------

@router.get("/ufs", response_model=list[UF])
def listar_ufs(_: dict = Depends(require_login)):
    return [UF(sigla=s, nome=n) for s, n in _UFS]


@router.get("/municipios", response_model=list[Municipio])
def listar_municipios(
    uf: str | None = Query(None, description="Filtrar por UF"),
    q: str | None = Query(None, description="Busca parcial pelo nome"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_login),
):
    sql = """
        SELECT DISTINCT m.codigo, m.descricao
        FROM municipio m
        JOIN estabelecimento e ON e.municipio = m.codigo
        WHERE (:uf   IS NULL OR e.uf         = :uf)
          AND (:q    IS NULL OR m.descricao ILIKE :q_like)
        ORDER BY m.descricao
        LIMIT 50
    """
    rows = db.execute(
        text(sql),
        {"uf": uf.upper() if uf else None, "q": q, "q_like": f"%{q}%" if q else None},
    ).fetchall()
    return [Municipio(codigo=r.codigo, descricao=r.descricao) for r in rows]


@router.get("/cnaes", response_model=list[Cnae])
def buscar_cnaes(
    q: str = Query(..., description="Texto para busca na descrição do CNAE"),
    db: Session = Depends(get_db),
    _: dict = Depends(require_login),
):
    rows = db.execute(
        text("SELECT codigo, descricao FROM cnae WHERE descricao ILIKE :q ORDER BY descricao LIMIT 30"),
        {"q": f"%{q}%"},
    ).fetchall()
    return [Cnae(codigo=r.codigo, descricao=r.descricao) for r in rows]


@router.get("/cnaes/atalhos", response_model=list[AtalhosCnae])
def listar_atalhos(_: dict = Depends(require_login)):
    return [AtalhosCnae(**a) for a in ATALHOS]


# ---------------------------------------------------------------------------
# Busca e exportação
# ---------------------------------------------------------------------------

@router.post("/buscar", response_model=BuscarResponse)
def buscar_leads(req: BuscarRequest, db: Session = Depends(get_db), _: dict = Depends(require_login)):
    return buscar(req, db)


@router.post("/exportar.csv")
def exportar_csv(req: BuscarRequest, db: Session = Depends(get_db), _: dict = Depends(require_login)):
    total = contar(req, db)
    return StreamingResponse(
        _stream_csv(req, db),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=prospec-leads.csv",
            "X-Total-Disponivel": str(total),
            "X-Truncado": str(total > LIMITE_EXPORTACAO).lower(),
        },
    )


@router.post("/exportar.xlsx")
def exportar_xlsx(req: BuscarRequest, db: Session = Depends(get_db), _: dict = Depends(require_login)):
    cnaes = resolve_cnaes(req)
    where, params = build_where(req, cnaes)
    total = contar(req, db)

    # write_only mantém uso de memória ~constante: cada linha é serializada
    # no XML temporário e descartada da RAM imediatamente.
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet("Leads")

    bold = Font(bold=True)
    header = []
    for h in _HEADER_EXPORT:
        cell = WriteOnlyCell(ws, value=h)
        cell.font = bold
        header.append(cell)
    ws.append(header)

    result = _execute_streaming(
        db,
        f"{SELECT_LEADS} WHERE {where} ORDER BY {build_order_by(req)} LIMIT :limit",
        {**params, "limit": LIMITE_EXPORTACAO},
    )
    for row in result:
        ws.append(_lead_to_row(row_to_lead(row)))

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=prospec-leads.xlsx",
            "X-Total-Disponivel": str(total),
            "X-Truncado": str(total > LIMITE_EXPORTACAO).lower(),
        },
    )


# ---------------------------------------------------------------------------
# Estatísticas
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=Stats)
def estatisticas(db: Session = Depends(get_db), _: dict = Depends(require_login)):
    total_estab = db.execute(text("SELECT COUNT(*) FROM estabelecimento")).scalar() or 0
    total_emp = db.execute(text("SELECT COUNT(*) FROM empresa")).scalar() or 0

    ultima = db.execute(
        text("SELECT mes_referencia FROM importacao WHERE status='concluido' ORDER BY concluida_em DESC LIMIT 1")
    ).scalar()

    dist = db.execute(
        text("""
            SELECT uf, COUNT(*) AS total
            FROM estabelecimento
            WHERE situacao_cadastral = '02'
            GROUP BY uf
            ORDER BY total DESC
        """)
    ).fetchall()

    return Stats(
        total_estabelecimentos=total_estab,
        total_empresas=total_emp,
        ultima_importacao=ultima,
        distribuicao_uf=[{"uf": r.uf, "total": r.total} for r in dist],
    )
