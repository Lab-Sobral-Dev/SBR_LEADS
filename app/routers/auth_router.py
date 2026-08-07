from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.orm import Session

from acoplamento import resolver_acoplamento
from auth import (
    ALGORITHM,
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
        secure=settings.session_cookie_secure,
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


# ─────────────────────────────────────────────────────────────────────────────
# Protocolo de Acoplamento (gestao-sbr)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/auth/sso")
def sso_acoplamento(
    token: str = Query(..., description="JWT curto emitido pelo gestao-sbr"),
    db: Session = Depends(get_db),
):
    """Entrada por SSO a partir do gestao-sbr, sem tela de login.

    O casco emite um JWT de 60 segundos assinado com o segredo compartilhado, já
    tendo verificado a permissão de quem clicou. Aqui só validamos a assinatura,
    materializamos a conta local e devolvemos o mesmo cookie de sessão que o
    login normal emite — nada no resto do app precisa saber que a pessoa entrou
    por aqui.

    Segredo ausente devolve 503 em vez de 500: é configuração faltando, não
    defeito, e o login local continua funcionando.
    """
    if not settings.docking_secret:
        raise HTTPException(status_code=503, detail="Acoplamento não configurado neste ambiente.")

    try:
        payload = jwt.decode(token, settings.docking_secret, algorithms=[ALGORITHM])
    except JWTError:
        # Sem detalhe do motivo de propósito: expirado, assinatura inválida e
        # malformado são a mesma coisa para quem está do lado de fora.
        raise HTTPException(status_code=401, detail="Token de acoplamento inválido ou expirado.")

    email = (payload.get("email") or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Token de acoplamento sem e-mail.")

    resultado = resolver_acoplamento(db, email=email, nome=payload.get("nome") or email)

    if resultado.acao == "login":
        # Conta desativada aqui dentro. Cai no login local em vez de entrar: a
        # decisão do admin deste produto vale sobre a permissão do casco.
        return RedirectResponse("/login", status_code=302)

    response = RedirectResponse("/", status_code=302)
    response.set_cookie(
        "access_token",
        criar_token(resultado.email, resultado.role),
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        max_age=TOKEN_EXPIRE_HOURS * 3600,
    )
    return response
