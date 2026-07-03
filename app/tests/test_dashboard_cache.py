import routers.dashboard as dash


class _Relogio:
    """Relógio falso para controlar time.monotonic() nos testes de TTL."""

    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t


def test_cachettl_serve_dentro_do_ttl_e_recomputa_apos_vencer(monkeypatch):
    relogio = _Relogio()
    monkeypatch.setattr(dash, "time", relogio)
    cache = dash._CacheTTL(ttl_segundos=100)

    chamadas = []
    def carregar():
        chamadas.append(1)
        return "v"

    assert cache.obter("k", carregar) == "v"   # miss -> computa
    assert cache.obter("k", carregar) == "v"   # dentro do TTL -> serve do cache
    assert len(chamadas) == 1

    relogio.t = 150                            # passou dos 100s de TTL
    assert cache.obter("k", carregar) == "v"   # recomputa
    assert len(chamadas) == 2


def test_cachettl_poda_entradas_vencidas_na_escrita(monkeypatch):
    relogio = _Relogio()
    monkeypatch.setattr(dash, "time", relogio)
    cache = dash._CacheTTL(ttl_segundos=100)

    cache.obter("dia1", lambda: "a")           # t=0
    relogio.t = 200                            # dia1 vence
    cache.obter("dia2", lambda: "b")           # escrita poda a entrada vencida

    assert list(cache._store.keys()) == ["dia2"]  # não acumula sem limite
