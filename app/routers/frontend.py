import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db, SessionLocal
from pedido_mobile import SyncError, sincronizar, sync_em_andamento, total_clientes, ultima_sync
from routers.api import _UFS
from schemas import BuscarRequest, Cnae, Municipio, Stats, UF
from service import ATALHOS, buscar, buscar_para_mapa

LIMITE_MAPA = 5000

logger = logging.getLogger(__name__)


def _sincronizar_bg() -> None:
    db = SessionLocal()
    try:
        sincronizar(db)
    except Exception:
        logger.exception("Erro na sincronização em background")
    finally:
        db.close()

templates = Jinja2Templates(directory="templates")
router = APIRouter()


def _get_stats(db: Session) -> Stats:
    try:
        total_estab = db.execute(text("SELECT COUNT(*) FROM estabelecimento")).scalar() or 0
        total_emp = db.execute(text("SELECT COUNT(*) FROM empresa")).scalar() or 0
        ultima = db.execute(
            text("SELECT mes_referencia FROM importacao WHERE status='concluido' ORDER BY concluida_em DESC LIMIT 1")
        ).scalar()
    except ProgrammingError:
        db.rollback()
        return Stats(
            total_estabelecimentos=0,
            total_empresas=0,
            ultima_importacao=None,
            distribuicao_uf=[],
        )
    return Stats(
        total_estabelecimentos=total_estab,
        total_empresas=total_emp,
        ultima_importacao=ultima,
        distribuicao_uf=[],
    )


def _info_pedido_mobile(db: Session) -> dict:
    try:
        return {
            "total": total_clientes(db),
            "ultima": ultima_sync(db),
        }
    except Exception:
        db.rollback()
        return {"total": 0, "ultima": None}


@router.get("/", response_class=HTMLResponse)
def pagina_inicial(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    stats = _get_stats(db)
    ufs = [UF(sigla=s, nome=n) for s, n in _UFS]
    atalhos_view = [{"segmento": a["segmento"], "descricao": a["descricao"]} for a in ATALHOS]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": current_user,
        "ufs": ufs,
        "atalhos": atalhos_view,
        "stats": stats,
        "pm": _info_pedido_mobile(db),
    })


