import os
import threading
import flet as ft
from core.simulator import Simulador
from core.market import obtener_multiples_precios
from core.storage import init_db
from core.gbm_import import import_file, persist_import
from core.history import (
    restaurar_snapshot, eliminar_importacion_por_id,
    obtener_calendario,
)
from ui.charts import build_pie_chart, build_bar_chart, COLORES
from ui.controls import build_import_panel

_MESES_NOMBRE = {
    "01": "ENE", "02": "FEB", "03": "MAR", "04": "ABR",
    "05": "MAY", "06": "JUN", "07": "JUL", "08": "AGO",
    "09": "SEP", "10": "OCT", "11": "NOV", "12": "DIC",
}

TICKER_STYLE = ft.TextStyle(size=14, weight=ft.FontWeight.BOLD)
VALOR_STYLE = ft.TextStyle(size=13)
CARD_BG = "#161B22"


class Dashboard:
    def __init__(self, page: ft.Page):
        self.page = page
        self.sim = Simulador()
        init_db()
        self.precios = {}
        # --- Modo histórico ---
        self.modo_historico = False
        self.historial_posiciones = None
        self.historial_efectivo = 0.0
        self.historial_label = ""
        # ----------------------
        self.loading_text = ft.Text("Cargando...", size=16, color=ft.colors.WHITE, weight=ft.FontWeight.BOLD)
        self.loading_spinner = ft.ProgressRing(width=48, height=48, stroke_width=4)
        self.loading_overlay = ft.Container(
            content=ft.Column(
                [self.loading_spinner, ft.Container(height=16), self.loading_text],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=ft.colors.with_opacity(0.75, "#0D1117"),
            expand=True,
            alignment=ft.alignment.center,
            visible=False,
        )
        page.overlay.append(self.loading_overlay)

        self.panel_posiciones = ft.Column(spacing=8, scroll=ft.ScrollMode.AUTO, expand=True)
        self.chart_type = "Pastel"
        self.chart_selector = ft.Dropdown(
            options=[ft.dropdown.Option("Pastel"), ft.dropdown.Option("Barras")],
            value="Pastel",
            width=150,
            on_change=self.on_chart_type_change,
            text_size=14,
            border_color=ft.colors.GREY_700,
        )
        self.chart_container = ft.Container(content=ft.Text("...", color=ft.colors.GREY_400), height=360)
        self.badge_historico = ft.Container(
            content=ft.Text("", size=12, color=ft.colors.WHITE, weight=ft.FontWeight.BOLD),
            bgcolor=ft.colors.AMBER_800,
            border_radius=6,
            padding=ft.padding.symmetric(horizontal=8, vertical=3),
            visible=False,
        )
        self.efectivo_text = ft.Text(
            f"Efectivo ficticio: ${self.sim.efectivo_ficticio:,.2f}",
            size=16,
            weight=ft.FontWeight.BOLD,
            color=ft.colors.GREEN_400,
        )
        self.panel_acciones = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
        self.acciones_header = ft.Text("", size=14, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE)

    def show_loading(self, msg="Procesando..."):
        self.loading_text.value = msg
        self.loading_overlay.visible = True
        self.loading_overlay.update()
        self.page.update()

    def hide_loading(self):
        self.loading_overlay.visible = False
        self.loading_overlay.update()
        self.page.update()

    def actualizar_precios(self):
        self.show_loading("Actualizando precios...")
        
        tickers = {
            info["ticker_yahoo"]: ticker
            for ticker, info in self.sim.posiciones.items()
            if info.get("tipo") != "DEUDA"
        }
        if not tickers:
            self.hide_loading()
            self.refresh_ui()
            return
        yahoo_tickers = list(tickers.keys())
        precios_raw = obtener_multiples_precios(yahoo_tickers)
        self.precios = {}
        for yahoo_t, ticker in tickers.items():
            if precios_raw.get(yahoo_t) is not None:
                self.precios[ticker] = precios_raw[yahoo_t]
        self.refresh_ui()
        self.hide_loading()

    def _cargar_acciones(self, import_id: int, month_label: str):
        from core.storage import obtener_acciones_por_import_id
        acciones = obtener_acciones_por_import_id(import_id)
        self.panel_acciones.controls.clear()
        if not getattr(self, 'acciones_container', None):
            return
        if not acciones:
            self.acciones_header.value = ""
            self.acciones_header.update()
            self.panel_acciones.update()
            self.acciones_container.visible = False
            self.acciones_container.update()
            return
        self.acciones_container.visible = True

        compras = [a for a in acciones if a["tipo_accion"] == "COMPRA"]
        ventas = [a for a in acciones if a["tipo_accion"] == "VENTA"]
        total_ganancia = sum(a.get("ganancia_perdida", 0) for a in acciones)

        self.acciones_header.value = f"Movimientos {self.historial_label}"
        self.acciones_header.update()

        cards = []
        if compras:
            cards.append(ft.Text("Compras", size=13, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_400))
            for a in compras:
                cards.append(ft.Container(
                    content=ft.Row([
                        ft.Text(a["ticker"], size=13, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE, width=80),
                        ft.Text(f"+{a['titulos']} tit", size=12, color=ft.colors.GREEN_300),
                        ft.Text(f"${a['precio_mxn']:.2f}", size=12, color=ft.colors.GREY_300),
                        ft.Text(f"${a['monto_total']:,.2f}", size=12, color=ft.colors.GREY_300),
                    ], spacing=6),
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    bgcolor="#1A2E1A",
                    border_radius=4,
                ))
        if ventas:
            cards.append(ft.Text("Ventas", size=13, weight=ft.FontWeight.BOLD, color=ft.colors.RED_400))
            for a in ventas:
                gan = a.get("ganancia_perdida", 0)
                color_gan = ft.colors.GREEN_400 if gan >= 0 else ft.colors.RED_400
                cards.append(ft.Container(
                    content=ft.Row([
                        ft.Text(a["ticker"], size=13, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE, width=80),
                        ft.Text(f"-{a['titulos']} tit", size=12, color=ft.colors.RED_300),
                        ft.Text(f"${a['precio_mxn']:.2f}", size=12, color=ft.colors.GREY_300),
                        ft.Text(f"${a['monto_total']:,.2f}", size=12, color=ft.colors.GREY_300),
                        ft.Text(f"{'G' if gan >= 0 else 'P'} ${abs(gan):,.2f}", size=12, color=color_gan),
                    ], spacing=6),
                    padding=ft.padding.symmetric(horizontal=8, vertical=3),
                    bgcolor="#2E1A1A",
                    border_radius=4,
                ))

        ganancia_color = ft.colors.GREEN_400 if total_ganancia >= 0 else ft.colors.RED_400
        cards.append(ft.Divider(height=1, color=ft.colors.GREY_700))
        cards.append(ft.Row([
            ft.Text("Resultado del mes:", size=13, weight=ft.FontWeight.BOLD, color=ft.colors.GREY_300),
            ft.Text(f"{'Ganancia' if total_ganancia >= 0 else 'Pérdida'} ${abs(total_ganancia):,.2f}",
                    size=13, weight=ft.FontWeight.BOLD, color=ganancia_color),
        ], spacing=6))

        self.panel_acciones.controls = cards
        self.panel_acciones.update()

    def on_chart_type_change(self, e):
        self.chart_type = e.control.value
        self.refresh_ui()

    def cargar_mes_historico(self, import_id: int, month_label: str):
        from core.storage import obtener_snapshot_por_id
        self._hist_import_id = import_id
        self._hist_month_label = month_label
        self.show_loading(f"Cargando {month_label}...")
        snapshot = obtener_snapshot_por_id(import_id)
        if not snapshot:
            self.hide_loading()
            return
        self.modo_historico = True
        mes_num = month_label.split("-")[1] if "-" in month_label else ""
        anio = month_label.split("-")[0] if "-" in month_label else ""
        mes_nombre = _MESES_NOMBRE.get(mes_num, mes_num)
        self.historial_label = f"{mes_nombre} {anio}"
        self.historial_posiciones = {p["ticker"]: p for p in snapshot.get("posiciones", [])}
        self.historial_efectivo = snapshot.get("efectivo_mxn", 0)
        self.badge_historico.content.value = f"📅 {self.historial_label}"
        self.badge_historico.visible = True
        self.badge_historico.update()
        self._refresh_with_data(self.historial_posiciones, self.historial_efectivo, historico=True)
        self._cargar_acciones(import_id, month_label)
        self.hide_loading()

    def volver_al_actual(self):
        """Sale del modo histórico y regresa al snapshot más reciente en vivo."""
        self.modo_historico = False
        self.historial_posiciones = None
        self.historial_label = ""
        self._hist_import_id = None
        self._hist_month_label = None
        self.badge_historico.visible = False
        self.badge_historico.update()
        if getattr(self, 'acciones_container', None):
            self.acciones_container.visible = False
            self.acciones_container.update()
        self.actualizar_precios()

    def refresh_ui(self):
        if self.modo_historico and self.historial_posiciones is not None:
            self._refresh_with_data(self.historial_posiciones, self.historial_efectivo, historico=True)
        else:
            estado = self.sim.obtener_estado()
            self._refresh_with_data(estado["posiciones"], self.sim.efectivo_ficticio, historico=False)

    def _refresh_with_data(self, posiciones: dict, efectivo: float, historico: bool):
        self.efectivo_text.value = f"Efectivo ficticio: ${efectivo:,.2f}"
        self.efectivo_text.color = ft.colors.AMBER_400 if historico else ft.colors.GREEN_400
        self.efectivo_text.update()

        precios_a_usar = {} if historico else self.precios

        cards = []
        for i, (ticker, info) in enumerate(posiciones.items()):
            precio_live = precios_a_usar.get(ticker)
            precio_prom = info.get("precio_promedio_mxn") or 0
            valor_mercado = (precio_live or precio_prom) * info["titulos"]
            color_asset = COLORES[i % len(COLORES)]

            if precio_live and precio_prom:
                diff = (precio_live - precio_prom) / precio_prom * 100
                color = ft.colors.GREEN_400 if diff >= 0 else ft.colors.RED_400
                pnl = f" ({diff:+.2f}%)"
            else:
                color = ft.colors.GREY_400
                pnl = ""

            precio_str = f"${precio_live:.2f}" if precio_live else f"${precio_prom:.2f} (prom)"

            card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([
                            ft.Container(width=10, height=10, border_radius=5, bgcolor=color_asset),
                            ft.Text(ticker, style=TICKER_STYLE, color=ft.colors.WHITE),
                        ], spacing=6),
                        ft.Text(f"{info['titulos']} titulos", size=12, color=ft.colors.GREY_400),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Row([
                        ft.Column([
                            ft.Text("Precio", size=11, color=ft.colors.GREY_500),
                            ft.Text(precio_str, style=VALOR_STYLE, color=color),
                        ]),
                        ft.Column([
                            ft.Text("Valor", size=11, color=ft.colors.GREY_500),
                            ft.Text(f"${valor_mercado:,.2f}", style=VALOR_STYLE, color=ft.colors.WHITE),
                        ]),
                        ft.Column([
                            ft.Text("P&L", size=11, color=ft.colors.GREY_500),
                            ft.Text(pnl if pnl else "-", style=VALOR_STYLE, color=color),
                        ]),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ], spacing=4),
                padding=12,
                bgcolor="#1C2430" if historico else CARD_BG,
                border_radius=8,
                border=ft.border.all(1, ft.colors.AMBER_800 if historico else ft.colors.GREY_800),
            )
            cards.append(card)

        self.panel_posiciones.controls = cards
        self.panel_posiciones.update()

        if self.chart_type == "Pastel":
            self.chart_container.content = build_pie_chart(posiciones, precios_a_usar)
        else:
            self.chart_container.content = build_bar_chart(posiciones, precios_a_usar)
        self.chart_container.update()
        self.page.update()

    def on_import_file(self, filepath):
        self.show_loading("Importando estado de cuenta...")
        try:
            parsed = import_file(filepath)
            if isinstance(parsed, dict) and "error" in parsed:
                self.hide_loading()
                return parsed

            resultado = persist_import(filepath, parsed)
            if isinstance(resultado, dict) and resultado.get("_duplicate"):
                self.hide_loading()
                return resultado

            self.sim.__init__()
            self.actualizar_precios()
            self.hide_loading()
            if callable(getattr(self, '_refresh_calendario', None)):
                self._refresh_calendario()
            return resultado
        except FileNotFoundError:
            self.hide_loading()
            return {"error": "Archivo no encontrado"}
        except Exception as ex:
            self.hide_loading()
            return {"error": str(ex)}

    def on_restore_snapshot(self, import_id):
        try:
            result = restaurar_snapshot(import_id)
            if isinstance(result, dict) and "error" in result:
                return result
            self.sim.__init__()
            self.actualizar_precios()
            return result
        except Exception as ex:
            return {"error": str(ex)}

    def on_delete_import(self, import_id):
        try:
            eliminar_importacion_por_id(import_id)
        except Exception:
            pass

