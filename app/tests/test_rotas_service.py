import math

import rotas_service as svc


# ---- haversine ----

def test_haversine_zero_quando_mesmo_ponto():
    assert svc.haversine_km(-9.0, -45.0, -9.0, -45.0) == 0.0


def test_haversine_distancia_conhecida_aproximada():
    # ~111 km por grau de latitude no equador (tolerância ampla).
    d = svc.haversine_km(0.0, 0.0, 1.0, 0.0)
    assert 110 < d < 112


# ---- ordenação vizinho mais próximo ----

def _p(doc, lat, lng):
    return {"documento": doc, "lat": lat, "lng": lng}


def test_ordenar_comeca_na_partida():
    paradas = [_p("A", 0.0, 0.0), _p("B", 0.0, 5.0), _p("C", 0.0, 1.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=0)
    assert [p["documento"] for p in saida] == ["A", "C", "B"]


def test_ordenar_partida_no_meio():
    paradas = [_p("A", 0.0, 0.0), _p("B", 0.0, 5.0), _p("C", 0.0, 6.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=1)
    # Começa em B(5); mais próximo é C(6), depois A(0).
    assert [p["documento"] for p in saida] == ["B", "C", "A"]


def test_ordenar_paradas_sem_coords_vao_para_o_fim():
    paradas = [_p("A", 0.0, 0.0), {"documento": "X", "lat": None, "lng": None}, _p("B", 0.0, 1.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=0)
    assert [p["documento"] for p in saida] == ["A", "B", "X"]


def test_ordenar_listas_pequenas_nao_quebram():
    assert svc.ordenar_vizinho_mais_proximo([], partida_idx=0) == []
    um = [_p("A", 1.0, 1.0)]
    assert svc.ordenar_vizinho_mais_proximo(um, partida_idx=0) == um


def test_ordenar_partida_idx_invalido_usa_zero():
    paradas = [_p("A", 0.0, 0.0), _p("B", 0.0, 1.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=99)
    assert saida[0]["documento"] == "A"


def test_ordenar_partida_sem_coords_usa_primeiro_com_coords():
    paradas = [{"documento": "X", "lat": None, "lng": None}, _p("A", 0.0, 0.0), _p("B", 0.0, 1.0)]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=0)
    assert saida[0]["documento"] == "A"
    assert saida[-1]["documento"] == "X"


def test_ordenar_todas_sem_coords_retorna_na_ordem_original():
    paradas = [{"documento": "X", "lat": None, "lng": None},
               {"documento": "Y", "lat": None, "lng": None}]
    saida = svc.ordenar_vizinho_mais_proximo(paradas, partida_idx=0)
    assert [p["documento"] for p in saida] == ["X", "Y"]


# ---- URLs do Google Maps ----

def test_maps_um_trecho_ate_10_paradas():
    paradas = [_p(str(i), 0.0, float(i)) for i in range(3)]
    urls = svc.montar_urls_google_maps(paradas)
    assert len(urls) == 1
    assert urls[0].startswith("https://www.google.com/maps/dir/?api=1")
    assert "origin=0.0%2C0.0" in urls[0]
    assert "destination=0.0%2C2.0" in urls[0]
    assert "travelmode=driving" in urls[0]


def test_maps_quebra_em_trechos_com_fronteira_compartilhada():
    paradas = [_p(str(i), 0.0, float(i)) for i in range(14)]  # 14 paradas, max 10
    urls = svc.montar_urls_google_maps(paradas, max_por_trecho=10)
    assert len(urls) == 2
    # Trecho 1: paradas 0..9 (origin 0, destination 9).
    assert "origin=0.0%2C0.0" in urls[0]
    assert "destination=0.0%2C9.0" in urls[0]
    # Trecho 2 começa onde o 1 terminou: parada 9 (origin), 13 (destination).
    assert "origin=0.0%2C9.0" in urls[1]
    assert "destination=0.0%2C13.0" in urls[1]


def test_maps_ignora_paradas_sem_coords():
    paradas = [_p("A", 0.0, 0.0), {"documento": "X", "lat": None, "lng": None}, _p("B", 0.0, 1.0)]
    urls = svc.montar_urls_google_maps(paradas)
    assert len(urls) == 1
    assert "origin=0.0%2C0.0" in urls[0]
    assert "destination=0.0%2C1.0" in urls[0]


def test_maps_lista_vazia_ou_um_ponto():
    assert svc.montar_urls_google_maps([]) == []
    assert svc.montar_urls_google_maps([_p("A", 0.0, 0.0)]) == []


# ---- helpers de banco ----

from datetime import date

from sqlalchemy import text


def _seed_estab(db, *, doc, cnpj=("11111111", "0001", "11"), cnae="4771701",
                municipio="2603900", uf="PE", cep="55000000", nome="Farmácia X"):
    db.execute(text("""
        INSERT INTO empresa (cnpj_basico, razao_social) VALUES (:b, :rs)
        ON CONFLICT DO NOTHING
    """), {"b": cnpj[0], "rs": nome})
    db.execute(text("""
        INSERT INTO municipio (codigo, descricao) VALUES (:c, 'Floriano')
        ON CONFLICT DO NOTHING
    """), {"c": municipio})
    db.execute(text("""
        INSERT INTO estabelecimento
            (cnpj_basico, cnpj_ordem, cnpj_dv, nome_fantasia, cnae_fiscal_principal,
             situacao_cadastral, cep, logradouro, numero, municipio, uf)
        VALUES (:b, :o, :d, :nf, :cnae, '02', :cep, 'Rua A', '10', :mun, :uf)
    """), {"b": cnpj[0], "o": cnpj[1], "d": cnpj[2], "nf": nome, "cnae": cnae,
           "cep": cep, "mun": municipio, "uf": uf})


def test_candidatos_traz_cliente_do_vendedor_e_prospecto(db):
    # Cliente do João: basico "11111111" + ordem "0001" + dv "1" → documento "111111110001 1".
    _seed_estab(db, doc="cli", cnpj=("11111111", "0001", "1"), nome="Cliente João")
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, vendedor, inativo)
        VALUES ('1111111100011', 'Joao', FALSE)
    """))
    # Prospecto (não-cliente) na mesma cidade.
    _seed_estab(db, doc="pro", cnpj=("22222222", "0001", "2"), nome="Prospecto")

    itens = svc.candidatos(db, vendedor="Joao", municipio_codigo="2603900", hoje=date(2026, 6, 10))
    por_doc = {i["documento"]: i for i in itens}
    assert por_doc["1111111100011"]["eh_cliente"] is True
    assert por_doc["2222222200012"]["eh_cliente"] is False
    assert por_doc["1111111100011"]["cep"] == "55000000"


def test_candidatos_nao_traz_cliente_de_outro_vendedor(db):
    _seed_estab(db, doc="cli", cnpj=("33333333", "0001", "3"), nome="Cliente Maria")
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, vendedor, inativo)
        VALUES ('3333333300013', 'Maria', FALSE)
    """))
    itens = svc.candidatos(db, vendedor="Joao", municipio_codigo="2603900", hoje=date(2026, 6, 10))
    # Cliente da Maria não aparece (nem como prospecto, pois é cliente).
    assert all(i["documento"] != "3333333300013" for i in itens)


