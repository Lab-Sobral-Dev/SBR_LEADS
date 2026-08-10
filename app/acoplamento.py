"""Política de provisionamento do Protocolo de Acoplamento (gestao-sbr).

Mantida PURA e separada da rota HTTP para que o contrato seja travado por teste:
o handler só orquestra cookie e redirect. Mesmo desenho já usado no SBR-KPIs
(`src/lib/acoplamento.ts`), de propósito — dois produtos acoplados que resolvem
identidade de formas diferentes viram duas fontes de bug diferentes.

Quem autoriza a entrada é o gestao-sbr, que só emite token para quem tem a
permissão do módulo. Este app confia no token e apenas materializa a conta local.
"""

from dataclasses import dataclass
from typing import Literal, Optional
import secrets

from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import hash_senha

# Papel dado a quem entra por acoplamento. Nunca 'admin': a administração do
# SBR_LEADS é decisão local, não herda da permissão do casco.
ROLE_PADRAO = "user"


@dataclass(frozen=True)
class ResultadoAcoplamento:
    """`acao` diz o que o handler faz: abrir sessão ou mandar para o login local."""
    acao: Literal["sessao", "login"]
    email: Optional[str] = None
    role: Optional[str] = None


def resolver_acoplamento(db: Session, email: str, nome: str) -> ResultadoAcoplamento:
    """Decide o destino de quem chega via SSO de acoplamento.

    - existe e ativo        -> sessão (reaproveita a conta local)
    - existe mas desativado -> login local (respeita bloqueio explícito do admin;
                               NÃO reativa, porque desativar aqui é decisão de
                               quem administra este produto)
    - não existe            -> cria e abre sessão
    """
    email = email.lower().strip()

    row = db.execute(
        text("SELECT email, role, ativo FROM usuario WHERE email = :email"),
        {"email": email},
    ).fetchone()

    if row is not None:
        if not row.ativo:
            return ResultadoAcoplamento(acao="login")
        return ResultadoAcoplamento(acao="sessao", email=row.email, role=row.role)

    # Senha aleatória e descartada: a conta só entra por SSO. Não deixamos o campo
    # nulo porque `verificar_senha` receberia None e o login local quebraria em vez
    # de simplesmente recusar.
    db.execute(
        text(
            "INSERT INTO usuario (email, nome, senha_hash, role, trocar_senha) "
            "VALUES (:email, :nome, :hash, :role, false)"
        ),
        {
            "email": email,
            "nome": (nome or email).strip(),
            "hash": hash_senha(secrets.token_urlsafe(48)),
            "role": ROLE_PADRAO,
        },
    )
    db.commit()
    return ResultadoAcoplamento(acao="sessao", email=email, role=ROLE_PADRAO)
