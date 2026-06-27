# AltFolio

*Tu portafolio alternativo — paper trading local que espejea tu cuenta GBM real.*

AltFolio es una sandbox de paper trading 100% local. Importa estados de cuenta GBM (PDF), reconstruye el historial de tu portafolio y te permite navegar mes a mes para ver cómo evolucionaron tus posiciones. Todo corre en tu máquina — cero datos enviados a la nube.

## Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12+ |
| UI | Flet (nativa) |
| Precios | yfinance |
| Persistencia | SQLite |
| Cálculos | pandas |

## Requisitos

- Python 3.12+
- `pdftotext` (para importar PDF de GBM):
  ```bash
  # Ubuntu/Debian
  sudo apt install poppler-utils
  # macOS
  brew install poppler
  ```

## Instalación

```bash
git clone https://github.com/tu-usuario/altfolio.git
cd altfolio
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

### Importar estado de cuenta

1. Descarga tu estado de cuenta GBM en PDF desde la plataforma.
2. En AltFolio, haz clic en **Carga Archivo** y selecciona el PDF.
3. El portafolio se cargará automáticamente y podrás ver las posiciones.

### Navegar historial

Usa el selector de año/mes para ver instantáneas anteriores. AltFolio detecta automáticamente compras y ventas entre meses consecutivos.

### Actualizar precios

Haz clic en **Actualizar Datos** para obtener precios en vivo vía yfinance. La app también se actualiza automáticamente cada 60 segundos.

## Estructura

```
altfolio/
├── main.py                   # Entry point
├── config.json               # Parámetros (comisiones, etc.)
├── core/
│   ├── storage.py            # CRUD SQLite
│   ├── market.py             # yfinance connector
│   ├── simulator.py          # Motor de simulación
│   ├── history.py            # Historial de importaciones
│   └── gbm_import.py         # Importador PDF GBM
└── ui/
    ├── dashboard.py          # Vista principal
    ├── charts.py             # PieChart y BarChart
    └── controls.py           # Panel de importación
```

## Configuración

`config.json` permite ajustar:

- `comision_gbm_pct` — comisión por operación (default: 0.25%)
- `spread_sic_pct` — spread estimado SIC (default: 0.50%)
- `moneda_base` — moneda base (default: MXN)
- `intervalo_actualizacion_precios_seg` — frecuencia de actualización (default: 60)

## Licencia

MIT
