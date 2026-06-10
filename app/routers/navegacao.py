from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from pedido_mobile import info_pedido_mobile, sync_em_andamento
from schemas import Stats

router = APIRouter()
templates = Jinja2Templates(directory="templates")


def _get_stats(db: Session) -> Stats:
    try:
        total_estab = db.execute(text("SELECT COUNT(*) FROM estabelecimento")).scalar() or 0
        total_emp = db.execute(text("SELECT COUNT(*) FROM empresa")).scalar() or 0
        ultima = db.execute(
            text("SELECT mes_referencia FROM importacao WHERE status='concluido' ORDER BY concluida_em DESC LIMIT 1")
        ).scalar()
    except ProgrammingError:
        db.rollback()
        return Stats(total_estabelecimentos=0, total_empresas=0, ultima_importacao=None, distribuicao_uf=[])
    return Stats(
        total_estabelecimentos=total_estab,
        total_empresas=total_emp,
        ultima_importacao=ultima,
        distribuicao_uf=[],
    )


@router.get("/inicio", response_class=HTMLResponse)
def inicio(request: Request, current_user: dict = Depends(require_login), db: Session = Depends(get_db)):
    return templates.TemplateResponse("inicio.html", {
        "request": request, "user": current_user, "pm": info_pedido_mobile(db),
    })


@router.get("/dashboards", response_class=HTMLResponse)
def dashboards(request: Request, current_user: dict = Depends(require_login)):
    return templates.TemplateResponse("dashboards.html", {
        "request": request, "user": current_user,
    })


@router.get("/configuracoes", response_class=HTMLResponse)
def configuracoes(request: Request, current_user: dict = Depends(require_login), db: Session = Depends(get_db)):
    return templates.TemplateResponse("configuracoes.html", {
        "request": request, "user": current_user,
        "stats": _get_stats(db),
        "pm": info_pedido_mobile(db),
        "sincronizando": sync_em_andamento(db),
        "resultado": None,
        "erro": None,
    })
