"""
Sincronização da base de clientes do Pedido Mobile.

A API expõe `GET /clienteintegracao/versao?versao=N&page=P` com versionamento incremental:
- versão 0 retorna todos os clientes (carga inicial)
- versões > 0 retornam apenas clientes alterados desde aquele número

Apenas operações de leitura (GET) são executadas — nunca POST/PUT/DELETE.
"""
import logging
import re
import time
from datetime import datetime, timezone

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import BRT, settings

logger = logging.getLogger(__name__)

ENDPOINT         = "/clienteintegracao/versao"
ENDPOINT_PEDIDOS = "/pedidointegracao/versao"
TIMEOUT_SEGUNDOS = 60
MAX_TENTATIVAS = 3


class SyncError(Exception):
    pass


def _credenciais_ou_erro() -> tuple[str, str]:
    if not settings.pedido_mobile_user or not settings.pedido_mobile_password:
        raise SyncError(
            "Credenciais do Pedido Mobile não configuradas. "
            "Defina PEDIDO_MOBILE_USER e PEDIDO_MOBILE_PASSWORD no .env."
        )
    return settings.pedido_mobile_user, settings.pedido_mobile_password


def _normalizar_documento(doc: str | None) -> str:
    return re.sub(r"\D", "", doc or "")


def _ultima_versao(db: Session) -> int:
    # Considera apenas syncs CONCLUÍDOS sem erro — evita ler o registro
    # da execução em andamento (que tem concluida_em IS NULL).
    return db.execute(
        text(
            "SELECT COALESCE(MAX(ultima_versao), 0) "
            "FROM pedido_mobile_sync "
            "WHERE concluida_em IS NOT NULL AND erro IS NULL"
        )
    ).scalar() or 0


def _sync_em_andamento(db: Session) -> bool:
    return bool(db.execute(
        text("SELECT 1 FROM pedido_mobile_sync WHERE concluida_em IS NULL LIMIT 1")
    ).scalar())


def sync_em_andamento(db: Session) -> bool:
    return _sync_em_andamento(db)


_RESPOSTA_VAZIA: dict = {"dados": [], "totalPaginas": 0, "totalRegistros": 0}


def _buscar_pagina(versao: int, page: int, endpoint: str = ENDPOINT) -> dict:
    user, pwd = _credenciais_ou_erro()
    url = settings.pedido_mobile_base_url.rstrip("/") + endpoint

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            r = requests.get(
                url,
                params={"versao": versao, "page": page},
                auth=(user, pwd),
                timeout=TIMEOUT_SEGUNDOS,
                headers={"Accept": "application/json"},
            )
            # 404 → sem alterações desde essa versão (sucesso, 0 registros)
            if r.status_code == 404:
                logger.info("Sem alterações desde a versão %d (HTTP 404)", versao)
                return {**_RESPOSTA_VAZIA, "ultimaVersao": versao}
            # 400 → versão inválida ou fora do range da API; sinaliza para o chamador
            if r.status_code == 400:
                raise SyncError(f"VERSAO_INVALIDA:{versao}")
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.warning(
                "Falha ao buscar página %d (tentativa %d/%d): %s",
                page, tentativa, MAX_TENTATIVAS, e,
            )
            if tentativa == MAX_TENTATIVAS:
                raise SyncError(f"Falha ao buscar página {page}: {e}") from e
            time.sleep(2 ** tentativa)
    raise SyncError("Loop de retry encerrado sem sucesso")


_UPSERT_SQL = text("""
    INSERT INTO cliente_pedido_mobile
        (documento, tipo_documento, razao_social, nome_fantasia,
         vendedor, inativo, municipio, uf, atualizado_em)
    VALUES
        (:documento, :tipo_documento, :razao_social, :nome_fantasia,
         :vendedor, :inativo, :municipio, :uf, NOW())
    ON CONFLICT (documento) DO UPDATE SET
        tipo_documento = EXCLUDED.tipo_documento,
        razao_social   = EXCLUDED.razao_social,
        nome_fantasia  = EXCLUDED.nome_fantasia,
        vendedor       = EXCLUDED.vendedor,
        inativo        = EXCLUDED.inativo,
        municipio      = EXCLUDED.municipio,
        uf             = EXCLUDED.uf,
        atualizado_em  = NOW()
    RETURNING (xmax = 0) AS inserido
""")


def _versao_pedidos(db: Session) -> int:
    return db.execute(
        text(
            "SELECT COALESCE(valor::int, 0) FROM pedido_mobile_config "
            "WHERE chave = 'versao_pedidos'"
        )
    ).scalar() or 0


def _salvar_versao_pedidos(db: Session, versao: int) -> None:
    db.execute(
        text("""
            INSERT INTO pedido_mobile_config (chave, valor) VALUES ('versao_pedidos', :v)
            ON CONFLICT (chave) DO UPDATE SET valor = :v
        """),
        {"v": str(versao)},
    )


_UPDATE_ULTIMA_COMPRA = text("""
    UPDATE cliente_pedido_mobile
       SET ultima_compra_em = :data
     WHERE documento = :documento
       AND (ultima_compra_em IS NULL OR ultima_compra_em < :data)
""")


