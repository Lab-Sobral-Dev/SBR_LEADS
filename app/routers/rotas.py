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
from routers.api import _UFS
from schemas import MapsUrlsRequest, OrdenarRequest, SalvarRotaRequest, UF

_UFS_OPCOES = [UF(sigla=s, nome=n) for s, n in _UFS]

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
        "ufs": _UFS_OPCOES, "municipios": [],
        "rota": None, "trechos": [],
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


@router.get("/rotas/{rota_id}", response_class=HTMLResponse)
def editar(rota_id: int, request: Request, current_user: dict = Depends(require_login),
           db: Session = Depends(get_db)):
    rota = svc.carregar_rota(db, rota_id)
    if rota is None:
        return RedirectResponse(url="/rotas", status_code=302)
    return templates.TemplateResponse("rota_montar.html", {
        "request": request, "user": current_user,
        "vendedores": opcoes_filtro(db).get("vendedores", []),
        "ufs": _UFS_OPCOES, "municipios": svc.municipios_por_uf(db, rota["uf"]),
        "rota": rota, "trechos": svc.montar_urls_google_maps(rota["paradas"]),
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
    if svc.carregar_rota(db, rota_id) is None:
        return JSONResponse({"erro": "Rota não encontrada"}, status_code=404)
    svc.atualizar_rota(db, rota_id, nome=req.nome, paradas=[p.model_dump() for p in req.paradas])
    db.commit()
    return JSONResponse({"id": rota_id})


@router.post("/rotas/{rota_id}/excluir")
def excluir(rota_id: int, current_user: dict = Depends(require_login), db: Session = Depends(get_db)):
    svc.excluir_rota(db, rota_id)
    db.commit()
    return RedirectResponse(url="/rotas", status_code=302)