def test_candidatos_marca_em_risco(db):
    _seed_estab(db, doc="cli", cnpj=("44444444", "0001", "4"), nome="Cliente Atrasado")
    db.execute(text("""
        INSERT INTO cliente_pedido_mobile (documento, vendedor, inativo)
        VALUES ('4444444400014', 'Joao', FALSE)
    """))
    # Última compra há muito tempo -> em risco.
    db.execute(text("""
        INSERT INTO pedido_mobile_pedido (pedido_numero, cliente_documento, vendedor, emissao, total_liquido)
        VALUES (901, '4444444400014', 'Joao', '2026-01-01', 100)
    """))
    itens = svc.candidatos(db, vendedor="Joao", municipio_codigo="2603900", hoje=date(2026, 6, 10))
    por_doc = {i["documento"]: i for i in itens}
    assert por_doc["4444444400014"]["em_risco"] is True


def test_documentos_em_risco_respeita_limite_de_dias(db):
    db.execute(text("""
        INSERT INTO pedido_mobile_pedido (pedido_numero, cliente_documento, vendedor, emissao, total_liquido)
        VALUES
            (801, 'doc_antigo', 'Joao', '2026-01-01', 100),
            (802, 'doc_recente', 'Joao', '2026-06-09', 100)
    """))
    risco = svc.documentos_em_risco(db, vendedor="Joao", hoje=date(2026, 6, 10))
    assert "doc_antigo" in risco       # > 30 dias
    assert "doc_recente" not in risco  # < 30 dias
