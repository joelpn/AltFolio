import hashlib
import json
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS eventos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL,
            tipo            TEXT NOT NULL,
            ticker          TEXT,
            titulos         REAL,
            precio_unitario REAL,
            monto_total     REAL,
            efectivo_post   REAL,
            notas           TEXT
        );

        CREATE TABLE IF NOT EXISTS precios_cache (
            ticker        TEXT PRIMARY KEY,
            precio_mxn    REAL,
            ultimo_update TEXT
        );

        CREATE TABLE IF NOT EXISTS imported_statements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filename        TEXT NOT NULL,
            account         TEXT NOT NULL DEFAULT '',
            month_label     TEXT NOT NULL,
            period_start    TEXT,
            period_end      TEXT,
            file_hash       TEXT NOT NULL,
            efectivo_mxn    REAL DEFAULT 0,
            capital_total   REAL DEFAULT 0,
            num_posiciones  INTEGER DEFAULT 0,
            snapshot_json   TEXT NOT NULL,
            imported_at     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS historical_prices (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker   TEXT NOT NULL,
            fecha    TEXT NOT NULL,
            precio   REAL NOT NULL,
            UNIQUE(ticker, fecha)
        );

        CREATE INDEX IF NOT EXISTS idx_imported_month
            ON imported_statements(month_label);
        CREATE INDEX IF NOT EXISTS idx_imported_account
            ON imported_statements(account);
        CREATE INDEX IF NOT EXISTS idx_hp_ticker
            ON historical_prices(ticker);

        CREATE TABLE IF NOT EXISTS acciones_mensuales (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            import_id       INTEGER NOT NULL,
            month_label     TEXT NOT NULL,
            ticker          TEXT NOT NULL,
            tipo_accion     TEXT NOT NULL,
            titulos         INTEGER NOT NULL,
            precio_mxn      REAL NOT NULL,
            monto_total     REAL NOT NULL,
            ganancia_perdida REAL DEFAULT 0,
            FOREIGN KEY (import_id) REFERENCES imported_statements(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_acciones_import
            ON acciones_mensuales(import_id);
    """)
    conn.commit()
    conn.close()


def registrar_evento(tipo, ticker=None, titulos=None, precio_unitario=None,
                     monto_total=None, efectivo_post=None, notas=None):
    conn = get_connection()
    conn.execute("""
        INSERT INTO eventos (timestamp, tipo, ticker, titulos, precio_unitario,
                             monto_total, efectivo_post, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (datetime.now().isoformat(), tipo, ticker, titulos, precio_unitario,
          monto_total, efectivo_post, notas))
    conn.commit()
    conn.close()


def obtener_eventos(limit=50):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM eventos ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def guardar_precio_cache(ticker, precio_mxn):
    conn = get_connection()
    conn.execute("""
        INSERT INTO precios_cache (ticker, precio_mxn, ultimo_update)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            precio_mxn = excluded.precio_mxn,
            ultimo_update = excluded.ultimo_update
    """, (ticker, precio_mxn, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def obtener_precio_cache(ticker):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM precios_cache WHERE ticker = ?", (ticker,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def guardar_importacion(filename: str, account: str, month_label: str,
                        period_start: str, period_end: str, file_hash: str,
                        efectivo_mxn: float, capital_total: float,
                        posiciones: list) -> int:
    snapshot = {
        "fecha_snapshot": datetime.now().isoformat(),
        "efectivo_mxn": efectivo_mxn,
        "capital_ficticio_disponible_mxn": capital_total,
        "posiciones": posiciones,
        "_filename": filename,
        "_month": month_label,
    }
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO imported_statements
            (filename, account, month_label, period_start, period_end,
             file_hash, efectivo_mxn, capital_total, num_posiciones,
             snapshot_json, imported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        filename, account, month_label, period_start, period_end,
        file_hash, efectivo_mxn, capital_total, len(posiciones),
        json.dumps(snapshot), datetime.now().isoformat(),
    ))
    import_id = cur.lastrowid
    conn.commit()
    conn.close()
    return import_id


def buscar_importacion_por_hash(file_hash: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM imported_statements WHERE file_hash = ?", (file_hash,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_importacion_por_mes(account: str, month_label: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM imported_statements WHERE account = ? AND month_label = ?",
        (account, month_label),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_historial_importaciones(limit=50):
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, filename, account, month_label, period_start, period_end,
               efectivo_mxn, capital_total, num_posiciones, imported_at
        FROM imported_statements
        ORDER BY period_start DESC, imported_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obtener_snapshot_por_id(import_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT snapshot_json FROM imported_statements WHERE id = ?",
        (import_id,),
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["snapshot_json"])
    return None


def guardar_precio_historico(ticker: str, fecha: str, precio: float):
    conn = get_connection()
    conn.execute("""
        INSERT INTO historical_prices (ticker, fecha, precio)
        VALUES (?, ?, ?)
        ON CONFLICT(ticker, fecha) DO UPDATE SET precio = excluded.precio
    """, (ticker.upper(), fecha, precio))
    conn.commit()
    conn.close()


def obtener_precios_historicos(ticker: str, limit=30):
    conn = get_connection()
    rows = conn.execute("""
        SELECT fecha, precio FROM historical_prices
        WHERE ticker = ? ORDER BY fecha DESC LIMIT ?
    """, (ticker.upper(), limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def eliminar_importacion(import_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM acciones_mensuales WHERE import_id = ?", (import_id,))
    conn.execute("DELETE FROM imported_statements WHERE id = ?", (import_id,))
    conn.commit()
    conn.close()


def obtener_anios_disponibles(account: str = "") -> dict:
    """
    Devuelve un dict agrupado por año con los meses disponibles e import_id:
    {
      "2026": [
        {"month_label": "2026-01", "import_id": 3, "capital_total": 61143.66},
        {"month_label": "2026-02", "import_id": 4, "capital_total": 65000.00},
      ],
      ...
    }
    """
    conn = get_connection()
    if account:
        rows = conn.execute(
            """SELECT id, month_label, capital_total, period_start
               FROM imported_statements
               WHERE account = ?
               ORDER BY period_start ASC""",
            (account,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id, month_label, capital_total, period_start
               FROM imported_statements
               ORDER BY period_start ASC"""
        ).fetchall()
    conn.close()

    result = {}
    for row in rows:
        row = dict(row)
        month_label = row.get("month_label", "")
        if not month_label or "-" not in month_label:
            continue
        year = month_label.split("-")[0]
        result.setdefault(year, [])
        result[year].append({
            "month_label": month_label,
            "import_id": row["id"],
            "capital_total": row.get("capital_total", 0),
        })
    return result


def obtener_importacion_por_mes(account: str, month_label: str) -> dict | None:
    """Devuelve los metadatos de la importación para la cuenta y mes dados."""
    conn = get_connection()
    if account:
        row = conn.execute(
            """SELECT id, month_label, capital_total, num_posiciones, period_start, period_end
               FROM imported_statements
               WHERE account = ? AND month_label = ?""",
            (account, month_label),
        ).fetchone()
    else:
        row = conn.execute(
            """SELECT id, month_label, capital_total, num_posiciones, period_start, period_end
               FROM imported_statements
               WHERE month_label = ?
               ORDER BY imported_at DESC""",
            (month_label,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def obtener_mes_anterior(account: str, month_label: str) -> dict | None:
    """Devuelve la importación del mes inmediato anterior para la misma cuenta."""
    conn = get_connection()
    row = conn.execute(
        """SELECT id, month_label, snapshot_json
           FROM imported_statements
           WHERE account = ? AND month_label < ?
           ORDER BY month_label DESC LIMIT 1""",
        (account, month_label),
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot_json"])
        return result
    return None


def guardar_acciones_mensuales(import_id: int, month_label: str, acciones: list[dict]):
    """Guarda las acciones (compras/ventas) detectadas para un mes."""
    conn = get_connection()
    conn.execute("DELETE FROM acciones_mensuales WHERE import_id = ?", (import_id,))
    for acc in acciones:
        conn.execute("""
            INSERT INTO acciones_mensuales
                (import_id, month_label, ticker, tipo_accion, titulos,
                 precio_mxn, monto_total, ganancia_perdida)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            import_id, month_label,
            acc["ticker"], acc["tipo_accion"], acc["titulos"],
            acc["precio_mxn"], acc["monto_total"], acc.get("ganancia_perdida", 0),
        ))
    conn.commit()
    conn.close()


def obtener_acciones_por_import_id(import_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM acciones_mensuales WHERE import_id = ? ORDER BY tipo_accion, ticker",
        (import_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def calcular_cambios_entre_meses(prev_snapshot: dict, curr_snapshot: dict) -> list[dict]:
    """
    Compara dos snapshots mensuales y devuelve una lista de acciones:
    - COMPRA: cuando aparece un nuevo ticker o aumentan títulos
    - VENTA: cuando desaparece un ticker o disminuyen títulos
    """
    prev_pos = {p["ticker"]: p for p in prev_snapshot.get("posiciones", [])}
    curr_pos = {p["ticker"]: p for p in curr_snapshot.get("posiciones", [])}
    acciones = []

    for ticker, curr in curr_pos.items():
        if ticker not in prev_pos:
            accion = {
                "ticker": ticker,
                "tipo_accion": "COMPRA",
                "titulos": curr["titulos"],
                "precio_mxn": curr.get("precio_promedio_mxn", 0),
                "monto_total": curr["titulos"] * curr.get("precio_promedio_mxn", 0),
                "ganancia_perdida": 0,
            }
            acciones.append(accion)
        else:
            prev = prev_pos[ticker]
            diff = curr["titulos"] - prev["titulos"]
            if diff > 0:
                acciones.append({
                    "ticker": ticker,
                    "tipo_accion": "COMPRA",
                    "titulos": diff,
                    "precio_mxn": curr.get("precio_promedio_mxn", 0),
                    "monto_total": diff * curr.get("precio_promedio_mxn", 0),
                    "ganancia_perdida": 0,
                })
            elif diff < 0:
                precio_prom = prev.get("precio_promedio_mxn", 0)
                precio_est = (
                    (prev.get("valor_mercado_mxn", 0) / prev["titulos"])
                    if prev["titulos"] > 0 and prev.get("valor_mercado_mxn")
                    else precio_prom
                )
                ganancia = (precio_est - precio_prom) * abs(diff)
                acciones.append({
                    "ticker": ticker,
                    "tipo_accion": "VENTA",
                    "titulos": abs(diff),
                    "precio_mxn": precio_est,
                    "monto_total": abs(diff) * precio_est,
                    "ganancia_perdida": round(ganancia, 2),
                })

    for ticker, prev in prev_pos.items():
        if ticker not in curr_pos:
            precio_prom = prev.get("precio_promedio_mxn", 0)
            precio_est = (
                (prev.get("valor_mercado_mxn", 0) / prev["titulos"])
                if prev["titulos"] > 0 and prev.get("valor_mercado_mxn")
                else precio_prom
            )
            ganancia = (precio_est - precio_prom) * prev["titulos"]
            acciones.append({
                "ticker": ticker,
                "tipo_accion": "VENTA",
                "titulos": prev["titulos"],
                "precio_mxn": precio_est,
                "monto_total": prev["titulos"] * precio_est,
                "ganancia_perdida": round(ganancia, 2),
            })

    return acciones