def _build_selector_historico(dashboard: "Dashboard") -> ft.Control:
    """Construye el selector de año/mes dinámico."""
    anio_dropdown = ft.Dropdown(
        options=[],
        width=100,
        text_size=13,
        border_color=ft.colors.GREY_700,
        hint_text="Año",
    )
    meses_row = ft.Row([], spacing=4, scroll=ft.ScrollMode.AUTO)
    calendario_actual = {}  # {anio: [{month_label, import_id, capital_total}]}

    def refrescar_calendario():
        nonlocal calendario_actual
        calendario_actual = obtener_calendario()
        anios = sorted(calendario_actual.keys(), reverse=True)
        anio_dropdown.options = [ft.dropdown.Option(a) for a in anios]
        if anios:
            anio_dropdown.value = anios[0]
        anio_dropdown.update()
        _actualizar_meses(anio_dropdown.value)

    def _actualizar_meses(anio: str):
        meses_row.controls.clear()
        meses_del_anio = {m["month_label"]: m for m in calendario_actual.get(anio, [])}
        
        for num, nombre in _MESES_NOMBRE.items():
            month_label = f"{anio}-{num}"
            if month_label not in meses_del_anio:
                continue
                
            import_id = meses_del_anio[month_label]["import_id"]

            def make_click(mid, ml):
                def fn(e):
                    if mid:
                        dashboard.cargar_mes_historico(mid, ml)
                return fn

            btn = ft.ElevatedButton(
                text=nombre,
                on_click=make_click(import_id, month_label),
                bgcolor=ft.colors.BLUE_900,
                color=ft.colors.WHITE,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=6),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                ),
                height=32,
            )
            meses_row.controls.append(btn)
        meses_row.update()

    def on_anio_change(e):
        if anio_dropdown.value:
            _actualizar_meses(anio_dropdown.value)

    anio_dropdown.on_change = on_anio_change

    def on_volver(e):
        dashboard.volver_al_actual()
        refrescar_calendario()

    selector = ft.Row(
        controls=[
            ft.Text("Historial:", size=13, color=ft.colors.GREY_400),
            anio_dropdown,
            meses_row,
            ft.Container(expand=True),
            ft.ElevatedButton(
                "↩ Actual",
                on_click=on_volver,
                bgcolor=ft.colors.GREEN_800,
                color=ft.colors.WHITE,
                height=32,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=6),
                ),
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )

    # Exponer función de refresco para llamarla desde fuera
    selector.refrescar = refrescar_calendario  # type: ignore
    return selector