@router.post("/sync-clientes", response_class=HTMLResponse)
def sync_clientes(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    erro = None
    em_andamento = sync_em_andamento(db)
    if not em_andamento:
        try:
            background_tasks.add_task(_sincronizar_bg)
            em_andamento = True
        except SyncError as e:
            erro = str(e)

    return templates.TemplateResponse("partials/pedido_mobile_card.html", {
        "request": request,
        "pm": _info_pedido_mobile(db),
        "sincronizando": em_andamento,
        "resultado": None,
        "erro": erro,
    })


@router.get("/sync-status", response_class=HTMLResponse)
def sync_status(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    em_andamento = sync_em_andamento(db)
    return templates.TemplateResponse("partials/pedido_mobile_card.html", {
        "request": request,
        "pm": _info_pedido_mobile(db),
        "sincronizando": em_andamento,
        "resultado": None,
        "erro": None,
    })


@router.get("/municipios-options", response_class=HTMLResponse)
def municipios_options(
    request: Request,
    uf: str | None = None,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    municipios = []
    if uf:
        rows = db.execute(
            text("""
                SELECT DISTINCT m.codigo, m.descricao
                FROM municipio m
                JOIN estabelecimento e ON e.municipio = m.codigo
                WHERE e.uf = :uf
                ORDER BY m.descricao
            """),
            {"uf": uf.upper()},
        ).fetchall()
        municipios = [Municipio(codigo=r.codigo, descricao=r.descricao) for r in rows]
    return templates.TemplateResponse("partials/municipios_options.html", {
        "request": request,
        "municipios": municipios,
    })


@router.get("/cnaes-options", response_class=HTMLResponse)
def cnaes_options(
    request: Request,
    q: str = "",
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    cnaes = []
    if q.strip():
        rows = db.execute(
            text("SELECT codigo, descricao FROM cnae WHERE descricao ILIKE :q ORDER BY descricao LIMIT 15"),
            {"q": f"%{q}%"},
        ).fetchall()
        cnaes = [Cnae(codigo=r.codigo, descricao=r.descricao) for r in rows]
    return templates.TemplateResponse("partials/cnaes_options.html", {
        "request": request,
        "cnaes": cnaes,
    })


@router.post("/buscar", response_class=HTMLResponse)
async def buscar_html(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    form = await request.form()
    page = int(form.get("page") or 1)
    req = _form_to_req(form, page=page, page_size=50)

    resultado = buscar(req, db)

    leads_mapa = buscar_para_mapa(req, db, limite=LIMITE_MAPA)
    leads_json = json.dumps([{
        "cnpj": l.cnpj,
        "razao_social": l.razao_social,
        "nome_fantasia": l.nome_fantasia,
        "logradouro": l.logradouro,
        "tipo_logradouro": l.tipo_logradouro,
        "numero": l.numero,
        "municipio": l.municipio,
        "uf": l.uf,
        "cep": l.cep,
        "ddd_1": l.ddd_1,
        "telefone_1": l.telefone_1,
        "eh_cliente": l.eh_cliente,
        "vendedor": l.vendedor,
    } for l in leads_mapa], ensure_ascii=False).replace("</", "<\\/")

    # JSON completo dos leads da página atual — usado pelo modal de detalhes
    pagina_json = json.dumps([{
        "cnpj": l.cnpj,
        "razao_social": l.razao_social,
        "nome_fantasia": l.nome_fantasia,
        "cnae_principal": l.cnae_principal,
        "cnae_descricao": l.cnae_descricao,
        "tipo_logradouro": l.tipo_logradouro,
        "logradouro": l.logradouro,
        "numero": l.numero,
        "complemento": l.complemento,
        "bairro": l.bairro,
        "cep": l.cep,
        "uf": l.uf,
        "municipio": l.municipio,
        "ddd_1": l.ddd_1,
        "telefone_1": l.telefone_1,
        "ddd_2": l.ddd_2,
        "telefone_2": l.telefone_2,
        "email": l.email,
        "situacao": l.situacao,
        "porte": l.porte,
        "capital_social": l.capital_social,
        "eh_cliente": l.eh_cliente,
        "vendedor": l.vendedor,
        "ultima_compra_em": l.ultima_compra_em.strftime("%d/%m/%Y") if l.ultima_compra_em else None,
        "dias_sem_compra": l.dias_sem_compra,
    } for l in resultado.items], ensure_ascii=False).replace("</", "<\\/")

    return templates.TemplateResponse("partials/resultados.html", {
        "request": request,
        "resultado": resultado,
        "leads_json": leads_json,
        "pagina_json": pagina_json,
        "total_no_mapa": len(leads_mapa),
        "limite_mapa": LIMITE_MAPA,
    })


@router.post("/exportar.csv")
async def exportar_csv_form(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    from routers.api import exportar_csv
    form = await request.form()
    req = _form_to_req(form)
    return exportar_csv(req, db)


@router.post("/exportar.xlsx")
async def exportar_xlsx_form(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    from routers.api import exportar_xlsx
    form = await request.form()
    req = _form_to_req(form)
    return exportar_xlsx(req, db)


def _form_to_req(form, *, page: int = 1, page_size: int = 50) -> BuscarRequest:
    cnaes_raw = form.get("cnaes") or ""
    return BuscarRequest(
        uf=form.get("uf") or None,
        municipio_codigo=form.get("municipio_codigo") or None,
        segmento=form.get("segmento") or None,
        cnaes=[c.strip() for c in cnaes_raw.split(",") if c.strip()] if cnaes_raw else None,
        apenas_ativas=form.get("apenas_ativas") == "true",
        porte=form.get("porte") or None,
        status_cliente=form.get("status_cliente") or None,
        page=page,
        page_size=page_size,
    )
