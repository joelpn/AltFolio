import json
import sqlite3
from datetime import datetime

import pytest
from core.storage import (
    init_db, registrar_evento, guardar_precio_cache, obtener_precio_cache,
    file_hash, guardar_importacion, buscar_importacion_por_hash,
    obtener_historial_importaciones, obtener_snapshot_por_id,
    guardar_precio_historico, obtener_precios_historicos,
    eliminar_importacion, obtener_anios_disponibles,
    obtener_importacion_por_mes, obtener_mes_anterior,
    guardar_acciones_mensuales, obtener_acciones_por_import_id,
    calcular_cambios_entre_meses,
)


class TestInitDB:
    def test_init_db_crea_tablas(self, temp_db):
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tablas = [r[0] for r in cursor.fetchall()]
        conn.close()
        assert "eventos" in tablas
        assert "precios_cache" in tablas
        assert "imported_statements" in tablas
        assert "historical_prices" in tablas
        assert "acciones_mensuales" in tablas

    def test_init_db_idempotente(self, temp_db):
        init_db()
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        count = cursor.fetchone()[0]
        conn.close()
        assert count >= 5


class TestEventos:
    def test_registrar_y_obtener_evento(self, temp_db):
        registrar_evento(
            tipo="COMPRA",
            ticker="FMTY14",
            titulos=10,
            precio_unitario=15.50,
            monto_total=155.0,
            efectivo_post=1000.0,
            notas="Compra de prueba",
        )
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        assert row["tipo"] == "COMPRA"
        assert row["ticker"] == "FMTY14"
        assert row["titulos"] == 10

    def test_registrar_evento_minimal(self, temp_db):
        registrar_evento(tipo="INYECCION", monto_total=5000.0)
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row["tipo"] == "INYECCION"
        assert row["monto_total"] == 5000.0


class TestPreciosCache:
    def test_guardar_y_obtener(self, temp_db):
        guardar_precio_cache("FMTY14.MX", 15.50)
        cached = obtener_precio_cache("FMTY14.MX")
        assert cached is not None
        assert cached["precio_mxn"] == 15.50
        assert cached["ultimo_update"] is not None

    def test_actualizar_precio_existente(self, temp_db):
        guardar_precio_cache("FMTY14.MX", 15.50)
        guardar_precio_cache("FMTY14.MX", 16.00)
        cached = obtener_precio_cache("FMTY14.MX")
        assert cached["precio_mxn"] == 16.00

    def test_obtener_inexistente(self, temp_db):
        assert obtener_precio_cache("NOEXISTE.MX") is None


