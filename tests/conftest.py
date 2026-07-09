import json
import os
import pytest
from typing import Any

# ---------------------------------------------------------------------------
# Fixtures de infraestructura: redirigen DB, config y snapshot a tmp_path
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Crea una base SQLite temporal y redirige DB_PATH hacia ella."""
    db_file = tmp_path / "test_portfolio.db"
    monkeypatch.setattr("core.storage.DB_PATH", str(db_file))
    from core.storage import init_db
    init_db()
    return db_file


@pytest.fixture
def temp_config(tmp_path, monkeypatch):
    """Crea config.json temporal con valores por defecto."""
    cfg = {
        "comision_gbm_pct": 0.25,
        "intervalo_actualizacion_precios_seg": 60,
    }
    cfg_file = tmp_path / "config.json"
    with open(cfg_file, "w") as f:
        json.dump(cfg, f)
    monkeypatch.setattr("core.simulator.CONFIG_PATH", str(cfg_file))
    return cfg


@pytest.fixture
def temp_snapshot(tmp_path, monkeypatch):
    """
    Crea un snapshot.json temporal y redirige SNAPSHOT_PATH
    tanto en core.simulator como en core.history (import por valor).
    """
    snap_file = tmp_path / "snapshot.json"
    data = {"posiciones": [], "efectivo_mxn": 0.0, "capital_ficticio_disponible_mxn": 0.0}
    with open(snap_file, "w") as f:
        json.dump(data, f)
    # Parchear ambas referencias (gotcha del import por valor)
    monkeypatch.setattr("core.simulator.SNAPSHOT_PATH", str(snap_file))
    try:
        import core.history
        monkeypatch.setattr(core.history, "SNAPSHOT_PATH", str(snap_file))
    except ImportError:
        pass
    return snap_file


# ---------------------------------------------------------------------------
# Fábricas de datos
# ---------------------------------------------------------------------------


def _default_posicion(overrides: dict[str, Any] | None = None) -> dict:
    base = {
        "ticker": "FMTY14",
        "ticker_yahoo": "FMTY14.MX",
        "tipo": "FIBRA",
        "titulos": 79,
        "precio_promedio_mxn": 10.834329,
        "costo_total_mxn": 855.91,
        "valor_mercado_mxn": 1158.14,
    }
    if overrides:
        base.update(overrides)
    return base


@pytest.fixture
def sample_posicion() -> dict:
    return _default_posicion()


@pytest.fixture
def sample_snapshot() -> dict:
    return {
        "fecha_snapshot": "2026-06-30",
        "efectivo_mxn": 5000.0,
        "capital_ficticio_disponible_mxn": 25000.0,
        "cuenta": "TEST001",
        "_month_label": "2026-06",
        "_period_start": "2026-06-01",
        "_period_end": "2026-06-30",
        "posiciones": [
            _default_posicion(),
            _default_posicion({"ticker": "FUNO11", "ticker_yahoo": "FUNO11.MX", "tipo": "FIBRA",
                               "titulos": 30, "precio_promedio_mxn": 21.70, "costo_total_mxn": 651.0,
                               "valor_mercado_mxn": 900.0}),
        ],
    }


# ---------------------------------------------------------------------------
# Limpieza global
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _limpiar_estado_global():
    """Limpia estado global de market antes de cada test."""
    from core.market import TICKERS_INVALIDOS, TIPO_CAMBIO_CACHE
    TICKERS_INVALIDOS.clear()
    TIPO_CAMBIO_CACHE["rate"] = None
    TIPO_CAMBIO_CACHE["timestamp"] = 0.0
