from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import hash_senha, require_admin
from config import BRT
from database import get_db

templates = Jinja2Templates(directory="templates")
router = APIRouter(prefix="/admin")


def _listar_usuarios(db: Session) -> list:
    rows = db.execute(
        text("SELECT id, email, nome, role, ativo, criado_em FROM usuario ORDER BY criado_em")
    ).fetchall()
    return [
        {
            "id": str(r.id),
            "email": r.email,
            "nome": r.nome,
            "role": r.role,
            "ativo": r.ativo,
            "criado_em": r.criado_em.astimezone(BRT).strftime("%d/%m/%Y") if r.criado_em and r.criado_em.tzinfo else (r.criado_em.strftime("%d/%m/%Y") if r.criado_em else "—"),
        }
        for r in rows
    ]


@router.get("/usuarios", response_class=HTMLResponse)
def pagina_usuarios(
    request: Request,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse("admin/usuarios.html", {
        "request": request,
        "user": current_user,
        "usuarios": _listar_usuarios(db),
        "mensagem": None,
        "erro": None,
    })


@router.post("/usuarios", response_class=HTMLResponse)
def criar_usuario(
    request: Request,
    nome: str = Form(...),
    email: str = Form(...),
    senha: str = Form(...),
    role: str = Form(...),
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if role not in ("admin", "user"):
        return templates.TemplateResponse("admin/usuarios.html", {
            "request": request,
            "user": current_user,
            "usuarios": _listar_usuarios(db),
            "erro": "Role inválido. Use 'admin' ou 'user'.",
            "mensagem": None,
        })

    email = email.lower().strip()
    existente = db.execute(
        text("SELECT id FROM usuario WHERE email = :email"), {"email": email}
    ).fetchone()

    if existente:
        return templates.TemplateResponse("admin/usuarios.html", {
            "request": request,
            "user": current_user,
            "usuarios": _listar_usuarios(db),
            "erro": f"E-mail {email} já cadastrado.",
            "mensagem": None,
        })

    db.execute(
        text("""
            INSERT INTO usuario (email, nome, senha_hash, role)
            VALUES (:email, :nome, :hash, :role)
        """),
        {"email": email, "nome": nome.strip(), "hash": hash_senha(senha), "role": role},
    )
    db.commit()

    return templates.TemplateResponse("admin/usuarios.html", {
        "request": request,
        "user": current_user,
        "usuarios": _listar_usuarios(db),
        "mensagem": f"Usuário {nome.strip()} criado com sucesso.",
        "erro": None,
    })


@router.post("/usuarios/{user_id}/toggle", response_class=HTMLResponse)
def toggle_usuario(
    request: Request,
    user_id: str,
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT id, ativo, email FROM usuario WHERE id = :id"), {"id": user_id}
    ).fetchone()

    if not row:
        return templates.TemplateResponse("admin/usuarios.html", {
            "request": request,
            "user": current_user,
            "usuarios": _listar_usuarios(db),
            "erro": "Usuário não encontrado.",
            "mensagem": None,
        })

    if row.email == current_user["email"]:
        return templates.TemplateResponse("admin/usuarios.html", {
            "request": request,
            "user": current_user,
            "usuarios": _listar_usuarios(db),
            "erro": "Não é possível desativar seu próprio usuário.",
            "mensagem": None,
        })

    novo_status = not row.ativo
    db.execute(
        text("UPDATE usuario SET ativo = :ativo WHERE id = :id"),
        {"ativo": novo_status, "id": user_id},
    )
    db.commit()

    acao = "ativado" if novo_status else "desativado"
    return templates.TemplateResponse("admin/usuarios.html", {
        "request": request,
        "user": current_user,
        "usuarios": _listar_usuarios(db),
        "mensagem": f"Usuário {acao} com sucesso.",
        "erro": None,
    })


@router.post("/usuarios/{user_id}/senha", response_class=HTMLResponse)
def resetar_senha(
    request: Request,
    user_id: str,
    nova_senha: str = Form(...),
    current_user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if len(nova_senha) < 6:
        return templates.TemplateResponse("admin/usuarios.html", {
            "request": request,
            "user": current_user,
            "usuarios": _listar_usuarios(db),
            "erro": "A senha deve ter pelo menos 6 caracteres.",
            "mensagem": None,
        })

    db.execute(
        text("UPDATE usuario SET senha_hash = :hash, trocar_senha = true WHERE id = :id"),
        {"hash": hash_senha(nova_senha), "id": user_id},
    )
    db.commit()

    return templates.TemplateResponse("admin/usuarios.html", {
        "request": request,
        "user": current_user,
        "usuarios": _listar_usuarios(db),
        "mensagem": "Senha alterada com sucesso. O usuário deverá trocá-la no próximo acesso.",
        "erro": None,
    })