class TestFileHash:
    def test_file_hash_consistente(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_text("contenido de prueba")
        h1 = file_hash(str(f))
        h2 = file_hash(str(f))
        assert h1 == h2

    def test_file_hash_diferente(self, tmp_path):
        f1 = tmp_path / "a.pdf"
        f2 = tmp_path / "b.pdf"
        f1.write_text("contenido A")
        f2.write_text("contenido B")
        assert file_hash(str(f1)) != file_hash(str(f2))


class TestImportacion:
    def test_guardar_importacion(self, temp_db):
        posiciones = [
            {"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
             "titulos": 79, "precio_promedio_mxn": 10.83},
        ]
        import_id = guardar_importacion(
            filename="test.pdf",
            account="TEST001",
            month_label="2026-06",
            period_start="2026-06-01",
            period_end="2026-06-30",
            file_hash="abc123",
            efectivo_mxn=5000.0,
            capital_total=25000.0,
            posiciones=posiciones,
        )
        assert import_id is not None
        assert import_id > 0

    def test_guardar_y_recuperar_snapshot(self, temp_db, sample_snapshot):
        posiciones = sample_snapshot["posiciones"]
        import_id = guardar_importacion(
            filename="test.pdf",
            account="TEST001",
            month_label="2026-06",
            period_start="2026-06-01",
            period_end="2026-06-30",
            file_hash="abc123",
            efectivo_mxn=5000.0,
            capital_total=25000.0,
            posiciones=posiciones,
        )
        snapshot = obtener_snapshot_por_id(import_id)
        assert snapshot is not None
        assert len(snapshot["posiciones"]) == 2

    def test_buscar_por_hash(self, temp_db):
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 79, "precio_promedio_mxn": 10.83}]
        guardar_importacion("a.pdf", "T1", "2026-06", "", "", "hash_a", 0, 0, pos)
        encontrada = buscar_importacion_por_hash("hash_a")
        assert encontrada is not None
        assert encontrada["file_hash"] == "hash_a"

    def test_buscar_por_hash_inexistente(self, temp_db):
        assert buscar_importacion_por_hash("no_existe") is None

    def test_obtener_historial(self, temp_db):
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 79, "precio_promedio_mxn": 10.83}]
        guardar_importacion("a.pdf", "T1", "2026-05", "2026-05-01", "2026-05-31", "h1", 0, 0, pos)
        guardar_importacion("b.pdf", "T1", "2026-06", "2026-06-01", "2026-06-30", "h2", 0, 0, pos)
        hist = obtener_historial_importaciones()
        assert len(hist) == 2

    def test_eliminar_importacion(self, temp_db):
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 79, "precio_promedio_mxn": 10.83}]
        iid = guardar_importacion("a.pdf", "T1", "2026-06", "", "", "h1", 0, 0, pos)
        eliminar_importacion(iid)
        assert obtener_snapshot_por_id(iid) is None

    def test_obtener_anios_disponibles(self, temp_db):
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 79, "precio_promedio_mxn": 10.83}]
        guardar_importacion("a.pdf", "T1", "2025-12", "2025-12-01", "2025-12-31", "h1", 0, 0, pos)
        guardar_importacion("b.pdf", "T1", "2026-01", "2026-01-01", "2026-01-31", "h2", 0, 0, pos)
        anios = obtener_anios_disponibles()
        assert "2025" in anios
        assert "2026" in anios
        assert len(anios["2025"]) == 1

    def test_obtener_importacion_por_mes(self, temp_db):
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 79, "precio_promedio_mxn": 10.83}]
        guardar_importacion("a.pdf", "T1", "2026-06", "", "", "h1", 100.0, 5000.0, pos)
        meta = obtener_importacion_por_mes("T1", "2026-06")
        assert meta is not None
        assert meta["capital_total"] == 5000.0

    def test_obtener_importacion_por_mes_inexistente(self, temp_db):
        assert obtener_importacion_por_mes("T1", "2099-01") is None

    def test_obtener_mes_anterior(self, temp_db):
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 79, "precio_promedio_mxn": 10.83}]
        guardar_importacion("a.pdf", "T1", "2026-05", "", "", "h1", 0, 0, pos)
        guardar_importacion("b.pdf", "T1", "2026-06", "", "", "h2", 0, 0, pos)
        prev = obtener_mes_anterior("T1", "2026-06")
        assert prev is not None
        assert prev["month_label"] == "2026-05"


class TestPreciosHistoricos:
    def test_guardar_y_obtener(self, temp_db):
        guardar_precio_historico("FMTY14.MX", "2026-06-15", 14.50)
        guardar_precio_historico("FMTY14.MX", "2026-06-16", 14.80)
        historial = obtener_precios_historicos("FMTY14.MX", limit=10)
        assert len(historial) == 2
        assert historial[0]["precio"] == 14.80

    def test_obtener_sin_datos(self, temp_db):
        assert obtener_precios_historicos("NOEXISTE.MX") == []

    def test_actualizar_existente(self, temp_db):
        guardar_precio_historico("FMTY14.MX", "2026-06-15", 14.50)
        guardar_precio_historico("FMTY14.MX", "2026-06-15", 15.00)
        historial = obtener_precios_historicos("FMTY14.MX", limit=10)
        assert historial[0]["precio"] == 15.00


