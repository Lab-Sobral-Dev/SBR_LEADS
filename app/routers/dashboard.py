import time
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import dashboard_service as svc
import analise_service as svc_analise
import recompra_service as svc_recompra
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


_cache_recompra: dict = {}  # chave -> (ts, dados)


def _dados_recompra_cacheados(db: Session, *, vendedor, cidade, uf, hoje) -> dict:
    chave = "|".join([vendedor or "", cidade or "", uf or "", hoje.isoformat()])
    agora = time.monotonic()
    item = _cache_recompra.get(chave)
    if item and (agora - item[0]) < _CACHE_TTL_SEGUNDOS:
        return item[1]
    dados = svc_recompra.montar_recompra(db, vendedor=vendedor, cidade=cidade, uf=uf, hoje=hoje)
    _cache_recompra[chave] = (agora, dados)
    return dados


@router.get("/dashboard/recompra", response_class=HTMLResponse)
def dashboard_recompra(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    hoje = datetime.now(BRT).date()
    q = dict(request.query_params)
    vendedor = q.get("vendedor") or None
    cidade = q.get("cidade") or None
    uf = q.get("uf") or None
    faixa = q.get("faixa") or ""

    dados = _dados_recompra_cacheados(db, vendedor=vendedor, cidade=cidade, uf=uf, hoje=hoje)
    clientes = dados["clientes"]
    if faixa:
        clientes = [c for c in clientes if c["faixa"] == faixa]

    ctx = {
        "request": request,
        "user": current_user,
        "kpis": dados["kpis"],
        "clientes": clientes,
        "opcoes": svc_recompra.opcoes_recompra(db),
        "filtros": {"vendedor": vendedor or "", "cidade": cidade or "", "uf": uf or "", "faixa": faixa},
    }
    template = "partials/recompra_paineis.html" if request.headers.get("HX-Request") else "recompra.html"
    return templates.TemplateResponse(template, ctx)
