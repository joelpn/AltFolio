"""Tests para core/market.py — yfinance siempre mockeado, sin llamadas reales."""
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from core import market


# ---------------------------------------------------------------------------
# Fixture autouse para aislar TICKERS_INVALIDOS y evitar llamadas reales
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_estado_global():
    market.TICKERS_INVALIDOS.clear()
    market.TIPO_CAMBIO_CACHE["rate"] = None
    market.TIPO_CAMBIO_CACHE["timestamp"] = 0.0
    yield
    market.TICKERS_INVALIDOS.clear()
    market.TIPO_CAMBIO_CACHE["rate"] = None
    market.TIPO_CAMBIO_CACHE["timestamp"] = 0.0


# ============= obtener_precio =============


class TestObtenerPrecio:
    def test_precio_exitoso_con_1d(self):
        mock_hist = pd.DataFrame({"Close": [150.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            precio = market.obtener_precio("FMTY14.MX")

        assert precio == 150.0
        mock_ticker.history.assert_called_with(period="1d")

    def test_fallback_a_5d_cuando_1d_vacio(self):
        mock_hist_1d = pd.DataFrame()
        mock_hist_5d = pd.DataFrame({"Close": [148.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = [mock_hist_1d, mock_hist_5d]

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            precio = market.obtener_precio("FMTY14.MX")

        assert precio == 148.0

    def test_fallback_a_1mo_cuando_1d_y_5d_vacios(self):
        mock_hist_1d = pd.DataFrame()
        mock_hist_5d = pd.DataFrame()
        mock_hist_1mo = pd.DataFrame({"Close": [145.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = [mock_hist_1d, mock_hist_5d, mock_hist_1mo]

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            precio = market.obtener_precio("FMTY14.MX")

        assert precio == 145.0

    def test_todos_los_periodos_vacios_lanza_error(self):
        mock_hist = pd.DataFrame()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            with pytest.raises(ValueError, match="No se pudo obtener precio"):
                market.obtener_precio("FMTY14.MX")

    def test_no_agrega_a_tickers_invalidos_en_error(self):
        mock_hist = pd.DataFrame()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            with pytest.raises(ValueError):
                market.obtener_precio("FMTY14.MX")

        assert "FMTY14.MX" not in market.TICKERS_INVALIDOS

    def test_ticker_en_invalidos_lanza_error_inmediato(self):
        market.excluir_ticker("MALA.MX")
        with pytest.raises(ValueError, match="Ticker inválido"):
            market.obtener_precio("MALA.MX")

    def test_sic_sin_mx_aplica_tipo_cambio(self):
        mock_hist = pd.DataFrame({"Close": [150.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        # Mock _obtener_tipo_cambio para que devuelva 20.0
        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            with patch.object(market, "_obtener_tipo_cambio", return_value=20.0):
                precio = market.obtener_precio("AAPL")

        # 150 USD * 20 = 3000 MXN
        assert precio == 3000.0

    def test_nacional_con_mx_no_aplica_tipo_cambio(self):
        mock_hist = pd.DataFrame({"Close": [150.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            with patch.object(market, "_obtener_tipo_cambio", return_value=20.0):
                precio = market.obtener_precio("FMTY14.MX")

        # 150 MXN, sin conversion
        assert precio == 150.0


# ============= obtener_multiples_precios =============


class TestObtenerMultiplesPrecios:
    def test_lista_vacia(self):
        assert market.obtener_multiples_precios([]) == {}

    def test_batch_exitoso_con_download(self):
        # yfinance.download devuelve un DataFrame con MultiIndex columns
        # cuando hay múltiples tickers: (Close, TICKER), (Volume, TICKER), ...
        idx = pd.to_datetime(["2026-07-08"])
        arrays = [["Close", "Close"], ["A.MX", "B.MX"]]
        tuples = list(zip(*arrays))
        index = pd.MultiIndex.from_tuples(tuples, names=["Price", "Ticker"])
        data = [[100.0, 200.0]]
        mock_df = pd.DataFrame(data, index=idx, columns=index)

        with patch.object(market.yf, "download", return_value=mock_df):
            result = market.obtener_multiples_precios(["A.MX", "B.MX"])

        assert result.get("A.MX") == 100.0
        assert result.get("B.MX") == 200.0

    def test_batch_con_sic_aplica_tipo_cambio(self):
        idx = pd.to_datetime(["2026-07-08"])
        arrays = [["Close", "Close"], ["A.MX", "AAPL"]]
        tuples = list(zip(*arrays))
        index = pd.MultiIndex.from_tuples(tuples, names=["Price", "Ticker"])
        data = [[100.0, 150.0]]
        mock_df = pd.DataFrame(data, index=idx, columns=index)

        with patch.object(market.yf, "download", return_value=mock_df):
            with patch.object(market, "_obtener_tipo_cambio", return_value=20.0):
                result = market.obtener_multiples_precios(["A.MX", "AAPL"])

        assert result.get("A.MX") == 100.0  # MXN, sin cambio
        assert result.get("AAPL") == 3000.0  # 150 USD * 20

    def test_fallback_individual_cuando_batch_falla(self):
        mock_hist = pd.DataFrame({"Close": [150.0]})
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch.object(market.yf, "download", side_effect=Exception("Network error")):
            with patch.object(market.yf, "Ticker", return_value=mock_ticker):
                result = market.obtener_multiples_precios(["FMTY14.MX"])

        assert result.get("FMTY14.MX") == 150.0

    def test_fallback_individual_cuando_batch_devuelve_vacio(self):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [150.0]})

        with patch.object(market.yf, "download", return_value=pd.DataFrame()):
            with patch.object(market.yf, "Ticker", return_value=mock_ticker):
                result = market.obtener_multiples_precios(["FMTY14.MX"])

        assert result.get("FMTY14.MX") == 150.0

    def test_filtra_tickers_invalidos(self):
        market.excluir_ticker("MALA.MX")
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"Close": [100.0]})

        with patch.object(market.yf, "download", return_value=pd.DataFrame()):
            with patch.object(market.yf, "Ticker", return_value=mock_ticker):
                result = market.obtener_multiples_precios(["MALA.MX", "BUENO.MX"])
        assert result.get("MALA.MX") is None
        assert result.get("BUENO.MX") == 100.0

    def test_retorna_none_para_ticker_que_falla_individual(self):
        mock_bueno = MagicMock()
        mock_bueno.history.return_value = pd.DataFrame({"Close": [100.0]})
        mock_malo = MagicMock()
        mock_malo.history.return_value = pd.DataFrame()

        def ticker_side_effect(t):
            return {"BUENO.MX": mock_bueno, "MALO.MX": mock_malo}.get(t, MagicMock())

        with patch.object(market.yf, "download", side_effect=Exception("fail")):
            with patch.object(market.yf, "Ticker", side_effect=ticker_side_effect):
                result = market.obtener_multiples_precios(["BUENO.MX", "MALO.MX"])

        assert result.get("BUENO.MX") == 100.0
        assert result.get("MALO.MX") is None


# ============= excluir_ticker / TICKERS_INVALIDOS =============


class TestExcluirTicker:
    def test_excluir_ticker_lo_agrega_al_set(self):
        assert "MALA.MX" not in market.TICKERS_INVALIDOS
        market.excluir_ticker("MALA.MX")
        assert "MALA.MX" in market.TICKERS_INVALIDOS

    def test_excluir_ticker_lo_persiste(self, tmp_path):
        ruta_excl = tmp_path / "tickers_excluidos.json"
        with patch.object(market, "_RUTA_EXCLUIDOS", str(ruta_excl)):
            market.excluir_ticker("MALA.MX")
            import json
            with open(ruta_excl) as f:
                data = json.load(f)
            assert "MALA.MX" in data

    def test_cargar_excluidos_al_iniciar(self, tmp_path):
        import json
        ruta_excl = tmp_path / "tickers_excluidos.json"
        with open(ruta_excl, "w") as f:
            json.dump(["MALA1.MX", "MALA2.MX"], f)

        with patch.object(market, "_RUTA_EXCLUIDOS", str(ruta_excl)):
            market.TICKERS_INVALIDOS.clear()
            market._cargar_excluidos()
            assert "MALA1.MX" in market.TICKERS_INVALIDOS
            assert "MALA2.MX" in market.TICKERS_INVALIDOS


# ============= obtener_historial =============


class TestObtenerHistorial:
    def test_historial_exitoso(self):
        idx = pd.to_datetime(["2026-07-07", "2026-07-08"])
        mock_hist = pd.DataFrame({
            "Close": [100.0, 101.0],
            "Volume": [1000, 1100],
        }, index=idx)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            historial = market.obtener_historial("FMTY14.MX", periodo="5d")

        assert len(historial) == 2
        assert historial[0]["close"] == 100.0
        assert historial[1]["volume"] == 1100

    def test_historial_vacio_devuelve_lista_vacia(self):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            historial = market.obtener_historial("FMTY14.MX")

        assert historial == []

    def test_historial_ticker_invalido_devuelve_vacio(self):
        market.excluir_ticker("MALA.MX")
        assert market.obtener_historial("MALA.MX") == []

    def test_historial_sic_aplica_tipo_cambio(self):
        idx = pd.to_datetime(["2026-07-07", "2026-07-08"])
        mock_hist = pd.DataFrame({
            "Close": [100.0, 101.0],
            "Volume": [1000, 1100],
        }, index=idx)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist

        with patch.object(market.yf, "Ticker", return_value=mock_ticker):
            with patch.object(market, "_obtener_tipo_cambio", return_value=20.0):
                historial = market.obtener_historial("AAPL", periodo="5d")

        assert len(historial) == 2
        assert historial[0]["close"] == 2000.0  # 100 USD * 20
        assert historial[1]["close"] == 2020.0  # 101 USD * 20
