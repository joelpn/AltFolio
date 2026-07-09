"""Tests unitarios para core/gbm_import.py (sin PDF real ni pdftotext)."""
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock, ANY

import pytest
from core.gbm_import import (
    _clean_ticker, _parse_decimal, _extract_numbers, _parse_period,
    _parse_posiciones_table, _parse_deuda_lines, parse_pdf, import_excel,
    import_file, persist_import,
)


# ============= _clean_ticker =============


class TestCleanTicker:
    def test_fibra_fmty(self):
        assert _clean_ticker("FMTY14") == ("FMTY14", "FIBRA", "FMTY14.MX")

    def test_fibra_funo(self):
        assert _clean_ticker("FUNO11") == ("FUNO11", "FIBRA", "FUNO11.MX")

    def test_fibra_fipra(self):
        assert _clean_ticker("FIPRA14") == ("FIPRA14", "FIBRA", "FIPRA14.MX")

    def test_etf_ivvpeso(self):
        assert _clean_ticker("IVVPESO") == ("IVVPESO", "ETF", "IVVPESO.MX")

    def test_accion_nacional(self):
        assert _clean_ticker("FSHOP13") == ("FSHOP13", "ACCION", "FSHOP13.MX")

    def test_sic_sin_mapeo(self):
        assert _clean_ticker("AMZN", es_sic=True) == ("AMZN", "SIC", "AMZN")

    def test_sic_baban_mapea_a_baba(self):
        assert _clean_ticker("BABAN", es_sic=True) == ("BABA", "SIC", "BABA")

    def test_sic_baba_sin_cambio(self):
        assert _clean_ticker("BABA", es_sic=True) == ("BABA", "SIC", "BABA")

    def test_ticker_con_asterisco(self):
        assert _clean_ticker("FMTY14*") == ("FMTY14", "FIBRA", "FMTY14.MX")

    def test_ticker_con_prefijo_1(self):
        assert _clean_ticker("1FMTY14") == ("FMTY14", "FIBRA", "FMTY14.MX")


# ============= _parse_decimal =============


class TestParseDecimal:
    def test_numero_simple(self):
        assert _parse_decimal("150.50") == 150.50

    def test_numero_con_signo_peso(self):
        assert _parse_decimal("$1,234.56") == 1234.56

    def test_numero_con_coma_miles(self):
        assert _parse_decimal("1,234,567.89") == 1234567.89

    def test_cadena_vacia(self):
        assert _parse_decimal("") is None

    def test_cadena_invalida(self):
        assert _parse_decimal("NO_NUMERO") is None

    def test_negativo(self):
        assert _parse_decimal("-500.00") == -500.00


# ============= _extract_numbers =============


class TestExtractNumbers:
    def test_encuentra_numeros(self):
        result = _extract_numbers("Hola $1,234 y 567.89")
        assert len(result) >= 2
        assert "$1,234" in [r[0] for r in result]
        assert "567.89" in [r[0] for r in result]

    def test_sin_numeros(self):
        assert _extract_numbers("Sin numeros aqui") == []

    def test_linea_vacia(self):
        assert _extract_numbers("") == []


# ============= _parse_period =============


class TestParsePeriod:
    def test_formato_fecha_corta(self):
        texto = "DEL 01/06/2026 AL 30/06/2026"
        ml, ps, pe = _parse_period(texto)
        assert ml == "2026-06"
        assert ps == "2026-06-01"
        assert pe == "2026-06-30"

    def test_formato_largo(self):
        texto = "DEL 1 AL 30 DE JUNIO DE 2026"
        ml, ps, pe = _parse_period(texto)
        assert ml == "2026-06"
        assert ps == "2026-06-01"
        assert pe == "2026-06-30"

    def test_formato_enero_abreviado(self):
        texto = "DEL 01/01/2026 AL 31/01/2026"
        ml, ps, pe = _parse_period(texto)
        assert ml == "2026-01"

    def test_sin_periodo(self):
        texto = "Solo texto sin fechas"
        ml, ps, pe = _parse_period(texto)
        assert ml == ""
        assert ps == ""
        assert pe == ""


# ============= _parse_posiciones_table =============


class TestParsePosicionesTable:
    LINEA_FMTY = (
        "FMTY14                                       100.00       79        1.00       10.83      855.91      100.00       50.00     1158.14      200.00      305.63"
    )

    def test_parsea_posicion_valida(self):
        lines = [self.LINEA_FMTY]
        posiciones = _parse_posiciones_table(lines)
        assert len(posiciones) == 1
        assert posiciones[0]["ticker"] == "FMTY14"
        assert posiciones[0]["tipo"] == "FIBRA"
        assert posiciones[0]["titulos"] == 79

    def test_ignora_encabezado(self):
        lines = ["EMISORA           TICKER    PRECIO    TITULOS    ...", self.LINEA_FMTY]
        posiciones = _parse_posiciones_table(lines)
        assert len(posiciones) == 1

    def test_ignora_total(self):
        lines = ["TOTAL: $10,000.00", self.LINEA_FMTY]
        posiciones = _parse_posiciones_table(lines)
        assert len(posiciones) == 1

    def test_linea_sin_numeros_ignorada(self):
        lines = ["Solo texto sin numeros"]
        assert _parse_posiciones_table(lines) == []

    def test_titulos_cero_ignorados(self):
        line = self.LINEA_FMTY.replace("79", "0", 1)
        assert _parse_posiciones_table([line]) == []

    def test_parsea_precio_promedio(self):
        posiciones = _parse_posiciones_table([self.LINEA_FMTY])
        assert posiciones[0]["precio_promedio_mxn"] == 10.83

    def test_parsea_costo_total(self):
        posiciones = _parse_posiciones_table([self.LINEA_FMTY])
        assert posiciones[0]["costo_total_mxn"] == 855.91

    def test_parsea_valor_mercado(self):
        posiciones = _parse_posiciones_table([self.LINEA_FMTY])
        assert posiciones[0]["valor_mercado_mxn"] == 1158.14


