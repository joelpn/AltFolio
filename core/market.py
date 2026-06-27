import warnings
import yfinance as yf
import pandas as pd

warnings.filterwarnings("ignore", message=".*possibly delisted.*")


TICKERS_INVALIDOS = set()


def obtener_precio(ticker_yahoo):
    if ticker_yahoo in TICKERS_INVALIDOS:
        raise ValueError(f"Ticker inválido: {ticker_yahoo}")
    ticker = yf.Ticker(ticker_yahoo)
    for period in ("1d", "5d", "1mo"):
        hist = ticker.history(period=period)
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    TICKERS_INVALIDOS.add(ticker_yahoo)
    raise ValueError(f"No se pudo obtener precio para {ticker_yahoo}")


def obtener_multiples_precios(tickers, batch=True):
    if not tickers:
        return {}
    if batch and len(tickers) > 1:
        try:
            data = yf.download(
                [t for t in tickers if t],
                period="1d",
                progress=False,
            )
            result = {}
            if "Close" in data.columns:
                for t in tickers:
                    try:
                        val = data["Close"][t].iloc[-1]
                        result[t] = float(val) if not pd.isna(val) else None
                    except (IndexError, KeyError):
                        result[t] = None
            elif not data.empty:
                for t in tickers:
                    try:
                        val = data.xs(t, axis=1, level=1)["Close"].iloc[-1]
                        result[t] = float(val) if not pd.isna(val) else None
                    except (IndexError, KeyError):
                        result[t] = None
            else:
                for t in tickers:
                    result[t] = None
            return result
        except Exception:
            pass

    result = {}
    for ticker in tickers:
        try:
            result[ticker] = obtener_precio(ticker)
        except Exception:
            result[ticker] = None
    return result


def obtener_historial(ticker_yahoo, periodo="1mo"):
    ticker = yf.Ticker(ticker_yahoo)
    hist = ticker.history(period=periodo)
    if hist.empty:
        return []
    return [
        {"fecha": str(idx.date()), "close": float(row["Close"]), "volume": int(row["Volume"])}
        for idx, row in hist.iterrows()
    ]



