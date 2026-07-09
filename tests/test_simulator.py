import json
import pytest
from core.simulator import Simulador, cargar_snapshot


class TestCargaInicial:
    def test_carga_vacia_sin_archivos(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        estado = sim.obtener_estado()
        assert estado["efectivo_ficticio"] == 0.0
        assert estado["posiciones"] == {}

    def test_carga_con_snapshot(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump(sample_snapshot, f)
        sim = Simulador()
        estado = sim.obtener_estado()
        assert estado["efectivo_ficticio"] > 0
        assert len(estado["posiciones"]) == 2

    def test_carga_con_snapshot_vacio_retorna_vacio(self, temp_db, temp_config, temp_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump({}, f)
        sim = Simulador()
        estado = sim.obtener_estado()
        assert estado["efectivo_ficticio"] == 0.0

    def test_snapshot_con_posiciones_sin_tipo_lanza_keyerror(self, temp_db, temp_config, temp_snapshot):
        data = {
            "efectivo_mxn": 1000.0,
            "capital_ficticio_disponible_mxn": 5000.0,
            "posiciones": [
                {"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX",
                 "titulos": 10, "precio_promedio_mxn": 15.0},
            ],
        }
        with open(temp_snapshot, "w") as f:
            json.dump(data, f)
        with pytest.raises(KeyError):
            Simulador()


class TestCargarSnapshot:
    def test_cargar_snapshot_desde_archivo(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump(sample_snapshot, f)
        data = cargar_snapshot()
        assert data["efectivo_mxn"] == 5000.0
        assert len(data["posiciones"]) == 2

    def test_cargar_snapshot_archivo_inexistente(self, temp_db, temp_config, temp_snapshot):
        import os
        os.remove(str(temp_snapshot))
        with pytest.raises(FileNotFoundError):
            cargar_snapshot()


class TestInyectarCapital:
    def test_inyectar_monto_positivo(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        sim.inyectar_capital(10000.0)
        assert sim.efectivo_ficticio == 10000.0

    def test_inyectar_multiple_veces(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        sim.inyectar_capital(5000.0)
        sim.inyectar_capital(3000.0)
        assert sim.efectivo_ficticio == 8000.0

    def test_inyectar_cero(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        sim.inyectar_capital(0)
        assert sim.efectivo_ficticio == 0.0

    def test_inyectar_registra_evento(self, temp_db, temp_config, temp_snapshot):
        import sqlite3
        sim = Simulador()
        sim.inyectar_capital(5000.0)
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row["tipo"] == "INYECCION"
        assert row["monto_total"] == 5000.0


class TestSimularCompra:
    def test_compra_simple(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        sim.inyectar_capital(10000.0)
        result = sim.simular_compra("FMTY14", 10, 15.0)
        assert "error" not in result
        estado = sim.obtener_estado()
        assert "FMTY14" in estado["posiciones"]
        assert estado["posiciones"]["FMTY14"]["titulos"] == 10

    def test_compra_con_comision(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        sim.inyectar_capital(10000.0)
        sim.simular_compra("FMTY14", 10, 100.0)
        # Comision 0.25% -> costo_total = 10 * 100 * 1.0025 = 1002.50
        assert sim.efectivo_ficticio == pytest.approx(10000.0 - 1002.50, 0.01)

    def test_compra_fondos_insuficientes(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        result = sim.simular_compra("FMTY14", 10, 1_000_000.0)
        assert "error" in result
        assert "Fondos" in result["error"]

    def test_compra_acumula_titulos(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        sim.inyectar_capital(10000.0)
        sim.simular_compra("FMTY14", 5, 10.0)
        sim.simular_compra("FMTY14", 5, 12.0)
        pos = sim.obtener_estado()["posiciones"]["FMTY14"]
        assert pos["titulos"] == 10
        # Precio promedio ponderado: (5*10 + 5*12) / 10 = 11.0
        assert pos["precio_promedio_mxn"] == 11.0

    def test_compra_con_ticker_sic(self, temp_db, temp_config, temp_snapshot):
        sim = Simulador()
        sim.inyectar_capital(10000.0)
        sim.simular_compra("AMZN", 1, 200.0)
        estado = sim.obtener_estado()
        assert estado["posiciones"]["AMZN"]["tipo"] == "SIC"

    def test_compra_registra_evento(self, temp_db, temp_config, temp_snapshot):
        import sqlite3
        sim = Simulador()
        sim.inyectar_capital(10000.0)
        sim.simular_compra("FMTY14", 10, 15.0)
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        assert row["tipo"] == "COMPRA_SIM"


class TestSimularVenta:
    @pytest.fixture(autouse=True)
    def _setup(self, temp_db, temp_config, temp_snapshot):
        self.sim = Simulador()
        self.sim.inyectar_capital(10000.0)
        self.sim.simular_compra("FMTY14", 10, 10.0)

    def test_venta_parcial(self):
        result = self.sim.simular_venta("FMTY14", 3, 12.0)
        assert "error" not in result
        estado = self.sim.obtener_estado()
        assert estado["posiciones"]["FMTY14"]["titulos"] == 7

    def test_venta_total(self):
        self.sim.simular_venta("FMTY14", 10, 12.0)
        estado = self.sim.obtener_estado()
        assert "FMTY14" not in estado["posiciones"]

    def test_venta_con_ganancia(self):
        result = self.sim.simular_venta("FMTY14", 5, 12.0)
        # Ganancia = (12 - 10) * 5 = 10
        assert result["ganancia"] == pytest.approx(10.0, 0.01)

    def test_venta_con_perdida(self):
        result = self.sim.simular_venta("FMTY14", 5, 8.0)
        # Perdida = (8 - 10) * 5 = -10
        assert result["ganancia"] == pytest.approx(-10.0, 0.01)

    def test_venta_titulos_insuficientes(self):
        result = self.sim.simular_venta("FMTY14", 999, 12.0)
        assert "error" in result

    def test_venta_posicion_inexistente(self):
        result = self.sim.simular_venta("NOEXISTE", 1, 100.0)
        assert "error" in result

    def test_venta_con_comision(self):
        efectivo_prev = self.sim.efectivo_ficticio
        self.sim.simular_venta("FMTY14", 5, 100.0)
        # Ingreso = 5 * 100 * (1 - 0.0025) = 498.75
        assert self.sim.efectivo_ficticio == pytest.approx(efectivo_prev + 498.75, 0.01)
