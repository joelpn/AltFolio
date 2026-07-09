import json
from unittest.mock import patch, MagicMock

import pytest
from core import history


# ============= listar_importaciones =============


class TestListarImportaciones:
    def test_listar_importaciones_delega_a_storage(self, temp_db, temp_config, temp_snapshot):
        mock = [{"id": 1, "month_label": "2026-06"}]
        with patch("core.history.obtener_historial_importaciones", return_value=mock):
            assert history.listar_importaciones() == mock

    def test_listar_importaciones_vacio(self, temp_db, temp_config, temp_snapshot):
        with patch("core.history.obtener_historial_importaciones", return_value=[]):
            assert history.listar_importaciones() == []


# ============= restaurar_snapshot =============


class TestRestaurarSnapshot:
    def test_restaurar_snapshot_escribe_archivo(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        import_data = {
            "month_label": "2026-06",
            "cuenta": "T1",
            "efectivo_mxn": 5000.0,
            "capital_ficticio_disponible_mxn": 10000.0,
            "posiciones": [
                {"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX",
                 "tipo": "FIBRA", "titulos": 100, "precio_promedio_mxn": 15.0,
                 "costo_total_mxn": 1500.0, "valor_mercado_mxn": 2000.0,
                 "precio_actual_mxn": 20.0, "plusvalia_mxn": 500.0,
                 "rendimiento_porcentaje": 33.33},
            ],
        }
        with patch("core.history.obtener_snapshot_por_id", return_value=import_data):
            result = history.restaurar_snapshot(1)

        assert "error" not in result
        with open(temp_snapshot) as f:
            data = json.load(f)
        assert data["efectivo_mxn"] == 5000.0
        assert len(data["posiciones"]) == 1

    def test_restaurar_snapshot_importacion_inexistente(self, temp_db, temp_config, temp_snapshot):
        with patch("core.history.obtener_snapshot_por_id", return_value=None):
            result = history.restaurar_snapshot(999)
        assert "error" in result

    def test_restaurar_snapshot_sin_posiciones(self, temp_db, temp_config, temp_snapshot):
        import_data = {
            "month_label": "2026-06",
            "cuenta": "T1",
            "efectivo_mxn": 5000.0,
            "capital_ficticio_disponible_mxn": 5000.0,
            "posiciones": [],
        }
        with patch("core.history.obtener_snapshot_por_id", return_value=import_data):
            result = history.restaurar_snapshot(1)
        assert "error" not in result
        with open(temp_snapshot) as f:
            data = json.load(f)
        assert data["posiciones"] == []


# ============= obtener_calendario =============


class TestObtenerCalendario:
    def test_calendario_con_datos(self, temp_db, temp_config, temp_snapshot):
        mock_calendario = {
            "2026": [
                {"month_label": "2026-01", "import_id": 1, "capital_total": 10000.0},
                {"month_label": "2026-06", "import_id": 2, "capital_total": 15000.0},
            ]
        }
        with patch("core.history.obtener_anios_disponibles", return_value=mock_calendario):
            calendario = history.obtener_calendario()
        assert "2026" in calendario
        assert len(calendario["2026"]) == 2

    def test_calendario_vacio(self, temp_db, temp_config, temp_snapshot):
        with patch("core.history.obtener_anios_disponibles", return_value={}):
            assert history.obtener_calendario() == {}


# ============= obtener_curva_patrimonio =============


class TestObtenerCurvaPatrimonio:
    def test_curva_con_datos(self, temp_db, temp_config, temp_snapshot):
        mock_imports = [
            {"id": 2, "month_label": "2026-06", "period_start": "2026-06-01", "capital_total": 15000.0},
            {"id": 1, "month_label": "2026-01", "period_start": "2026-01-01", "capital_total": 10000.0},
        ]
        with patch("core.history.obtener_historial_importaciones", return_value=mock_imports):
            curva = history.obtener_curva_patrimonio()
        assert len(curva) == 2
        # Orden cronologico: enero antes que junio
        assert curva[0]["fecha"] == "2026-01-01"
        assert curva[0]["valor"] == 10000.0
        assert curva[1]["fecha"] == "2026-06-01"
        assert curva[1]["valor"] == 15000.0

    def test_curva_sin_datos(self, temp_db, temp_config, temp_snapshot):
        with patch("core.history.obtener_historial_importaciones", return_value=[]):
            assert history.obtener_curva_patrimonio() == []

    def test_curva_filtra_sin_period_start(self, temp_db, temp_config, temp_snapshot):
        mock_imports = [
            {"id": 1, "month_label": "2026-01", "period_start": None, "capital_total": 10000.0},
        ]
        with patch("core.history.obtener_historial_importaciones", return_value=mock_imports):
            assert history.obtener_curva_patrimonio() == []


# ============= calcular_kpis =============


class TestCalcularKpis:
    def test_kpis_con_datos_suficientes(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump(sample_snapshot, f)

        # La funcion ordena por id DESC internamente, asi que el primer elemento
        # de la lista es el mas reciente
        mock_imports = [
            {"id": 3, "capital_total": 12500.0, "period_start": "2026-06-01"},
            {"id": 2, "capital_total": 11000.0, "period_start": "2026-05-01"},
            {"id": 1, "capital_total": 9000.0, "period_start": "2025-12-01"},
        ]
        with patch("core.history.obtener_historial_importaciones", return_value=mock_imports):
            kpis = history.calcular_kpis({})

        assert kpis["total_pct"] is not None
        assert kpis["total_val"] is not None

    def test_kpis_sin_datos_historicos(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump(sample_snapshot, f)

        with patch("core.history.obtener_historial_importaciones", return_value=[]):
            kpis = history.calcular_kpis({})
        assert kpis["total_val"] == 0
        assert kpis["total_pct"] == 0

    def test_kpis_sin_capital_inicial(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump(sample_snapshot, f)

        mock_imports = [{"id": 1, "capital_total": 0, "period_start": "2026-06-01"}]
        with patch("core.history.obtener_historial_importaciones", return_value=mock_imports):
            kpis = history.calcular_kpis({})
        assert kpis["total_pct"] == 0

    def test_kpis_con_dashboard_mockeado(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump(sample_snapshot, f)

        mock_dashboard = MagicMock()
        mock_dashboard.modo_historico = True  # salta el codigo diario

        mock_imports = [
            {"id": 2, "capital_total": 15000.0, "period_start": "2026-06-01"},
            {"id": 1, "capital_total": 10000.0, "period_start": "2026-01-01"},
        ]
        with patch("core.history.obtener_historial_importaciones", return_value=mock_imports):
            kpis = history.calcular_kpis(mock_dashboard)
        assert kpis["total_val"] == 5000.0  # 15000 - 10000
        assert kpis["total_pct"] == pytest.approx(50.0, 0.01)

    def test_kpis_mes_actual_calculado(self, temp_db, temp_config, temp_snapshot, sample_snapshot):
        with open(temp_snapshot, "w") as f:
            json.dump(sample_snapshot, f)

        mock_dashboard = MagicMock()
        mock_dashboard.modo_historico = True

        mock_imports = [
            {"id": 3, "capital_total": 12500.0, "period_start": "2026-06-15"},
            {"id": 2, "capital_total": 11000.0, "period_start": "2026-05-01"},
            {"id": 1, "capital_total": 9000.0, "period_start": "2025-12-01"},
        ]
        with patch("core.history.obtener_historial_importaciones", return_value=mock_imports):
            kpis = history.calcular_kpis(mock_dashboard)
        assert kpis["mes_val"] is not None