def build_dashboard(page: ft.Page):
    dashboard = Dashboard(page)

    page.title = "AltFolio"

    def start_refresh(e=None):
        if dashboard.modo_historico:
            if getattr(dashboard, '_hist_import_id', None):
                dashboard.cargar_mes_historico(dashboard._hist_import_id, dashboard._hist_month_label)
        else:
            dashboard.sim = Simulador()
            dashboard.actualizar_precios()

    selector_historico = _build_selector_historico(dashboard)
    dashboard._refresh_calendario = selector_historico.refrescar

    status = ft.Text("Listo", size=12, color=ft.colors.GREY_500, selectable=True)

    def on_import_status(msg: str, is_error=False):
        status.value = msg
        status.color = ft.colors.RED_400 if is_error else ft.colors.GREEN_400
        status.update()

    dashboard.import_status_callback = on_import_status
    panel_import = build_import_panel(
        page, dashboard.on_import_file,
        status_callback=on_import_status,
    )

    acciones_container = ft.Container(
        content=ft.Column([
            dashboard.acciones_header,
            dashboard.panel_acciones,
        ], spacing=8),
        padding=15,
        bgcolor="#161B22",
        border_radius=10,
        border=ft.border.all(1, ft.colors.GREY_800),
        visible=False,
    )
    dashboard.acciones_container = acciones_container

    layout = ft.Row([
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Posiciones", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE),
                    ft.Row([dashboard.badge_historico], spacing=6),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                dashboard.efectivo_text,
                ft.Divider(color=ft.colors.GREY_700),
                dashboard.panel_posiciones,
            ], spacing=8, expand=True),
            width=330,
            padding=15,
            bgcolor="#161B22",
            border_radius=10,
            border=ft.border.all(1, ft.colors.GREY_800),
        ),
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Distribucion", size=18, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE),
                    dashboard.chart_selector,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                dashboard.chart_container,
                acciones_container,
            ], spacing=8, expand=True),
            expand=True,
            padding=15,
            bgcolor="#161B22",
            border_radius=10,
            border=ft.border.all(1, ft.colors.GREY_800),
        ),
    ], expand=True, spacing=10)

    page.window.prevent_close = False
    page.on_close = lambda e: os._exit(0)

    page.add(
        ft.Row([
            ft.ElevatedButton(
                "Carga Archivo",
                on_click=panel_import.pick_file,
                icon="upload_file",
                bgcolor=ft.colors.AMBER_700,
                color=ft.colors.WHITE,
            ),
            ft.ElevatedButton(
                "Actualizar Datos",
                on_click=start_refresh,
                icon="refresh",
                bgcolor=ft.colors.BLUE_700,
                color=ft.colors.WHITE,
            ),
        ], alignment=ft.MainAxisAlignment.START),
        ft.Container(
            content=selector_historico,
            padding=ft.padding.symmetric(horizontal=6, vertical=4),
            bgcolor="#0D1117",
            border_radius=8,
            border=ft.border.all(1, ft.colors.GREY_800),
        ),
        ft.Container(
            content=status,
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            bgcolor="#161B22",
            border_radius=6,
            border=ft.border.all(1, ft.colors.GREY_800),
        ),
        layout
    )
    page.update()

    # Cargar el calendario de historial
    selector_historico.refrescar()

    start_refresh()

    stop_timer = threading.Event()

    def refrescar_periodico():
        if stop_timer.is_set():
            return
        if not dashboard.modo_historico:
            start_refresh()
        intervalo = dashboard.sim.config.get("intervalo_actualizacion_precios_seg", 60)
        t = threading.Timer(intervalo, refrescar_periodico)
        t.daemon = True
        t.start()

    intervalo = dashboard.sim.config.get("intervalo_actualizacion_precios_seg", 60)
    t = threading.Timer(intervalo, refrescar_periodico)
    t.daemon = True
    t.start()
