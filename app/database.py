from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def valores_distintos(db: Session, coluna: str, *, origem: str, filtro: str | None = None) -> list[str]:
    """Valores DISTINCT de `coluna`, com TRIM, ignorando vazios/nulos e ordenados.

    Idioma usado pelos selects de filtro dos dashboards. `origem` é a cláusula
    FROM (tabela ou JOIN) e `filtro` um WHERE extra opcional. `coluna`/`origem`/
    `filtro` são montados por chamadores internos (nunca entrada do usuário).
    """
    onde = f"NULLIF(TRIM({coluna}), '') IS NOT NULL"
    if filtro:
        onde = f"{filtro} AND {onde}"
    return db.execute(text(
        f"SELECT DISTINCT TRIM({coluna}) AS x FROM {origem} WHERE {onde} ORDER BY x"
    )).scalars().all()
