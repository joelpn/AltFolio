import base64
import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import mplfinance as mpf
import squarify
import flet as ft

COLORES = [
    "#58A6FF", "#3FB950", "#D29922", "#BC8CFF",
    "#F85149", "#56D4DD", "#A5D6A7", "#FFA657",
    "#79C0FF", "#7EE787", "#E3B341", "#D2A8FF",
]
FONDO = "#0D1117"
TEXTO = "#E6EDF3"
TEXTO_SEC = "#8B949E"
FONDO_AX = "#161B22"

plt.rcParams.update({
    "figure.facecolor": FONDO,
    "axes.facecolor": FONDO_AX,
    "axes.edgecolor": "#30363D",
    "axes.labelcolor": TEXTO_SEC,
    "text.color": TEXTO,
    "xtick.color": TEXTO_SEC,
    "ytick.color": TEXTO_SEC,
    "grid.color": "#21262D",
    "grid.alpha": 0.5,
    "font.size": 9,
    "axes.titlesize": 11,
    "axes.labelsize": 9,
})


def _fig_a_image(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=FONDO, edgecolor="none", transparent=False)
    buf.seek(0)
    plt.close(fig)
    return base64.b64encode(buf.read()).decode("utf-8")


def build_kpi_cards(kpis: dict) -> ft.Row:
    KPI_COLORS = {
        "Hoy": ft.colors.GREEN_400 if kpis["hoy_val"] >= 0 else ft.colors.RED_400,
        "Mes": ft.colors.GREEN_400 if kpis["mes_val"] >= 0 else ft.colors.RED_400,
        "YTD": ft.colors.GREEN_400 if kpis["ytd_val"] >= 0 else ft.colors.RED_400,
        "Total": ft.colors.GREEN_400 if kpis["total_val"] >= 0 else ft.colors.RED_400,
    }

    def _card(titulo, valor, pct, color):
        flecha = "▲" if pct >= 0 else "▼"
        signo = "+" if pct >= 0 else ""
        return ft.Container(
            content=ft.Column([
                ft.Text(titulo, size=10, color=TEXTO_SEC, weight=ft.FontWeight.W_500),
                ft.Text(f"${valor:,.0f}" if abs(valor) >= 1 else f"${valor:,.2f}",
                        size=17, weight=ft.FontWeight.BOLD, color=color),
                ft.Row([
                    ft.Text(f"{flecha}", size=11, color=color),
                    ft.Text(f"{signo}{pct:.2f}%", size=11, color=color),
                ], spacing=2, alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=FONDO_AX,
            border=ft.border.all(1, "#30363D"),
            border_radius=8,
            padding=ft.padding.symmetric(vertical=12, horizontal=8),
            expand=True,
        )

    return ft.Row([
        _card("Hoy", kpis["hoy_val"], kpis["hoy_pct"], KPI_COLORS["Hoy"]),
        _card("Mes", kpis["mes_val"], kpis["mes_pct"], KPI_COLORS["Mes"]),
        _card("YTD", kpis["ytd_val"], kpis["ytd_pct"], KPI_COLORS["YTD"]),
        _card("Total", kpis["total_val"], kpis["total_pct"], KPI_COLORS["Total"]),
    ], spacing=6)


def _build_equity_chart(puntos: list[dict], modo: str = "area") -> ft.Container:
    if not puntos:
        return ft.Container(ft.Text("Sin datos historicos", color=TEXTO_SEC))

    from flet import LineChart, LineChartData, LineChartDataPoint, ChartAxisLabel

    fechas = [datetime.strptime(p["fecha"], "%Y-%m-%d") for p in puntos]
    valores = [p["valor"] for p in puntos]
    min_v, max_v = min(valores), max(valores)
    rango = max_v - min_v or 1

    total = len(puntos)
    paso_etiqueta = max(1, total // 4)

    etiquetas = [
        ChartAxisLabel(
            value=i,
            label=ft.Container(
                ft.Text(f"{fechas[i].strftime('%b %Y')}", size=8, color=TEXTO_SEC, no_wrap=False),
                padding=ft.padding.only(top=2),
            ),
        )
        for i in range(0, total, paso_etiqueta)
    ]
    if etiquetas and etiquetas[-1].value != total - 1:
        etiquetas.append(
            ChartAxisLabel(
                value=total - 1,
                label=ft.Container(
                    ft.Text(f"{fechas[-1].strftime('%b %Y')}", size=8, color=TEXTO_SEC, no_wrap=False),
                    padding=ft.padding.only(top=2),
                ),
            )
        )

    if modo == "linea":
        datos = LineChartData(
            data_points=[
                LineChartDataPoint(x=i, y=v)
                for i, v in enumerate(valores)
            ],
            stroke_width=3,
            color="#58A6FF",
            curved=True,
            stroke_cap_round=True,
            below_line_bgcolor=None,
        )
    else:
        datos = LineChartData(
            data_points=[
                LineChartDataPoint(x=i, y=v)
                for i, v in enumerate(valores)
            ],
            stroke_width=2.5,
            color="#58A6FF",
            curved=True,
            stroke_cap_round=True,
            below_line_bgcolor=ft.colors.with_opacity(0.12, "#58A6FF"),
        )

    grafica = LineChart(
        data_series=[datos],
        border=ft.Border(bottom=ft.BorderSide(1, "#30363D")),
        left_axis=ft.ChartAxis(labels_size=55, labels_interval=rango / 5),
        bottom_axis=ft.ChartAxis(labels=etiquetas, labels_size=45),
        tooltip_bgcolor=ft.colors.with_opacity(0.85, "#161B22"),
        expand=True,
        min_y=min_v - rango * 0.05,
        max_y=max_v + rango * 0.05,
        interactive=True,
    )

    return ft.Container(content=grafica, padding=5, expand=True)


def build_area_chart(puntos: list[dict]) -> ft.Container:
    return _build_equity_chart(puntos, "area")


def build_line_chart(puntos: list[dict]) -> ft.Container:
    return _build_equity_chart(puntos, "linea")


def build_treemap(posiciones: dict, precios: dict) -> ft.Image:
    sectores = []
    for ticker, info in posiciones.items():
        precio = precios.get(ticker) or info.get("precio_promedio_mxn") or 0
        valor = info["titulos"] * precio
        if valor > 0:
            sectores.append((ticker, valor))

    if not sectores:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", color=TEXTO, fontsize=14)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        return ft.Image(src_base64=_fig_a_image(fig), fit=ft.ImageFit.CONTAIN)

    values = [s[1] for s in sectores]
    total = sum(values)
    labels = [f"{s[0]}\n${v:,.0f}\n({v/total*100:.1f}%)" for s, v in zip(sectores, values)]

    fig, ax = plt.subplots(figsize=(5.5, 4.5))
    colors = [COLORES[i % len(COLORES)] for i in range(len(sectores))]

    squarify.plot(sizes=values, label=labels, color=colors, alpha=0.85,
                  ax=ax, text_kwargs={"color": "white", "fontsize": 8, "fontweight": "bold"})
    ax.axis("off")
    ax.set_title("Distribucion del Portafolio", color=TEXTO, fontsize=11, pad=8)

    return ft.Image(src_base64=_fig_a_image(fig), fit=ft.ImageFit.CONTAIN)


def build_pnl_chart(rendimientos: list[dict]) -> ft.Image:
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    if not rendimientos:
        ax.text(0.5, 0.5, "Sin datos historicos", ha="center", va="center",
                color=TEXTO, fontsize=14, transform=ax.transAxes)
        return ft.Image(src_base64=_fig_a_image(fig), fit=ft.ImageFit.CONTAIN)

    etiquetas = [r["fecha"] for r in rendimientos]
    valores = [r["ganancia"] for r in rendimientos]
    colores = ["#3FB950" if v >= 0 else "#F85149" for v in valores]

    bars = ax.bar(etiquetas, valores, color=colores, width=0.6, edgecolor="none",
                  linewidth=0, zorder=3)
    ax.axhline(y=0, color="#30363D", linewidth=0.8, zorder=2)
    ax.set_ylabel("Ganancia / Perdida ($)", color=TEXTO_SEC)
    ax.set_title("Rendimientos Mensuales", color=TEXTO, fontsize=12, pad=8)

    ax.tick_params(axis="x", rotation=35, labelsize=8.5)
    ax.tick_params(axis="y", labelsize=9)

    max_abs = max(abs(v) for v in valores) if valores else 1
    ax.set_ylim(-max_abs * 1.35, max_abs * 1.35)

    for bar, v in zip(bars, valores):
        y = bar.get_height() + (max_abs * 0.06 if v >= 0 else -max_abs * 0.1)
        ax.text(bar.get_x() + bar.get_width() / 2, y, f"${v:,.0f}",
                ha="center", va="center", fontsize=7.5, color=TEXTO, fontweight="bold")

    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:,.0f}"))
    return ft.Image(src_base64=_fig_a_image(fig), fit=ft.ImageFit.CONTAIN)


def build_candlestick(ticker: str) -> ft.Image | ft.Container:
    import logging
    import warnings
    warnings.filterwarnings("ignore", message=".*possibly delisted.*")
    logging.getLogger("yfinance").setLevel(logging.ERROR)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
    try:
        from core.market import TICKERS_INVALIDOS
        if ticker in TICKERS_INVALIDOS:
            return ft.Container(
                ft.Text(f"Ticker no disponible: {ticker}", color=ft.colors.GREY_400),
                padding=20,
            )
        import yfinance as yf
        from core.market import _call_silent
        df = _call_silent(yf.download, ticker, period="6mo", interval="1d", progress=False)
        if df.empty:
            return ft.Container(
                ft.Text(f"Sin datos OHLC para {ticker}", color=ft.colors.GREY_400),
                padding=20,
            )
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={
            "Open": "Open", "High": "High", "Low": "Low",
            "Close": "Close", "Volume": "Volume",
        })

        mc = mpf.make_marketcolors(
            up="#3FB950", down="#F85149",
            edge={"up": "#3FB950", "down": "#F85149"},
            wick={"up": "#3FB950", "down": "#F85149"},
            volume={"up": "#3FB950", "down": "#F85149"},
        )
        s = mpf.make_mpf_style(
            marketcolors=mc,
            facecolor=FONDO_AX,
            edgecolor="#30363D",
            figcolor=FONDO,
            gridstyle="",
            gridcolor="#21262D",
        )
        fig, axlist = mpf.plot(
            df, type="candle", style=s,
            volume=False, returnfig=True,
            figsize=(7, 4.2),
            ylabel="Precio (MXN)",
            title=f"{ticker}",
            tight_layout=True,
        )
        ax = axlist[0]

        fig.patch.set_facecolor(FONDO)
        ax.set_facecolor(FONDO_AX)
        ax.tick_params(colors=TEXTO_SEC, labelsize=8)
        ax.yaxis.label.set_color(TEXTO_SEC)
        ax.yaxis.label.set_size(9)
        ax.set_title(ticker, color=TEXTO, fontsize=11)

        return ft.Image(src_base64=_fig_a_image(fig), fit=ft.ImageFit.CONTAIN)
    except Exception as ex:
        return ft.Container(
            ft.Text(f"Error: {ex}", color="#F85149", size=12),
            padding=20,
        )


def build_time_selector(valor_actual: str, on_change) -> ft.Row:
    opciones = ["H", "1S", "1M", "3M", "1A", "5A"]
    btns = []
    for o in opciones:
        es_activo = o == valor_actual
        btns.append(
            ft.ElevatedButton(
                text=o,
                on_click=lambda e, v=o: on_change(v),
                bgcolor="#58A6FF" if es_activo else "#21262D",
                color=ft.colors.WHITE,
                height=26,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=4),
                    padding=ft.padding.symmetric(horizontal=8, vertical=2),
                    side=ft.BorderSide(1, "#30363D" if not es_activo else "#58A6FF"),
                ),
            )
        )
    return ft.Row(btns, spacing=4)
