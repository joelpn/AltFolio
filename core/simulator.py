import json
import os
from core.storage import init_db, registrar_evento

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), '..', 'snapshot.json')
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')


def _cargar_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def cargar_snapshot():
    with open(SNAPSHOT_PATH) as f:
        return json.load(f)


class Simulador:
    def __init__(self):
        init_db()
        # Priority: XML > PDF > Snapshot.json
        snapshot = self._cargar_mejor_snapshot()
        self.config = _cargar_config()
        self.efectivo_ficticio = snapshot["capital_ficticio_disponible_mxn"]
        self.posiciones = {}
        for p in snapshot["posiciones"]:
            ticker = p["ticker"]
            self.posiciones[ticker] = {
                "ticker_yahoo": p["ticker_yahoo"],
                "tipo": p["tipo"],
                "titulos": p["titulos"],
                "precio_promedio_mxn": p.get("precio_promedio_mxn"),
                "costo_total_mxn": p.get("costo_total_mxn"),
            }
        self.historial_eventos = []

    def _cargar_mejor_snapshot(self):
        from core.history import listar_importaciones
        from core.storage import obtener_snapshot_por_id
        importaciones = listar_importaciones()

        if importaciones:
            ultimo = importaciones[0]
            snapshot = obtener_snapshot_por_id(ultimo["id"])
            if snapshot and snapshot.get("posiciones"):
                return snapshot

        if os.path.exists(SNAPSHOT_PATH):
            try:
                with open(SNAPSHOT_PATH) as f:
                    data = json.load(f)
                if data.get("posiciones"):
                    return data
            except (json.JSONDecodeError, IOError):
                pass

        return {
            "fecha_snapshot": "",
            "efectivo_mxn": 0.0,
            "capital_ficticio_disponible_mxn": 0.0,
            "posiciones": []
        }

    def obtener_estado(self):
        return {
            "efectivo_ficticio": self.efectivo_ficticio,
            "posiciones": self.posiciones,
        }

    def inyectar_capital(self, monto):
        self.efectivo_ficticio += monto
        registrar_evento(
            tipo="INYECCION",
            monto_total=monto,
            efectivo_post=self.efectivo_ficticio,
            notas=f"Inyección de ${monto:,.2f} MXN",
        )

    def simular_compra(self, ticker, titulos, precio_unitario):
        comision = self.config["comision_gbm_pct"] / 100
        costo_total = titulos * precio_unitario * (1 + comision)

        if self.efectivo_ficticio < costo_total:
            return {"error": "Fondos insuficientes"}

        self.efectivo_ficticio -= costo_total

        if ticker in self.posiciones:
            pos = self.posiciones[ticker]
            total_titulos = pos["titulos"] + titulos
            total_costo = pos["titulos"] * (pos["precio_promedio_mxn"] or 0) + titulos * precio_unitario
            pos["precio_promedio_mxn"] = total_costo / total_titulos if total_titulos else 0
            pos["titulos"] = total_titulos
        else:
            self.posiciones[ticker] = {
                "ticker_yahoo": ticker,
                "tipo": "SIC",
                "titulos": titulos,
                "precio_promedio_mxn": precio_unitario,
                "costo_total_mxn": costo_total,
            }

        registrar_evento(
            tipo="COMPRA_SIM",
            ticker=ticker,
            titulos=titulos,
            precio_unitario=precio_unitario,
            monto_total=costo_total,
            efectivo_post=self.efectivo_ficticio,
        )

        return self.posiciones[ticker]

    def simular_venta(self, ticker, titulos, precio_unitario):
        if ticker not in self.posiciones:
            return {"error": "Posición no encontrada"}

        pos = self.posiciones[ticker]
        if pos["titulos"] < titulos:
            return {"error": "Títulos insuficientes"}

        comision = self.config["comision_gbm_pct"] / 100
        precio_prom = pos["precio_promedio_mxn"] or 0
        ingreso = titulos * precio_unitario * (1 - comision)
        ganancia = (precio_unitario - precio_prom) * titulos

        self.efectivo_ficticio += ingreso
        pos["titulos"] -= titulos

        if pos["titulos"] == 0:
            del self.posiciones[ticker]

        registrar_evento(
            tipo="VENTA_SIM",
            ticker=ticker,
            titulos=titulos,
            precio_unitario=precio_unitario,
            monto_total=ingreso,
            efectivo_post=self.efectivo_ficticio,
            notas=f"Ganancia/Pérdida: ${ganancia:,.2f} MXN",
        )

        return {"ingreso": ingreso, "ganancia": ganancia, "posiciones_restantes": pos.get("titulos", 0)}
