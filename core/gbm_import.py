import json
import os
import re
import subprocess
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

def _clean_ticker(ticker: str, es_sic: bool = False) -> tuple[str, str, str]:
    t = ticker.upper()
    if t.startswith("1"):
        t = t[1:]
    if t.endswith("*"):
        t = t[:-1]

    if "FMTY" in t:
        return "FMTY14", "FIBRA", "FMTY14.MX"
    if "FUNO" in t:
        return "FUNO11", "FIBRA", "FUNO11.MX"
    if "FIPRA" in t:
        return "FIPRA14", "FIBRA", "FIPRA14.MX"
    if "IVVPESO" in t:
        return "IVVPESO", "ETF", "IVVPESO.MX"

    if es_sic:
        _SIC_MAP = {"BABAN": "BABA"}
        t = _SIC_MAP.get(t, t)
        return t, "SIC", t
    return t, "ACCION", f"{t}.MX"


def _parse_decimal(val_str: str) -> float | None:
    try:
        clean = val_str.replace("$", "").replace(",", "").strip()
        if not clean:
            return None
        return float(Decimal(clean))
    except (InvalidOperation, ValueError):
        return None


def _extract_numbers(line: str) -> list[tuple[str, int]]:
    matches = []
    for m in re.finditer(r"-?\$?\d+(?:,\d{3})*(?:\.\d+)?", line):
        matches.append((m.group(), m.start()))
    return matches


_MESES_MAP = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11, "DICIEMBRE": 12,
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
}


def _parse_period(text: str) -> tuple[str, str, str]:
    lines = text.split("\n")
    month_label = ""
    period_start = ""
    period_end = ""
    
    for line in lines:
        upper = line.upper()
        if "DEL" in upper and "AL" in upper:
            m = re.search(r"DEL\s+(\d{2}/\d{2}/\d{4})\s+AL\s+(\d{2}/\d{2}/\d{4})", upper)
            if m:
                d_start = datetime.strptime(m.group(1), "%d/%m/%Y").date()
                d_end = datetime.strptime(m.group(2), "%d/%m/%Y").date()
                period_start = d_start.isoformat()
                period_end = d_end.isoformat()
                month_label = d_start.strftime("%Y-%m")
                break
            m2 = re.search(r"DEL\s+(\d+)\s+AL\s+(\d+)\s+DE\s+(\w+)\s+DE\s+(\d{4})", upper)
            if m2:
                mes_num = _MESES_MAP.get(m2.group(3))
                if mes_num:
                    anio = int(m2.group(4))
                    month_label = f"{anio:04d}-{mes_num:02d}"
                    import calendar
                    ultimo_dia = calendar.monthrange(anio, mes_num)[1]
                    period_start = f"{anio:04d}-{mes_num:02d}-01"
                    period_end = f"{anio:04d}-{mes_num:02d}-{ultimo_dia}"
                    break
    return month_label, period_start, period_end


def _parse_posiciones_table(lines: list[str], es_sic: bool = False) -> list[dict]:
    posiciones = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^EMISORA", stripped):
            continue
        if re.match(r"^(TOTAL|Total|Subtotal):", stripped):
            continue
        if not re.search(r"\d", stripped):
            continue

        nums = _extract_numbers(stripped)
        if len(nums) < 10:
            continue

        data_vals = nums[-10:]
        first_data_pos = data_vals[0][1]
        emisora_raw = stripped[:first_data_pos].strip().rstrip("*").strip()

        ticker_name = re.sub(r"\s+", "", emisora_raw)
        try:
            titulos_actual = int(data_vals[1][0].replace(",", ""))
        except ValueError:
            continue
        if titulos_actual <= 0:
            continue

        costo_promedio = _parse_decimal(data_vals[3][0])
        costo_total = _parse_decimal(data_vals[4][0])
        valor_mercado = _parse_decimal(data_vals[7][0])

        ticker, tipo, yahoo = _clean_ticker(ticker_name, es_sic=es_sic)

        pos = {
            "ticker": ticker,
            "ticker_yahoo": yahoo,
            "tipo": tipo,
            "titulos": titulos_actual,
            "precio_promedio_mxn": costo_promedio or 0,
        }
        if costo_total is not None:
            pos["costo_total_mxn"] = costo_total
        if valor_mercado is not None:
            pos["valor_mercado_mxn"] = valor_mercado

        posiciones.append(pos)

    return posiciones


