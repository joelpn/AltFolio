"""Tests de integracion para core/gbm_import.py con pdftotext real."""
import subprocess
import textwrap
from unittest.mock import patch

import pytest
from core.gbm_import import (
    _parse_posiciones_table, _parse_deuda_lines,
    _parse_period, _extract_numbers,
)


# ============= Verificacion del binario pdftotext =============


@pytest.mark.integration
class TestPdftotextDisponible:
    def test_pdftotext_instalado(self):
        """Verifica que pdftotext (poppler-utils) este instalado."""
        try:
            result = subprocess.run(["which", "pdftotext"], capture_output=True, text=True)
            assert result.returncode == 0, "pdftotext no encontrado"
            assert result.stdout.strip().endswith("pdftotext")
        except FileNotFoundError:
            pytest.fail("pdftotext no esta instalado")


# ============= parse_pdf end-to-end con subprocess mockeado =============


LINES_REALES = """\
ESTADO DE CUENTA
Contrato: T1

ACCIONES
FMTY14                                       100.00       79        1.00       10.83      855.91      100.00       50.00     1158.14      200.00      305.63
FUNO11                                        50.00       30       10.00       21.70      651.00       50.00       30.00      651.00       50.00       30.00
TOTAL ACCIONES:                              $1,809.14

ACCIONES DEL SIC
AAPL                                         250.00       10        0.00      240.00     2400.00      250.00       12.00     2500.00      180.00        0.52
TOTAL SIC:                                  $4,309.14

DEUDA
CETES 061226                                  10.00      100        0.00       10.00     1000.00        9.95      100.00      995.00      200.00        0.50
TOTAL DEUDA:                                 $995.00

EFECTIVO MISMO DIA                   $5,000.00

DEL 01/06/2026 AL 30/06/2026
"""  # noqa: E501


@pytest.mark.integration
class TestParsePdfEndToEnd:
    @patch("core.gbm_import.os.path.exists", return_value=True)
    @patch("core.gbm_import.subprocess.run")
    def test_parse_pdf_con_texto_real(self, mock_run, mock_exists):
        mock_run.return_value.stdout = LINES_REALES
        mock_run.return_value.returncode = 0

        from core.gbm_import import parse_pdf
        result = parse_pdf("/fake/file.pdf")

        assert "error" not in result
        assert result["cuenta"] == "T1"
        assert result["efectivo_mxn"] == 5000.0
        assert len(result["posiciones"]) == 4
        assert result["_month_label"] == "2026-06"

        tickers = [p["ticker"] for p in result["posiciones"]]
        assert "FMTY14" in tickers
        assert "FUNO11" in tickers
        assert tickers.count("AAPL") == 1  # SIC position
        assert "CETES061226" in tickers  # DEUDA (ticker sin espacios)

    @patch("core.gbm_import.os.path.exists", return_value=True)
    @patch("core.gbm_import.subprocess.run")
    def test_parse_pdf_pdftotext_falla(self, mock_run, mock_exists):
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "Error al procesar PDF"
        mock_run.return_value.stdout = ""

        from core.gbm_import import parse_pdf
        result = parse_pdf("/fake/file.pdf")
        assert "error" in result

    @patch("core.gbm_import.os.path.exists", return_value=True)
    @patch("core.gbm_import.subprocess.run")
    def test_parse_pdf_sin_posiciones(self, mock_run, mock_exists):
        mock_run.return_value.stdout = "Solo texto sin posiciones\n"
        mock_run.return_value.returncode = 0

        from core.gbm_import import parse_pdf
        result = parse_pdf("/fake/file.pdf")
        assert "error" in result

    def test_parse_pdf_archivo_inexistente(self):
        from core.gbm_import import parse_pdf
        result = parse_pdf("/ruta/inexistente.pdf")
        assert "error" in result
        assert "no encontrado" in result["error"].lower()


# ============= pdftotext real con PDF sintetico (reportlab) =============


@pytest.mark.integration
@pytest.mark.slow
class TestPdftotextSyntheticPDF:
    def test_pdftotext_extrae_texto_de_pdf_sintetico(self, tmp_path):
        """Crea un PDF con reportlab y verifica que pdftotext extrae texto."""
        try:
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import letter
        except ImportError:
            pytest.skip("reportlab no instalado")

        pdf_path = tmp_path / "test.pdf"
        c = canvas.Canvas(str(pdf_path), pagesize=letter)
        c.setFont("Helvetica", 10)
        c.drawString(50, 750, "ESTADO DE CUENTA")
        c.drawString(50, 735, "Contrato: T1")
        c.drawString(50, 715, "Hola mundo 123.45")
        c.save()

        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"pdftotext fallo: {result.stderr}"
        assert "ESTADO DE CUENTA" in result.stdout
        assert "Contrato: T1" in result.stdout
        assert "Hola mundo" in result.stdout
        assert "123.45" in result.stdout or "123 45" in result.stdout


# ============= Validacion de formato real =============


class TestParseoConFormatoReal:
    """Prueba que _parse_posiciones_table funcione con lineas realistas."""

    LINEA_ACCION = (
        "FMTY14                                       100.00       79        1.00       10.83      855.91      100.00       50.00     1158.14      200.00      305.63"
    )

    def test_linea_con_suficientes_numeros(self):
        nums = _extract_numbers(self.LINEA_ACCION)
        assert len(nums) >= 10, (
            f"Se esperaban >=10 numeros, se encontraron {len(nums)}. "
            f"Verifica que la linea tenga suficientes valores numericos. "
            f"Numeros encontrados: {[n[0] for n in nums]}"
        )

    def test_parsea_correctamente(self):
        lineas = [
            "ACCIONES",
            self.LINEA_ACCION,
            "TOTAL ACCIONES:                              $1,809.14",
        ]
        posiciones = _parse_posiciones_table(lineas)
        assert len(posiciones) == 1
        assert posiciones[0]["ticker"] == "FMTY14"
        assert posiciones[0]["tipo"] == "FIBRA"
        assert posiciones[0]["titulos"] == 79
        assert posiciones[0]["precio_promedio_mxn"] == 10.83
        assert posiciones[0]["costo_total_mxn"] == 855.91
        assert posiciones[0]["valor_mercado_mxn"] == 1158.14

    def test_parsea_deuda_correctamente(self):
        lineas = [
            "DEUDA",
            "CETES 061226                                  10.00      100        0.00       10.00     1000.00        9.95      100.00      995.00      200.00        0.50",
            "TOTAL DEUDA:                                 $995.00",
        ]
        posiciones = _parse_deuda_lines(lineas)
        assert len(posiciones) == 1
        assert posiciones[0]["ticker"] == "CETES061226"
        assert posiciones[0]["tipo"] == "DEUDA"
        assert posiciones[0]["titulos"] == 100
