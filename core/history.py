import json
import os
from datetime import date, datetime, timedelta

from core.simulator import SNAPSHOT_PATH
from core.storage import (
    eliminar_importacion,
    obtener_historial_importaciones,
    obtener_snapshot_por_id, obtener_anios_disponibles,
    obtener_precios_historicos,
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


def obtener_calendario() -> dict:
    return obtener_anios_disponibles()


def obtener_curva_patrimonio() -> list[dict]:
    """
    Devuelve lista de {fecha, valor} mensual desde todas las importaciones,
    ordenada cronologicamente.
    """
    importaciones = obtener_historial_importaciones(limit=9999)
    puntos = []
    for imp in importaciones:
        period_start = imp.get("period_start")
        capital = imp.get("capital_total", 0)
        if period_start and capital:
            puntos.append({"fecha": period_start[:10], "valor": capital})
    puntos.sort(key=lambda x: x["fecha"])
    return puntos


def obtener_rendimientos_mensuales() -> list[dict]:
    """Devuelve [{fecha, ganancia, porcentaje}] mensual basado en la curva de patrimonio."""
    curva = obtener_curva_patrimonio()
    rendimientos = []
    for i in range(1, len(curva)):
        prev = curva[i-1]["valor"]
        curr = curva[i]["valor"]
        delta = curr - prev
        pct = ((curr / prev) - 1) * 100 if prev else 0
        rendimientos.append({
            "fecha": curva[i]["fecha"][:7],
            "ganancia": round(delta, 2),
            "porcentaje": round(pct, 2),
        })
    return rendimientos


def calcular_kpis(dashboard=None) -> dict:
    """Calcula rendimientos diario, mensual, YTD y total
    basado en las importaciones disponibles."""
    from core.market import TICKERS_INVALIDOS
    importaciones = obtener_historial_importaciones(limit=9999)
    if len(importaciones) < 1:
        return {"hoy_pct": 0, "hoy_val": 0, "mes_pct": 0, "mes_val": 0,
                "ytd_pct": 0, "ytd_val": 0, "total_pct": 0, "total_val": 0}

    ultimo = importaciones[0]
    valor_actual = ultimo.get("capital_total", 0)
    fecha_actual = ultimo.get("period_start", "")[:10] if ultimo.get("period_start") else ""

    # Total: vs primera importacion
    primero = importaciones[-1]
    valor_inicial = primero.get("capital_total", 1)
    total_val = valor_actual - valor_inicial
    total_pct = ((valor_actual / valor_inicial) - 1) * 100 if valor_inicial else 0

    # YTD: vs importacion mas cercana al 1 de enero del año actual
    anio_actual = date.today().year
    ytd_val = 0
    ytd_pct = 0
    for imp in reversed(importaciones):
        ps = imp.get("period_start", "")
        if ps and ps.startswith(str(anio_actual)):
            base = imp.get("capital_total", valor_actual)
            ytd_val = valor_actual - base
            ytd_pct = ((valor_actual / base) - 1) * 100 if base else 0
            break

    # Mensual: vs importacion mas cercana hace ~30 dias
    mes_val = 0
    mes_pct = 0
    objetivo = date.today() - timedelta(days=35)
    for imp in reversed(importaciones):
        ps = imp.get("period_start", "")
        if ps:
            try:
                fd = datetime.strptime(ps[:10], "%Y-%m-%d").date()
                if fd <= objetivo:
                    base = imp.get("capital_total", valor_actual)
                    mes_val = valor_actual - base
                    mes_pct = ((valor_actual / base) - 1) * 100 if base else 0
                    break
            except ValueError:
                continue

    # Diario: usar precios del ultimo snapshot + historical_prices
    hoy_val = 0
    hoy_pct = 0
    if dashboard and not dashboard.modo_historico:
        try:
            estado = dashboard.sim.obtener_estado()
            tickers_precios = dashboard.precios
            cash = estado.get("efectivo_ficticio", 0) or dashboard.sim.efectivo_ficticio
            valor_hoy = cash
            tickers_lista = [t for t in estado.get("posiciones", {})
                            if t not in TICKERS_INVALIDOS]

            for t in tickers_lista:
                info = estado["posiciones"].get(t, {})
                tit = info.get("titulos", 0)
                precio_vivo = tickers_precios.get(t)
                if precio_vivo:
                    valor_hoy += tit * precio_vivo

            # Valor de ayer desde historical_prices
            ayer = (date.today() - timedelta(days=1)).isoformat()
            valor_ayer = 0
            for t in tickers_lista:
                precios_hist = obtener_precios_historicos(t, limit=5)
                precio_ayer = None
                for ph in precios_hist:
                    if ph["fecha"] <= ayer:
                        precio_ayer = ph["precio"]
                        break
                if precio_ayer:
                    info = estado["posiciones"].get(t, {})
                    valor_ayer += info.get("titulos", 0) * precio_ayer
            valor_ayer += cash

            if valor_ayer:
                hoy_val = valor_hoy - valor_ayer
                hoy_pct = ((valor_hoy / valor_ayer) - 1) * 100
        except Exception:
            pass

    return {
        "hoy_pct": hoy_pct, "hoy_val": hoy_val,
        "mes_pct": mes_pct, "mes_val": mes_val,
        "ytd_pct": ytd_pct, "ytd_val": ytd_val,
        "total_pct": total_pct, "total_val": total_val,
    }

