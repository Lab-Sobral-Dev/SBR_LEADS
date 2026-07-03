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
from dashboard_filters import FiltrosDashboard, _limpar
from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

_CACHE_TTL_SEGUNDOS = 180


class _CacheTTL:
    """Cache em memória com TTL e poda de expiradas.

    As chaves embutem data/filtros do recorte; sem poda o dicionário cresceria
    sem limite (ao menos uma entrada nova por dia). A cada escrita removemos as
    entradas já vencidas, mantendo o tamanho limitado aos recortes acessados
    dentro da janela de TTL.
    """

    def __init__(self, ttl_segundos: int = _CACHE_TTL_SEGUNDOS):
        self._ttl = ttl_segundos
        self._store: dict = {}  # chave -> (ts, dados)

    def obter(self, chave: str, carregar):
        agora = time.monotonic()
        item = self._store.get(chave)
        if item and (agora - item[0]) < self._ttl:
            return item[1]
        dados = carregar()
        self._store[chave] = (agora, dados)
        self._podar(agora)
        return dados

    def _podar(self, agora: float) -> None:
        vencidas = [k for k, (ts, _) in self._store.items() if agora - ts >= self._ttl]
        for k in vencidas:
            del self._store[k]

    def clear(self) -> None:
        self._store.clear()


_cache = _CacheTTL()
_cache_analise = _CacheTTL()
_cache_recompra = _CacheTTL()


def _dados_cacheados(db: Session, f: FiltrosDashboard, *, hoje) -> dict:
    return _cache.obter(f.chave_cache(), lambda: svc.montar_dados(db, f, hoje=hoje))


def _dados_analise_cacheados(db: Session, f: FiltrosDashboard, *, criterio: str, cortes_str: str) -> dict:
    chave = "|".join([f.chave_cache(), criterio, cortes_str])
    return _cache_analise.obter(
        chave, lambda: svc_analise.montar_analise(db, f, criterio=criterio, cortes_str=cortes_str)
    )


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


def _dados_recompra_cacheados(db: Session, *, vendedor, cidade, uf, hoje) -> dict:
    chave = "|".join([vendedor or "", cidade or "", uf or "", hoje.isoformat()])
    return _cache_recompra.obter(
        chave, lambda: svc_recompra.montar_recompra(db, vendedor=vendedor, cidade=cidade, uf=uf, hoje=hoje)
    )


@router.get("/dashboard/recompra", response_class=HTMLResponse)
def dashboard_recompra(
    request: Request,
    current_user: dict = Depends(require_login),
    db: Session = Depends(get_db),
):
    hoje = datetime.now(BRT).date()
    q = dict(request.query_params)
    vendedor = _limpar(q.get("vendedor"))  # strip + vazio->None (mesma norma do dashboard)
    cidade = _limpar(q.get("cidade"))
    uf = _limpar(q.get("uf"))
    faixa = (q.get("faixa") or "").strip()

    dados = _dados_recompra_cacheados(db, vendedor=vendedor, cidade=cidade, uf=uf, hoje=hoje)
    clientes = dados["clientes"]
    if faixa:
        clientes = [c for c in clientes if c["faixa"] == faixa]

    ctx = {
        "request": request,
        "user": current_user,
        # KPIs seguem o mesmo recorte da tabela: com faixa selecionada, os cards
        # refletem só o conjunto filtrado. Sem faixa, equivale a dados["kpis"].
        "kpis": svc_recompra.calcular_kpis(clientes),
        "clientes": clientes,
        "faixas": svc_recompra.FAIXAS,  # apresentação (emoji/label/cor/card) das faixas
    }

    # Troca de filtro é HX-Request e só re-renderiza #recompra-paineis (KPIs + tabela);
    # o formulário de selects não volta, então evitamos os 3 SELECT DISTINCT de opcoes
    # que seriam descartados. Elas só são necessárias no carregamento da página cheia.
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("partials/recompra_paineis.html", ctx)

    ctx["opcoes"] = svc_recompra.opcoes_recompra(db)
    ctx["filtros"] = {"vendedor": vendedor or "", "cidade": cidade or "", "uf": uf or "", "faixa": faixa}
    return templates.TemplateResponse("recompra.html", ctx)
