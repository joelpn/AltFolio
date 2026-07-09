# AltFolio — Suite de pruebas

## Ejecucion

```bash
# Desde la raiz del proyecto
source venv/bin/activate
pytest

# Con cobertura
pytest --cov=core --cov-report=term-missing

# Solo tests unitarios (sin integracion)
pytest -m "not integration"

# Solo tests de integracion
pytest -m integration

# Sin tests lentos
pytest -m "not slow"
```

## Estructura

| Archivo | Contenido |
|---|---|
| `test_storage.py` | CRUD SQLite: eventos, precios_cache, imported_statements, precios_historicos, acciones_mensuales |
| `test_simulator.py` | Simulador: carga, inyeccion, compra, venta |
| `test_gbm_import.py` | Parseo unitario: _clean_ticker, _parse_decimal, _parse_posiciones_table, import_excel, persist_import |
| `test_gbm_import_integration.py` | Integracion con pdftotext real y PDF sintetico |
| `test_history.py` | Capa de consulta historica: KPI, curva, calendario, restauracion |
| `test_market.py` | Market con yfinance mockeado: obtener_precio, batch, TICKERS_INVALIDOS |

## Convenciones

- **Aislamiento completo**: usar `tmp_path` + `monkeypatch` en `DB_PATH`, `SNAPSHOT_PATH` (ambos `core.simulator` y `core.history`), `CONFIG_PATH`. Nunca tocar `data/portfolio.db` ni `snapshot.json`.
- **Mock yfinance**: todas las llamadas a yfinance deben mockearse. Usar `unittest.mock.patch`.
- **TICKERS_INVALIDOS**: cada test debe limpiar este set (el `conftest` lo hace via `_limpiar_tickers_invalidos`).
- **UI excluida**: `ui/` no tiene tests (Flet testing es un concern separado).

## Marcadores

- `integration` — requiere pdftotext o reportlab
- `slow` — pruebas lentas (ej. generacion de PDF sintetico)

## Dependencias extra (solo tests)

```
pytest
pytest-cov
pytest-mock
reportlab      # solo para tests de integracion
```