def _parse_deuda_lines(lines: list[str]) -> list[dict]:
    posiciones = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^EMISORA", stripped):
            continue
        if re.match(r"^(TOTAL|Total):", stripped):
            continue
        if not re.search(r"\d", stripped):
            continue

        nums = _extract_numbers(stripped)
        if len(nums) < 10:
            continue

        data_vals = nums[-10:]
        first_data_pos = data_vals[0][1]
        emisora_raw = stripped[:first_data_pos].strip().rstrip("*").strip()
        ticker = re.sub(r"\s+", "", emisora_raw)

        try:
            titulos_actual = int(data_vals[1][0].replace(",", ""))
        except ValueError:
            continue
        if titulos_actual <= 0:
            continue

        valor_repo = _parse_decimal(data_vals[7][0])

        pos = {
            "ticker": ticker,
            "ticker_yahoo": ticker,
            "tipo": "DEUDA",
            "titulos": titulos_actual,
            "precio_promedio_mxn": 0,
        }
        if valor_repo is not None:
            pos["valor_mercado_mxn"] = valor_repo

        posiciones.append(pos)

    return posiciones


def parse_pdf(filepath: str) -> dict | None:
    if not os.path.exists(filepath):
        return {"error": f"Archivo no encontrado: {filepath}"}

    result = subprocess.run(
        ["pdftotext", "-layout", filepath, "-"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {"error": f"Error al leer PDF: {result.stderr}"}

    text = result.stdout
    lines = text.split("\n")

    account_number = ""
    for line in lines:
        m = re.search(r"Contrato:\s*(\S+)", line)
        if m:
            account_number = m.group(1)
            break

    month_label, period_start, period_end = _parse_period(text)

    efectivo = 0.0
    for line in lines:
        if "EFECTIVO MISMO DIA" in line.upper():
            nums = _extract_numbers(line)
            if nums:
                efectivo = _parse_decimal(nums[0][0]) or 0.0
            break

    accion_lines = []
    sic_lines = []
    deuda_lines = []
    current_section = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if re.match(r"^ACCIONES\b", stripped) and "DEL SIC" not in stripped.upper():
            current_section = "NACIONAL"
            continue
        if "ACCIONES DEL SIC" in stripped.upper():
            current_section = "SIC"
            continue
        if re.match(r"^DEUDA\b", stripped):
            current_section = "DEUDA"
            continue

        if re.match(r"^(TOTAL|Total):", stripped) and current_section:
            current_section = None
            continue

        if current_section == "DEUDA":
            deuda_lines.append(stripped)
        elif current_section == "SIC":
            sic_lines.append(stripped)
        elif current_section == "NACIONAL":
            accion_lines.append(stripped)

    posiciones = _parse_posiciones_table(accion_lines)
    posiciones += _parse_posiciones_table(sic_lines, es_sic=True)
    posiciones += _parse_deuda_lines(deuda_lines)

    if not posiciones:
        return {"error": "No se pudieron extraer posiciones del PDF"}

    total_portfolio = sum(
        p.get("valor_mercado_mxn") or (p.get("precio_promedio_mxn", 0) * p.get("titulos", 0))
        for p in posiciones
    )

    return {
        "fecha_snapshot": date.today().isoformat(),
        "efectivo_mxn": round(efectivo, 2),
        "posiciones": posiciones,
        "capital_ficticio_disponible_mxn": round(total_portfolio + efectivo, 2),
        "cuenta": account_number,
        "_month_label": month_label,
        "_period_start": period_start,
        "_period_end": period_end,
    }


def import_excel(filepath: str) -> dict:
    """Importa un archivo Excel (.xlsx) de GBM con la posición actual."""
    import pandas as pd
    try:
        df = pd.read_excel(filepath)
    except Exception as ex:
        return {"error": f"No se pudo leer el Excel: {ex}"}

    df.columns = [str(c).strip().upper() for c in df.columns]
    posibles_ticker = ["TICKER", "SIMBOLO", "EMISORA", "INSTRUMENTO", "CLAVE"]
    posibles_titulos = ["TITULOS", "CANTIDAD", "QTY", "CANT", "POSICION"]
    posibles_precio = ["PRECIO PROMEDIO", "PRECIO PROM", "PRECIO PROMEDIO MXN",
                       "COSTO PROMEDIO", "P.PROMEDIO", "PP"]
    posibles_efectivo = ["EFECTIVO", "DISPONIBLE", "CAJA", "SALDO"]

    col_ticker = next((c for c in df.columns if any(p in c for p in posibles_ticker)), None)
    col_titulos = next((c for c in df.columns if any(p in c for p in posibles_titulos)), None)
    col_precio = next((c for c in df.columns if any(p in c for p in posibles_precio)), None)

    if not col_ticker or not col_titulos:
        return {"error": f"No se encontraron columnas de ticker/títulos en el Excel. "
                         f"Columnas detectadas: {list(df.columns)}"}

    posiciones = []
    for _, row in df.iterrows():
        ticker = str(row[col_ticker]).strip().upper()
        if not ticker or ticker == "NAN" or pd.isna(row[col_ticker]):
            continue
        try:
            titulos = int(float(row[col_titulos]))
        except (ValueError, TypeError):
            continue
        if titulos <= 0:
            continue
        precio = float(row[col_precio]) if col_precio and pd.notna(row.get(col_precio)) else 0.0

        es_sic = ticker.endswith("*") or ticker.startswith("1") or any(
            kw in ticker for kw in ["UBER", "AAPL", "MSFT", "GOOGL", "META", "NVDA", "TSLA"]
        )
        ticker_clean, tipo, ticker_yahoo = _clean_ticker(ticker, es_sic=es_sic)

        posiciones.append({
            "ticker": ticker_clean,
            "ticker_yahoo": ticker_yahoo,
            "tipo": tipo,
            "titulos": titulos,
            "precio_promedio_mxn": round(precio, 6),
            "costo_total_mxn": round(titulos * precio, 2),
        })

    if not posiciones:
        return {"error": "No se pudieron extraer posiciones del Excel"}

    efectivo_col = next((c for c in df.columns if any(p in c for p in posibles_efectivo)), None)
    efectivo = float(df[efectivo_col].iloc[0]) if efectivo_col else 0.0

    total_pos = sum(p["costo_total_mxn"] for p in posiciones)
    hoy = date.today()
    month_label = hoy.strftime("%Y-%m")
    period_start = hoy.replace(day=1).isoformat()
    period_end = hoy.isoformat()

    return {
        "fecha_snapshot": hoy.isoformat(),
        "efectivo_mxn": round(efectivo, 2),
        "posiciones": posiciones,
        "capital_ficticio_disponible_mxn": round(total_pos + efectivo, 2),
        "cuenta": "GBM",
        "_month_label": month_label,
        "_period_start": period_start,
        "_period_end": period_end,
    }


def import_file(filepath: str) -> dict:
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".pdf":
        result = parse_pdf(filepath)
    elif ext in (".xlsx", ".xls"):
        result = import_excel(filepath)
    else:
        return {"error": f"Formato no soportado: {ext}. Solo se admite .pdf y .xlsx"}

    if result is None:
        return {"error": "No se pudo procesar el archivo"}
    if isinstance(result, dict) and "error" in result:
        return result

    return result


def persist_import(filepath: str, parsed_data: dict) -> dict:
    from core.storage import (
        guardar_importacion, file_hash, obtener_historial_importaciones,
        obtener_mes_anterior,
        guardar_acciones_mensuales, calcular_cambios_entre_meses,
        registrar_evento, buscar_importacion_por_hash,
    )
    from core.simulator import SNAPSHOT_PATH

    fhash = file_hash(filepath)
    existente = buscar_importacion_por_hash(fhash)
    if existente:
        return {"error": f"Este archivo ya fue importado ({existente['month_label']})", "_duplicate": True}

    month_label = parsed_data.get("_month_label") or ""
    account = parsed_data.get("cuenta", "UNKNOWN")

    if month_label:
        historial = obtener_historial_importaciones(limit=200)
        for h in historial:
            if h["month_label"] == month_label and h.get("account", "") == account:
                return {"error": f"Ya existe una importación para {month_label}", "_duplicate": True}

    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(parsed_data, f, indent=2, ensure_ascii=False)

    import_id = guardar_importacion(
        filename=filepath,
        account=account,
        month_label=month_label,
        period_start=parsed_data.get("_period_start", ""),
        period_end=parsed_data.get("_period_end", ""),
        file_hash=fhash,
        efectivo_mxn=parsed_data.get("efectivo_mxn", 0),
        capital_total=parsed_data.get("capital_ficticio_disponible_mxn", 0.0),
        posiciones=parsed_data.get("posiciones", []),
    )

    prev = obtener_mes_anterior(account, month_label)
    if prev:
        prev_snapshot = prev["snapshot"]
        acciones = calcular_cambios_entre_meses(prev_snapshot, parsed_data)
        guardar_acciones_mensuales(import_id, month_label, acciones)

        for acc in acciones:
            ganancia = acc.get("ganancia_perdida", 0)
            notas = f"Mes {month_label}"
            if acc["tipo_accion"] == "VENTA" and ganancia != 0:
                notas += f" | {'Ganancia' if ganancia > 0 else 'Pérdida'}: ${abs(ganancia):,.2f}"
            registrar_evento(
                tipo=acc["tipo_accion"],
                ticker=acc["ticker"],
                titulos=acc["titulos"],
                precio_unitario=acc["precio_mxn"],
                monto_total=acc["monto_total"],
                notas=notas,
            )

    return parsed_data
