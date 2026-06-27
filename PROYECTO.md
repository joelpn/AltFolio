# Contexto del Proyecto: AltFolio

## Propósito

Sandbox de paper trading local que replica un portafolio real de GBM (Grupo Bolsa
Mexicana). Permite importar estados de cuenta mensuales (PDF), navegar el historial
de posiciones mes a mes, y consultar precios actuales vía yfinance.

## Arquitectura

```
Flet UI (dashboard.py, charts.py, controls.py)
    ↓ llama a métodos del
Simulador (core/simulator.py)
    ↓ lee/escribe
SQLite (core/storage.py)  ←  yfinance (core/market.py)
    ↑
Importador PDF (core/gbm_import.py)
```

## Módulos

### core/storage.py
CRUD SQLite con 5 tablas:
- `eventos` — bitácora de operaciones simuladas
- `precios_cache` — caché de precios intradía
- `imported_statements` — metadatos de cada importación
- `historical_prices` — histórico de precios diarios
- `acciones_mensuales` — compras/ventas detectadas entre meses

Funciones clave: `init_db()`, `guardar_importacion()`, `calcular_cambios_entre_meses()`

### core/market.py
Wrapper sobre yfinance:
- `obtener_precio(ticker)` — precio único con fallback de períodos
- `obtener_multiples_precios(tickers)` — batch con yf.download + fallback individual
- Mantiene `TICKERS_INVALIDOS` global para evitar reintentos

### core/simulator.py
Motor de simulación. Clase `Simulador`:
- `__init__()` — carga snapshot (XML>PDF>snapshot.json>vacío)
- `inyectar_capital(monto)` — agrega efectivo ficticio
- `simular_compra(ticker, titulos, precio)` — con comisión
- `simular_venta(ticker, titulos, precio)` — con comisión y cálculo de ganancia

### core/history.py
Capa de consulta histórica:
- `listar_importaciones()` — wrappea `obtener_historial_importaciones()`
- `restaurar_snapshot(import_id)` — escribe snapshot.json desde DB
- `actualizar_precios_historicos(tickers)` — cachea precios diarios

### core/gbm_import.py
Importador de estados de cuenta GBM desde PDF:
- Usa `pdftotext -layout` para extraer texto
- `_clean_ticker()` — normaliza tickers a formato Yahoo Finance (.MX)
- `_parse_posiciones_table()` — extrae posiciones de acciones
- `_parse_deuda_lines()` — extrae posiciones de deuda
- `persist_import()` — guarda en DB, detecta cambios vs mes anterior

### ui/dashboard.py
Clase `Dashboard` y función `build_dashboard()`:
- Panel izquierdo: lista de posiciones con precios en vivo
- Panel derecho: gráfico de distribución (pastel/barras) + movimientos mensuales
- Selector histórico: navegación por año/mes
- Temporizador: actualización automática cada N segundos
- Overlay de carga con spinner

### ui/charts.py
Gráficos Flet nativos:
- `build_pie_chart()` — PieChart con sectores por ticker
- `build_bar_chart()` — BarChart horizontal

### ui/controls.py
Componentes reutilizables:
- `build_import_panel()` — selector de archivos PDF + procesamiento batch

## Flujo de datos

```
PDF GBM
    ↓ pdftotext
Texto plano
    ↓ _parse_posiciones_table / _parse_deuda_lines
dict con posiciones
    ↓ persist_import()
SQLite (imported_statements + acciones_mensuales)
    ↓ Simulador.__init__()
Simulador.posiciones (dict en memoria)
    ↓ obtener_multiples_precios() [yfinance]
Dashboard._refresh_with_data() → UI
```

## Configuración

`config.json`:
```json
{
  "comision_gbm_pct": 0.25,
  "spread_sic_pct": 0.50,
  "limite_minimo_titulos": 1,
  "moneda_base": "MXN",
  "intervalo_actualizacion_precios_seg": 60
}
```

## Snapshot (snapshot.json)

Contiene el estado del portafolio en un momento dado:
- `efectivo_mxn` — efectivo disponible
- `posiciones[]` — lista de posiciones con ticker, Yahoo ticker, tipo, titulos, precios
- `capital_ficticio_disponible_mxn` — capital total
- Metadatos: cuenta, mes, período

## Convenciones

- Código en español (nombres de funciones, variables, comentarios)
- Precios en MXN
- Tickers con sufijo `.MX` para Yahoo Finance (excepto deuda)
- Fechas en ISO 8601
- SQLite con WAL mode
- Conexiones se abren/cierran en cada operación (sin pool)

## Dependencias

- `flet>=0.21.0,<0.24.0` — UI nativa multiplataforma
- `python-dotenv` — carga de .env
- `yfinance` — precios del mercado
- `pandas` — manipulación de datos (usado internamente por yfinance)
- `pdftotext` (binario externo del paquete `poppler-utils`)

## Archivos ignorados (gitignore)

- `venv/`, `.venv/` — entornos virtuales
- `.local/` — librerías locales (libmpv.so)
- `data/*.db*` — base de datos SQLite con datos del portafolio
- `snapshot.json` — instantánea con datos financieros reales
- `files/` — estados de cuenta PDF con PII
- `.env` — variables de entorno
- `.agents/`, `AGENTS.md`, `skills-lock.json` — configuración de opencode
