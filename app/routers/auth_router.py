from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import (
    TOKEN_EXPIRE_HOURS,
    criar_token,
    get_current_user,
    hash_senha,
    require_login_raw,
    verificar_senha,
)
from config import settings
from database import get_db

templates = Jinja2Templates(directory="templates")
router = APIRouter()


@router.get("/login", response_class=HTMLResponse)
def pagina_login(request: Request, user=Depends(get_current_user)):
    if user:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "erro": None})


@router.post("/login")
def fazer_login(
    request: Request,
    email: str = Form(...),
    senha: str = Form(...),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT email, senha_hash, role, ativo, trocar_senha FROM usuario WHERE email = :email"),
        {"email": email.lower().strip()},
    ).fetchone()

    if not row or not row.ativo or not verificar_senha(senha, row.senha_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "erro": "E-mail ou senha inválidos."},
            status_code=401,
        )

    token = criar_token(row.email, row.role)
    destino = "/trocar-senha" if row.trocar_senha else "/"
    response = RedirectResponse(destino, status_code=302)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
        max_age=TOKEN_EXPIRE_HOURS * 3600,
    )
    return response


@router.get("/trocar-senha", response_class=HTMLResponse)
def pagina_trocar_senha(request: Request, user: dict = Depends(require_login_raw)):
    if not user.get("trocar_senha"):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("trocar_senha.html", {
        "request": request,
        "user": user,
        "erro": None,
    })


@router.post("/trocar-senha", response_class=HTMLResponse)
def fazer_trocar_senha(
    request: Request,
    nova_senha: str = Form(...),
    confirmar_senha: str = Form(...),
    user: dict = Depends(require_login_raw),
    db: Session = Depends(get_db),
):
    if nova_senha != confirmar_senha:
        return templates.TemplateResponse("trocar_senha.html", {
            "request": request,
            "user": user,
            "erro": "As senhas não coincidem.",
        })
    if len(nova_senha) < 6:
        return templates.TemplateResponse("trocar_senha.html", {
            "request": request,
            "user": user,
            "erro": "A senha deve ter pelo menos 6 caracteres.",
        })

    db.execute(
        text("UPDATE usuario SET senha_hash = :hash, trocar_senha = false WHERE id = :id"),
        {"hash": hash_senha(nova_senha), "id": user["id"]},
    )
    db.commit()
    return RedirectResponse("/", status_code=302)


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("access_token")
    return response
