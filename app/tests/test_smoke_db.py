from sqlalchemy import text


def test_fixture_db_conecta(db):
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_tabelas_existem(db):
    for t in ("cliente_pedido_mobile", "pedido_mobile_pedido", "pedido_mobile_item"):
        db.execute(text(f"SELECT COUNT(*) FROM {t}"))