def _sincronizar_pedidos(db: Session) -> None:
    """Percorre pedidointegracao/versao e atualiza ultima_compra_em por cliente.
    Usa versionamento incremental — apenas pedidos alterados desde o último sync.
    Se a API rejeitar a versão armazenada (400), reinicia do zero automaticamente.
    """
    versao_inicial = _versao_pedidos(db)
    nova_versao = versao_inicial
    page = 1
    resetado = False

    while True:
        try:
            data = _buscar_pagina(versao_inicial, page, ENDPOINT_PEDIDOS)
        except SyncError as e:
            if "VERSAO_INVALIDA" in str(e) and not resetado:
                logger.warning(
                    "Versão %d rejeitada pela API de pedidos (400). "
                    "Reiniciando sync completo desde versão 0.",
                    versao_inicial,
                )
                versao_inicial = 0
                nova_versao = 0
                page = 1
                resetado = True
                _salvar_versao_pedidos(db, 0)
                db.commit()
                data = _buscar_pagina(versao_inicial, page, ENDPOINT_PEDIDOS)
            else:
                raise
        nova_versao = max(nova_versao, data.get("ultimaVersao") or 0)
        total_paginas = data.get("totalPaginas") or 0
        pedidos = data.get("dados") or []

        for pedido in pedidos:
            doc = _normalizar_documento(pedido.get("clienteDocumento"))
            emissao_str = pedido.get("pedidoEmissao")
            if not doc or not emissao_str:
                continue
            try:
                data_compra = datetime.strptime(emissao_str, "%d/%m/%Y").date()
            except ValueError:
                continue
            db.execute(_UPDATE_ULTIMA_COMPRA, {"documento": doc, "data": data_compra})

        db.commit()
        logger.info("Pedidos: página %d/%d processada", page, total_paginas)

        if page >= total_paginas:
            break
        page += 1

    _salvar_versao_pedidos(db, nova_versao)
    db.commit()


def sincronizar(db: Session) -> dict:
    """Executa um ciclo de sincronização. Retorna estatísticas."""
    _credenciais_ou_erro()
    if _sync_em_andamento(db):
        raise SyncError(
            "Já existe uma sincronização em andamento. Aguarde a conclusão "
            "antes de iniciar outra."
        )
    versao_inicial = _ultima_versao(db)
    logger.info("Iniciando sync Pedido Mobile (versão local: %d)", versao_inicial)

    inicio_sync = db.execute(
        text(
            "INSERT INTO pedido_mobile_sync (ultima_versao) "
            "VALUES (:v) RETURNING id"
        ),
        {"v": versao_inicial},
    ).scalar()
    db.commit()

    novos = atualizados = 0
    nova_versao = versao_inicial
    paginas_processadas = 0
    total = 0

    try:
        page = 1
        while True:
            data = _buscar_pagina(versao_inicial, page)
            total = data.get("totalRegistros") or total
            total_paginas = data.get("totalPaginas") or 0
            nova_versao = max(nova_versao, data.get("ultimaVersao") or 0)
            registros = data.get("dados") or []

            for cliente in registros:
                documento = _normalizar_documento(cliente.get("documento"))
                if not documento:
                    continue
                inserido = db.execute(_UPSERT_SQL, {
                    "documento":      documento,
                    "tipo_documento": (cliente.get("tipoDocumento") or "")[:4] or None,
                    "razao_social":   (cliente.get("razaoSocial") or "")[:200] or None,
                    "nome_fantasia":  (cliente.get("nomeFantasia") or "")[:200] or None,
                    "vendedor":       (cliente.get("vendedor") or "")[:100] or None,
                    "inativo":        bool(cliente.get("inativo")),
                    "municipio":      (cliente.get("municipio") or "")[:100] or None,
                    "uf":             (cliente.get("estado") or "")[:2] or None,
                }).scalar()
                if inserido:
                    novos += 1
                else:
                    atualizados += 1
            db.commit()

            paginas_processadas = page
            logger.info(
                "Página %d/%d processada (novos=%d, atualizados=%d)",
                page, total_paginas, novos, atualizados,
            )
            if page >= total_paginas:
                break
            page += 1

    except Exception as e:
        db.rollback()
        db.execute(
            text(
                "UPDATE pedido_mobile_sync "
                "SET erro = :erro, concluida_em = NOW() WHERE id = :id"
            ),
            {"erro": str(e)[:500], "id": inicio_sync},
        )
        db.commit()
        raise

    db.execute(
        text("""
            UPDATE pedido_mobile_sync SET
                concluida_em   = NOW(),
                ultima_versao  = :v,
                total_clientes = :total,
                novos          = :novos,
                atualizados    = :atualizados,
                paginas        = :paginas
            WHERE id = :id
        """),
        {
            "id": inicio_sync,
            "v": nova_versao,
            "total": total,
            "novos": novos,
            "atualizados": atualizados,
            "paginas": paginas_processadas,
        },
    )
    db.commit()

    logger.info("Sincronizando datas de última compra via pedidointegracao...")
    _sincronizar_pedidos(db)

    return {
        "total_registros": total,
        "novos": novos,
        "atualizados": atualizados,
        "paginas": paginas_processadas,
        "versao_inicial": versao_inicial,
        "nova_versao": nova_versao,
    }


def total_clientes(db: Session) -> int:
    return db.execute(text("SELECT COUNT(*) FROM cliente_pedido_mobile")).scalar() or 0


def ultima_sync(db: Session) -> dict | None:
    row = db.execute(
        text("""
            SELECT concluida_em, ultima_versao, total_clientes, novos, atualizados, erro
            FROM pedido_mobile_sync
            WHERE concluida_em IS NOT NULL
            ORDER BY concluida_em DESC
            LIMIT 1
        """)
    ).first()
    if not row:
        return None
    concluida_em = row.concluida_em
    if concluida_em:
        if concluida_em.tzinfo is None:
            concluida_em = concluida_em.replace(tzinfo=timezone.utc)
        concluida_em = concluida_em.astimezone(BRT)
    return {
        "concluida_em":   concluida_em,
        "ultima_versao":  row.ultima_versao,
        "total_clientes": row.total_clientes,
        "novos":          row.novos,
        "atualizados":    row.atualizados,
        "erro":           row.erro,
    }
