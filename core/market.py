import contextlib
import io
import json
import logging
import os
import warnings
import yfinance as yf
import pandas as pd

warnings.filterwarnings("ignore", message=".*possibly delisted.*")
for _logger in ("yfinance", "yfinance.ticker", "yfinance.utils",
                "urllib3", "urllib3.connectionpool", "requests"):
    logging.getLogger(_logger).setLevel(logging.ERROR)
    logging.getLogger(_logger).propagate = False


TICKERS_INVALIDOS: set[str] = set()

TIPO_CAMBIO_CACHE: dict = {"rate": None, "timestamp": 0.0}
CACHE_TTL = 300  # 5 minutos

_RUTA_EXCLUIDOS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "tickers_excluidos.json",
)


def _cargar_excluidos():
    global TICKERS_INVALIDOS
    try:
        if os.path.exists(_RUTA_EXCLUIDOS):
            with open(_RUTA_EXCLUIDOS) as f:
                datos = json.load(f)
            if isinstance(datos, list):
                TICKERS_INVALIDOS = set(datos)
    except Exception:
        pass


def _guardar_excluidos():
    os.makedirs(os.path.dirname(_RUTA_EXCLUIDOS), exist_ok=True)
    with open(_RUTA_EXCLUIDOS, "w") as f:
        json.dump(sorted(TICKERS_INVALIDOS), f, indent=2)


def excluir_ticker(ticker: str):
    TICKERS_INVALIDOS.add(ticker)
    _guardar_excluidos()


_cargar_excluidos()


def _call_silent(fn, *args, **kwargs):
    null = io.StringIO()
    with contextlib.redirect_stderr(null), contextlib.redirect_stdout(null):
        return fn(*args, **kwargs)


def _es_sic(ticker_yahoo: str) -> bool:
    """Detecta si un ticker de Yahoo Finance es SIC (cotiza en USD)."""
    if ticker_yahoo.endswith(".MX") or ticker_yahoo.endswith("=X"):
        return False
    return True


def _obtener_tipo_cambio() -> float:
    """Devuelve USD/MXN, cachead0 5 min."""
    import time
    ahora = time.time()
    if TIPO_CAMBIO_CACHE["rate"] is not None and (ahora - TIPO_CAMBIO_CACHE["timestamp"]) < CACHE_TTL:
        return TIPO_CAMBIO_CACHE["rate"]
    try:
        mxn = yf.Ticker("MXN=X")
        hist = _call_silent(mxn.history, period="1d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
        else:
            hist = _call_silent(mxn.history, period="5d")
            rate = float(hist["Close"].iloc[-1]) if not hist.empty else 20.0
    except Exception:
        rate = 20.0
    TIPO_CAMBIO_CACHE["rate"] = rate
    TIPO_CAMBIO_CACHE["timestamp"] = ahora
    return rate


def obtener_precio(ticker_yahoo):
    if ticker_yahoo in TICKERS_INVALIDOS:
        raise ValueError(f"Ticker inválido: {ticker_yahoo}")
    ticker = yf.Ticker(ticker_yahoo)
    for period in ("1d", "5d", "1mo"):
        hist = _call_silent(ticker.history, period=period)
        if not hist.empty:
            px = float(hist["Close"].iloc[-1])
            if _es_sic(ticker_yahoo):
                px *= _obtener_tipo_cambio()
            return px
    raise ValueError(f"No se pudo obtener precio para {ticker_yahoo}")


def obtener_multiples_precios(tickers, batch=True):
    if not tickers:
        return {}
    tickers_validos = [t for t in tickers if t and t not in TICKERS_INVALIDOS]
    result = {}
    fallback = set(tickers_validos)

    if batch and len(tickers_validos) > 1:
        try:
            data = _call_silent(
                yf.download, tickers_validos, period="1d", progress=False,
            )
            sic_tickers = [t for t in tickers if _es_sic(t)]
            if sic_tickers:
                tc = _obtener_tipo_cambio()
            else:
                tc = 1.0
            if "Close" in data.columns:
                for t in tickers:
                    try:
                        val = data["Close"][t].iloc[-1]
                        result[t] = float(val) if not pd.isna(val) else None
                        if result[t] is not None and t in fallback:
                            fallback.remove(t)
                        if result[t] is not None and _es_sic(t):
                            result[t] *= tc
                    except (IndexError, KeyError):
                        result[t] = None
            elif not data.empty:
                for t in tickers:
                    try:
                        val = data.xs(t, axis=1, level=1)["Close"].iloc[-1]
                        result[t] = float(val) if not pd.isna(val) else None
                        if result[t] is not None and t in fallback:
                            fallback.remove(t)
                        if result[t] is not None and _es_sic(t):
                            result[t] *= tc
                    except (IndexError, KeyError):
                        result[t] = None
            else:
                for t in tickers:
                    result[t] = None
        except Exception:
            pass

    for t in tickers:
        result.setdefault(t, None)

    for ticker in list(fallback):
        try:
            px = obtener_precio(ticker)
            result[ticker] = px
        except Exception:
            result[ticker] = None

    return result


def obtener_historial(ticker_yahoo, periodo="1mo"):
    if ticker_yahoo in TICKERS_INVALIDOS:
        return []
    ticker = yf.Ticker(ticker_yahoo)
    hist = _call_silent(ticker.history, period=periodo)
    if hist.empty:
        return []
    es_sic = _es_sic(ticker_yahoo)
    tc = _obtener_tipo_cambio() if es_sic else 1.0
    return [
        {"fecha": str(idx.date()), "close": float(row["Close"]) * tc, "volume": int(row["Volume"])}
        for idx, row in hist.iterrows()
    ]