class TestAccionesMensuales:
    def test_guardar_y_obtener(self, temp_db):
        acciones = [
            {"ticker": "FMTY14", "tipo_accion": "COMPRA", "titulos": 10,
             "precio_mxn": 15.0, "monto_total": 150.0, "ganancia_perdida": 0},
        ]
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 10, "precio_promedio_mxn": 15.0}]
        iid = guardar_importacion("a.pdf", "T1", "2026-06", "", "", "h1", 0, 0, pos)
        guardar_acciones_mensuales(iid, "2026-06", acciones)
        obtenidas = obtener_acciones_por_import_id(iid)
        assert len(obtenidas) == 1
        assert obtenidas[0]["tipo_accion"] == "COMPRA"

    def test_sobrescribe_acciones(self, temp_db):
        acciones_v1 = [{"ticker": "FMTY14", "tipo_accion": "COMPRA", "titulos": 5,
                        "precio_mxn": 10.0, "monto_total": 50.0, "ganancia_perdida": 0}]
        acciones_v2 = [{"ticker": "FUNO11", "tipo_accion": "COMPRA", "titulos": 10,
                        "precio_mxn": 20.0, "monto_total": 200.0, "ganancia_perdida": 0}]
        pos = [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX", "tipo": "FIBRA",
                "titulos": 5, "precio_promedio_mxn": 10.0}]
        iid = guardar_importacion("a.pdf", "T1", "2026-06", "", "", "h1", 0, 0, pos)
        guardar_acciones_mensuales(iid, "2026-06", acciones_v1)
        guardar_acciones_mensuales(iid, "2026-06", acciones_v2)
        obtenidas = obtener_acciones_por_import_id(iid)
        assert len(obtenidas) == 1
        assert obtenidas[0]["ticker"] == "FUNO11"


class TestCalcularCambiosEntreMeses:
    def test_sin_cambios(self):
        prev = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 10, "precio_promedio_mxn": 10.0},
        ]}
        curr = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 10, "precio_promedio_mxn": 10.0},
        ]}
        acciones = calcular_cambios_entre_meses(prev, curr)
        assert acciones == []

    def test_compra_nueva_posicion(self):
        prev = {"posiciones": []}
        curr = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 10, "precio_promedio_mxn": 15.0},
        ]}
        acciones = calcular_cambios_entre_meses(prev, curr)
        assert len(acciones) == 1
        assert acciones[0]["tipo_accion"] == "COMPRA"
        assert acciones[0]["ticker"] == "FMTY14"

    def test_venta_total(self):
        prev = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 10, "precio_promedio_mxn": 10.0},
        ]}
        curr = {"posiciones": []}
        acciones = calcular_cambios_entre_meses(prev, curr)
        assert len(acciones) == 1
        assert acciones[0]["tipo_accion"] == "VENTA"
        assert acciones[0]["ticker"] == "FMTY14"

    def test_aumento_titulos(self):
        prev = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 10, "precio_promedio_mxn": 10.0},
        ]}
        curr = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 20, "precio_promedio_mxn": 12.0},
        ]}
        acciones = calcular_cambios_entre_meses(prev, curr)
        assert len(acciones) == 1
        assert acciones[0]["tipo_accion"] == "COMPRA"
        assert acciones[0]["titulos"] == 10

    def test_disminucion_titulos(self):
        prev = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 20, "precio_promedio_mxn": 10.0,
             "valor_mercado_mxn": 250.0},
        ]}
        curr = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 15, "precio_promedio_mxn": 10.0,
             "valor_mercado_mxn": 200.0},
        ]}
        acciones = calcular_cambios_entre_meses(prev, curr)
        assert len(acciones) == 1
        assert acciones[0]["tipo_accion"] == "VENTA"
        assert acciones[0]["titulos"] == 5

    def test_compra_y_venta_simultaneas(self):
        prev = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 10, "precio_promedio_mxn": 10.0},
        ]}
        curr = {"posiciones": [
            {"ticker": "FMTY14", "titulos": 15, "precio_promedio_mxn": 12.0},
            {"ticker": "FUNO11", "titulos": 5, "precio_promedio_mxn": 20.0},
        ]}
        acciones = calcular_cambios_entre_meses(prev, curr)
        assert len(acciones) == 2
        tipos = {a["tipo_accion"] for a in acciones}
        assert tipos == {"COMPRA", "COMPRA"}
