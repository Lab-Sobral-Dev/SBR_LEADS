from datetime import date, timedelta

import recompra_service as svc
from sqlalchemy import text


def _datas(inicio: date, *intervalos: int) -> list[date]:
    """Constrói datas de compra a partir de um início e dos intervalos entre elas."""
    datas = [inicio]
    for d in intervalos:
        datas.append(datas[-1] + timedelta(days=d))
    return datas


# ---- mediana ----

def test_mediana_impar():
    assert svc._mediana([10, 30, 20]) == 20

def test_mediana_par_media_dos_centrais():
    assert svc._mediana([10, 20, 30, 40]) == 25

def test_mediana_vazia_zero():
    assert svc._mediana([]) == 0.0


# ---- percentil (interpolação linear) ----

def test_percentil_p90_interpola():
    # [20,30,40], p=0.9 -> rank=1.8 -> 30 + 0.8*(40-30) = 38
    assert svc._percentil([20, 30, 40], 0.9) == 38.0

def test_percentil_um_elemento():
    assert svc._percentil([25], 0.9) == 25.0

def test_percentil_vazio_zero():
    assert svc._percentil([], 0.9) == 0.0


# ---- classificar_recompra ----

def test_sem_padrao_com_menos_de_3_compras():
    for ints in ([], [30]):  # 1 e 2 compras
        datas = _datas(date(2026, 1, 1), *ints)
        r = svc.classificar_recompra(datas, date(2026, 3, 1), receita_total=200)
        assert r["faixa"] == "sem_padrao"
        assert r["indice"] is None
        assert r["mediana"] is None
        assert r["n_compras"] == len(datas)
        assert r["ultima_compra"] == datas[-1]
        assert r["ticket_medio"] == round(200 / len(datas), 2)


def test_faixa_em_dia_no_limite_da_mediana():
    datas = _datas(date(2026, 1, 1), 20, 30, 40)
    ultima = datas[-1]
    r = svc.classificar_recompra(datas, ultima + timedelta(days=30), receita_total=400)
    assert r["mediana"] == 30.0
    assert r["maior_intervalo_normal"] == 38.0
    assert r["dias_sem_comprar"] == 30
    assert r["faixa"] == "em_dia"        # 30 <= mediana(30)
    assert r["indice"] == 1.0


def test_faixa_atrasando_entre_mediana_e_p90():
    datas = _datas(date(2026, 1, 1), 20, 30, 40)
    ultima = datas[-1]
    r = svc.classificar_recompra(datas, ultima + timedelta(days=35), receita_total=400)
    assert r["faixa"] == "atrasando"     # 30 < 35 <= 38


def test_faixa_atrasando_no_limite_p90():
    datas = _datas(date(2026, 1, 1), 20, 30, 40)
    ultima = datas[-1]
    r = svc.classificar_recompra(datas, ultima + timedelta(days=38), receita_total=400)
    assert r["faixa"] == "atrasando"     # 38 <= p90(38)


def test_faixa_atrasado_acima_do_p90():
    datas = _datas(date(2026, 1, 1), 20, 30, 40)
    ultima = datas[-1]
    r = svc.classificar_recompra(datas, ultima + timedelta(days=39), receita_total=400)
    assert r["faixa"] == "atrasado"      # 39 > p90(38)
    assert r["indice"] == round(39 / 30, 2)


def test_p90_robusto_a_outlier():
    datas = _datas(date(2026, 1, 1), 30, 30, 30, 200)
    ultima = datas[-1]
    r = svc.classificar_recompra(datas, ultima + timedelta(days=60), receita_total=500)
    assert r["mediana"] == 30.0
    assert r["maior_intervalo_normal"] < 200
    assert r["faixa"] in ("atrasando", "atrasado")


def test_ticket_medio():
    datas = _datas(date(2026, 1, 1), 30, 30)  # 3 compras
    r = svc.classificar_recompra(datas, datas[-1] + timedelta(days=10), receita_total=900)
    assert r["ticket_medio"] == 300.0


def test_pedidos_no_mesmo_dia_contam_como_uma_compra():
    # 3 "pedidos" em apenas 2 dias distintos -> 2 compras -> sem padrão (< 3)
    d = date(2026, 1, 1)
    r = svc.classificar_recompra([d, d, d + timedelta(days=30)], date(2026, 3, 1), receita_total=300)
    assert r["n_compras"] == 2
    assert r["faixa"] == "sem_padrao"


def test_dedup_dias_distintos_calcula_ritmo():
    # 4 datas, mas 2 são no mesmo dia -> 3 dias distintos -> ritmo calculado sobre [30, 30]
    base = date(2026, 1, 1)
    datas = [base, base, base + timedelta(days=30), base + timedelta(days=60)]
    r = svc.classificar_recompra(datas, base + timedelta(days=60 + 10), receita_total=900)
    assert r["n_compras"] == 3            # 3 dias distintos (não 4 pedidos)
    assert r["mediana"] == 30.0
    assert r["ticket_medio"] == 300.0     # 900 / 3 ocasiões