# ============= import_excel =============


class TestImportExcel:
    @pytest.fixture
    def mock_df(self):
        import pandas as pd
        return pd.DataFrame({
            "TICKER": ["FMTY14", "FUNO11"],
            "TITULOS": [79, 30],
            "PRECIO PROMEDIO": [10.83, 21.70],
            "EFECTIVO": [5000.0, None],
        })

    def test_importa_excel_valido(self, tmp_path, mock_df):
        import pandas as pd
        xlsx = tmp_path / "test.xlsx"
        mock_df.to_excel(xlsx, index=False)
        with patch("pandas.read_excel", return_value=mock_df):
            result = import_excel(str(xlsx))
        assert "error" not in result
        assert len(result["posiciones"]) == 2

    def test_excel_sin_ticker_error(self, tmp_path):
        import pandas as pd
        df = pd.DataFrame({"OTRA_COL": [1]})
        with patch("pandas.read_excel", return_value=df):
            result = import_excel("dummy.xlsx")
        assert "error" in result

    def test_excel_titulos_cero_ignorados(self, tmp_path):
        import pandas as pd
        df = pd.DataFrame({"TICKER": ["FMTY14", "MUERTA"], "TITULOS": [79, 0],
                           "EFECTIVO": [5000.0, None]})
        with patch("pandas.read_excel", return_value=df):
            result = import_excel("dummy.xlsx")
        assert len(result["posiciones"]) == 1

    def test_excel_vacio_error(self, tmp_path):
        import pandas as pd
        df = pd.DataFrame({"TICKER": [], "TITULOS": []})
        with patch("pandas.read_excel", return_value=df):
            result = import_excel("dummy.xlsx")
        assert "error" in result


# ============= import_file =============


class TestImportFile:
    def test_extension_no_soportada(self):
        result = import_file("test.csv")
        assert "error" in result
        assert "soportado" in result["error"]

    def test_extension_xlsx_llama_import_excel(self):
        with patch("core.gbm_import.import_excel", return_value={"posiciones": []}):
            result = import_file("test.xlsx")
        assert "error" not in result

    def test_extension_xls_llama_import_excel(self):
        with patch("core.gbm_import.import_excel", return_value={"posiciones": []}):
            result = import_file("test.xls")
        assert "error" not in result

    def test_extension_pdf_llama_parse_pdf(self):
        with patch("core.gbm_import.parse_pdf", return_value={"posiciones": []}):
            result = import_file("test.pdf")
        assert "error" not in result

    def test_import_file_con_error(self):
        with patch("core.gbm_import.parse_pdf", return_value={"error": "Fallo"}):
            result = import_file("test.pdf")
        assert "error" in result


# ============= persist_import =============


class TestPersistImport:
    def test_persist_import_duplicado_por_hash(self, temp_db, temp_config, temp_snapshot):
        with patch("core.storage.file_hash", return_value="dup_hash"):
            with patch("core.storage.buscar_importacion_por_hash", return_value={"month_label": "2026-06"}):
                result = persist_import("test.pdf", {
                    "_month_label": "2026-06", "cuenta": "T1",
                    "efectivo_mxn": 100, "capital_ficticio_disponible_mxn": 1000,
                    "posiciones": [],
                })
        assert result.get("_duplicate")

    def test_persist_import_duplicado_por_mes(self, temp_db, temp_config, temp_snapshot):
        with patch("core.storage.file_hash", return_value="h1"):
            with patch("core.storage.buscar_importacion_por_hash", return_value=None):
                with patch("core.storage.obtener_historial_importaciones",
                           return_value=[{"month_label": "2026-06", "account": "T1"}]):
                    result = persist_import("test.pdf", {
                        "_month_label": "2026-06", "cuenta": "T1",
                        "efectivo_mxn": 100, "capital_ficticio_disponible_mxn": 1000,
                        "posiciones": [],
                    })
        assert result.get("_duplicate")

    def test_persist_import_exitoso(self, temp_db, temp_config, temp_snapshot):
        with patch("core.storage.file_hash", return_value="h_new"):
            with patch("core.storage.buscar_importacion_por_hash", return_value=None):
                with patch("core.storage.obtener_historial_importaciones", return_value=[]):
                    with patch("core.storage.obtener_mes_anterior", return_value=None):
                        result = persist_import("test.pdf", {
                            "_month_label": "2026-06", "cuenta": "T1",
                            "efectivo_mxn": 100, "capital_ficticio_disponible_mxn": 1000,
                            "posiciones": [{"ticker": "FMTY14", "ticker_yahoo": "FMTY14.MX",
                                            "tipo": "FIBRA", "titulos": 10,
                                            "precio_promedio_mxn": 15.0}],
                        })
        assert "error" not in result
        assert result["efectivo_mxn"] == 100
