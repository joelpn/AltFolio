import json
import os
from datetime import date, datetime

from core.market import obtener_precio
from core.simulator import SNAPSHOT_PATH
from core.storage import (
    eliminar_importacion, guardar_precio_historico,
    obtener_historial_importaciones, obtener_precios_historicos,
    obtener_snapshot_por_id, obtener_anios_disponibles,
    obtener_importacion_por_mes,
)


def listar_importaciones(limit=60):
    return obtener_historial_importaciones(limit=limit)


def restaurar_snapshot(import_id: int) -> dict:
    snapshot = obtener_snapshot_por_id(import_id)
    if not snapshot:
        return {"error": "Snapshot no encontrado"}

    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    return snapshot


def eliminar_importacion_por_id(import_id: int):
    eliminar_importacion(import_id)


def precios_actuales(tickers: list[str]) -> dict:
    from core.market import obtener_multiples_precios
    return obtener_multiples_precios(tickers)


def historial_precios(ticker: str, dias=30):
    return obtener_precios_historicos(ticker, limit=dias)


def actualizar_precios_historicos(tickers: list[str]):
    from core.storage import obtener_precio_cache, guardar_precio_cache
    from core.market import obtener_multiples_precios

    hoy = date.today().isoformat()
    for t in tickers:
        cached = obtener_precio_cache(t)
        if cached and cached.get("ultimo_update", "")[:10] == hoy:
            continue
        try:
            precio = obtener_precio(t)
            guardar_precio_cache(t, precio)
            guardar_precio_historico(t, hoy, precio)
        except Exception:
            pass

    return obtener_multiples_precios(tickers)


def obtener_snapshot_por_mes(account: str, month_label: str) -> dict | None:
    """Devuelve el snapshot guardado para un mes y cuenta específicos."""
    meta = obtener_importacion_por_mes(account, month_label)
    if not meta:
        return None
    return obtener_snapshot_por_id(meta["id"])


def obtener_calendario() -> dict:
    """
    Devuelve el calendario de importaciones agrupado por año:
    {"2026": [{"month_label": "2026-01", "import_id": 3, ...}, ...]}
    """
    return obtener_anios_disponibles()


def obtener_acciones_por_mes(account: str, month_label: str) -> list[dict]:
    """Devuelve las compras/ventas detectadas para un mes específico."""
    meta = obtener_importacion_por_mes(account, month_label)
    if not meta:
        return []
    from core.storage import obtener_acciones_por_import_id
    return obtener_acciones_por_import_id(meta["id"])