def test_intervalos_minimos_de_um_dia_nao_quebram_indice():
    # Menor mediana possível: datas distintas coladas (intervalos de 1 dia).
    # Fixa o invariante de que a divisão do índice nunca é por zero.
    base = date(2026, 1, 1)
    datas = [base, base + timedelta(days=1), base + timedelta(days=2)]  # intervalos [1, 1]
    r = svc.classificar_recompra(datas, base + timedelta(days=5), receita_total=300)
    assert r["mediana"] == 1.0
    assert r["indice"] == 3.0  # 3 dias sem comprar / mediana 1


def test_sem_compras_retorna_sem_padrao():
    r = svc.classificar_recompra([], date(2026, 3, 1))
    assert r["faixa"] == "sem_padrao"
    assert r["n_compras"] == 0
    assert r["ultima_compra"] is None
    assert r["dias_sem_comprar"] is None
    assert r["ticket_medio"] == 0.0


# ---- helpers de banco ----


def _cli(db, doc, vendedor="Joao", uf="PI", municipio="Floriano"):
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, razao_social, nome_fantasia, vendedor, inativo, municipio, uf)
        VALUES (:d, :rs, :nf, :v, FALSE, :m, :uf)
        ON CONFLICT (documento) DO UPDATE SET vendedor = EXCLUDED.vendedor
    """), {"d": doc, "rs": f"Razao {doc}", "nf": f"Farmacia {doc}", "v": vendedor, "m": municipio, "uf": uf})


_pedido_seq = [0]

def _pedido(db, doc, emissao, *, total=100.0, orcamento=False, situacao="Enviado"):
    _pedido_seq[0] += 1
    db.execute(text("""
        INSERT INTO pedido_mobile_pedido
            (pedido_numero, cliente_documento, vendedor, emissao, situacao, orcamento, total_liquido)
        VALUES (:n, :d, 'Joao', :e, :s, :o, :t)
    """), {"n": _pedido_seq[0], "d": doc, "e": emissao, "s": situacao, "o": orcamento, "t": total})


def test_montar_recompra_classifica_e_conta(db):
    # Cliente A: 4 compras regulares (~30d), última há 70d -> atrasado.
    _cli(db, "A")
    base = date(2026, 1, 1)
    for off in (0, 30, 60, 90):
        _pedido(db, "A", base + timedelta(days=off), total=200)
    hoje = base + timedelta(days=90 + 70)  # 70 dias após a última
    dados = svc.montar_recompra(db, vendedor="Joao", cidade=None, uf=None, hoje=hoje)
    a = next(c for c in dados["clientes"] if c["documento"] == "A")
    assert a["faixa"] == "atrasado"
    assert a["n_compras"] == 4
    assert dados["kpis"]["atrasado"] >= 1
    assert dados["kpis"]["receita_atrasados"] >= 200


def test_montar_recompra_ignora_orcamento_e_cancelado(db):
    _cli(db, "B")
    base = date(2026, 1, 1)
    _pedido(db, "B", base, total=100)
    _pedido(db, "B", base + timedelta(days=30), total=100)
    _pedido(db, "B", base + timedelta(days=60), total=100)
    _pedido(db, "B", base + timedelta(days=70), total=100, orcamento=True)
    _pedido(db, "B", base + timedelta(days=75), total=100, situacao="Cancelado")
    dados = svc.montar_recompra(db, vendedor="Joao", cidade=None, uf=None, hoje=base + timedelta(days=80))
    b = next(c for c in dados["clientes"] if c["documento"] == "B")
    assert b["n_compras"] == 3   # só os efetivos


def test_montar_recompra_cancelado_e_insensivel_a_caixa(db):
    # A origem grava a situação crua; 'CANCELADO'/' Cancelado ' devem ser ignorados
    # igual ao resto do cockpit (mesma régua de dashboard_service._NAO_CANCELADO).
    _cli(db, "B2")
    base = date(2026, 1, 1)
    _pedido(db, "B2", base, total=100)
    _pedido(db, "B2", base + timedelta(days=30), total=100)
    _pedido(db, "B2", base + timedelta(days=60), total=100)
    _pedido(db, "B2", base + timedelta(days=70), total=100, situacao="CANCELADO")
    _pedido(db, "B2", base + timedelta(days=75), total=100, situacao=" Cancelado ")
    dados = svc.montar_recompra(db, vendedor="Joao", cidade=None, uf=None, hoje=base + timedelta(days=80))
    b = next(c for c in dados["clientes"] if c["documento"] == "B2")
    assert b["n_compras"] == 3   # variações de caixa/espaço não contam como compra


def test_montar_recompra_sem_padrao_vai_para_o_fim(db):
    _cli(db, "C")  # 1 compra só -> sem padrão
    _pedido(db, "C", date(2026, 1, 1), total=50)
    _cli(db, "D")  # 3 compras, atrasado
    base = date(2026, 1, 1)
    for off in (0, 30, 60):
        _pedido(db, "D", base + timedelta(days=off), total=100)
    dados = svc.montar_recompra(db, vendedor="Joao", cidade=None, uf=None, hoje=base + timedelta(days=200))
    docs = [c["documento"] for c in dados["clientes"]]
    assert docs.index("C") > docs.index("D")
    assert dados["kpis"]["sem_padrao"] >= 1


def test_montar_recompra_filtra_por_vendedor(db):
    _cli(db, "E", vendedor="Maria")
    _pedido(db, "E", date(2026, 1, 1))
    dados = svc.montar_recompra(db, vendedor="Joao", cidade=None, uf=None, hoje=date(2026, 2, 1))
    assert all(c["documento"] != "E" for c in dados["clientes"])


def test_opcoes_recompra_lista_vendedores_e_locais(db):
    _cli(db, "F", vendedor="Joao", uf="PI", municipio="Floriano")
    _pedido(db, "F", date(2026, 1, 1))  # precisa de compra efetiva p/ entrar no universo
    out = svc.opcoes_recompra(db)
    assert "Joao" in out["vendedores"]
    assert "PI" in out["ufs"]
    assert "Floriano" in out["cidades"]


def test_opcoes_recompra_escopa_ao_universo_com_compra(db):
    # Cliente sem compra efetiva não deve aparecer nas opções (evita escolha "morta").
    _cli(db, "SEMPED", vendedor="Fantasma", uf="AC", municipio="Rio Branco")
    _cli(db, "INAT", vendedor="Inativo", uf="AM", municipio="Manaus")
    db.execute(text("UPDATE cliente_pedido_mobile SET inativo = TRUE WHERE documento = 'INAT'"))
    _pedido(db, "INAT", date(2026, 1, 1))       # tem pedido, mas está inativo
    out = svc.opcoes_recompra(db)
    assert "Fantasma" not in out["vendedores"]  # sem pedido efetivo
    assert "AC" not in out["ufs"]
    assert "Inativo" not in out["vendedores"]   # inativo
    assert "AM" not in out["ufs"]


def test_montar_recompra_filtro_ignora_espacos_no_dado(db):
    # Vendedor gravado com espaço à toa; a opção do select vem TRIM-ada ('Espaco').
    _cli(db, "H", vendedor="Espaco ", uf="PI", municipio="Floriano")
    _pedido(db, "H", date(2026, 1, 1))
    out = svc.opcoes_recompra(db)
    assert "Espaco" in out["vendedores"]         # opção sem o espaço
    dados = svc.montar_recompra(db, vendedor="Espaco", cidade=None, uf=None, hoje=date(2026, 2, 1))
    assert any(c["documento"] == "H" for c in dados["clientes"])  # filtro casa mesmo assim


def test_montar_recompra_filtra_por_uf(db):
    _cli(db, "G", vendedor="Joao", uf="SP", municipio="Sao Paulo")
    _pedido(db, "G", date(2026, 1, 1))
    dados = svc.montar_recompra(db, vendedor=None, cidade=None, uf="PI", hoje=date(2026, 2, 1))
    assert all(c["documento"] != "G" for c in dados["clientes"])


# ---- calcular_kpis (KPIs seguem o recorte da lista dada) ----


def test_calcular_kpis_conta_por_faixa():
    clientes = [
        {"faixa": "em_dia", "ticket_medio": 100},
        {"faixa": "atrasado", "ticket_medio": 200},
        {"faixa": "atrasado", "ticket_medio": 50},
        {"faixa": "sem_padrao", "ticket_medio": 10},
    ]
    kpis = svc.calcular_kpis(clientes)
    assert kpis["em_dia"] == 1
    assert kpis["atrasado"] == 2
    assert kpis["sem_padrao"] == 1
    assert kpis["atrasando"] == 0
    assert kpis["receita_atrasados"] == 250  # só ticket dos atrasados


def test_calcular_kpis_lista_filtrada_zera_outras_faixas():
    # Ao filtrar a tabela por 'atrasado', os KPIs refletem só esse conjunto.
    so_atrasados = [{"faixa": "atrasado", "ticket_medio": 300}]
    kpis = svc.calcular_kpis(so_atrasados)
    assert kpis == {"em_dia": 0, "atrasando": 0, "atrasado": 1,
                    "sem_padrao": 0, "receita_atrasados": 300}
