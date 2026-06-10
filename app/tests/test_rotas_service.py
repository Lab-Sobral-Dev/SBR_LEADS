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
