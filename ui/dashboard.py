import os
import threading
from datetime import datetime
import flet as ft
from core.simulator import Simulador
from core.market import obtener_multiples_precios, excluir_ticker, TICKERS_INVALIDOS
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


def _fecha_rendimiento(fecha_str: str) -> datetime:
    return datetime.strptime(fecha_str, "%Y-%m")

TICKER_STYLE = ft.TextStyle(size=14, weight=ft.FontWeight.W_600)
VALOR_STYLE = ft.TextStyle(size=13, weight=ft.FontWeight.W_500)
CARD_BG = "#161B22"
CARD_BORDER = "#30363D"
CARD_HOVER = "#1C2430"
BG = "#0D1117"
TEXTO_PRIM = "#E6EDF3"
TEXTO_SEC = "#8B949E"


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
        self.loading_text = ft.Text("Cargando...", size=15, color=TEXTO_PRIM, weight=ft.FontWeight.W_500)
        self.loading_spinner = ft.ProgressRing(width=40, height=40, stroke_width=3, color="#58A6FF")
        self.loading_overlay = ft.Container(
            content=ft.Column(
                [self.loading_spinner, ft.Container(height=12), self.loading_text],
                spacing=0,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            bgcolor=ft.colors.with_opacity(0.8, BG),
            expand=True,
            alignment=ft.alignment.center,
            visible=False,
        )
        page.overlay.append(self.loading_overlay)

        self.panel_posiciones = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        self.chart_type = "Pastel"
        self.chart_selector = ft.Dropdown(
            options=[
                ft.dropdown.Option("Pastel"),
                ft.dropdown.Option("Barras"),
                ft.dropdown.Option("Treemap"),
                ft.dropdown.Option("Velas"),
            ],
            value="Pastel",
            width=160,
            on_change=self.on_chart_type_change,
            text_size=12,
            border_color=CARD_BORDER,
            bgcolor=CARD_BG,
            color=TEXTO_PRIM,
        )
        self.chart_container = ft.Container(content=ft.Text("...", color=TEXTO_SEC), expand=True)
        self.kpi_container = ft.Column(visible=True, spacing=4)
        self.selected_ticker_velas = None
        self.modo_grafica = "linea"
        self.rango_tiempo = "1A"
        self.subvista_patrimonio = "Evolucion"
        self.chart_patrimonio_container = ft.Container(height=480)
        self.tiempo_selector = ft.Row([], spacing=4, visible=False)
        self.badge_historico = ft.Container(
            content=ft.Text("", size=11, color=TEXTO_PRIM, weight=ft.FontWeight.W_500),
            bgcolor="#D29922",
            border_radius=4,
            padding=ft.padding.symmetric(horizontal=8, vertical=3),
            visible=False,
        )
        self.efectivo_text = ft.Text(
            f"Efectivo ficticio: ${self.sim.efectivo_ficticio:,.2f}",
            size=15,
            weight=ft.FontWeight.W_600,
            color="#3FB950",
        )
        self.panel_acciones = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, expand=True)
        self.acciones_header = ft.Text("", size=14, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE)
        self.vs_anterior_container = self._build_vs_anterior()

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
            if info.get("tipo") != "DEUDA" and info.get("ticker_yahoo") not in TICKERS_INVALIDOS
        }
        if not tickers:
            self.hide_loading()
            self.refresh_ui()
            return
        yahoo_tickers = list(tickers.keys())
        precios_raw = obtener_multiples_precios(yahoo_tickers)
        self.precios = {}
        fallaron = []
        for yahoo_t, ticker in tickers.items():
            if precios_raw.get(yahoo_t) is not None:
                self.precios[ticker] = precios_raw[yahoo_t]
            else:
                fallaron.append(yahoo_t)
        if fallaron:
            self._notificar_fallidos(list(tickers.values()), fallaron)
        self.refresh_ui()
        self.hide_loading()

    def _notificar_fallidos(self, locales: list, yahoo_fallados: list):
        if not yahoo_fallados:
            return
        msg = f"No se pudo obtener precio para: {', '.join(locales[:3])}"
        if len(locales) > 3:
            msg += f" y {len(locales)-3} mas"
        snack = ft.SnackBar(
            content=ft.Row([
                ft.Text(msg, size=13, color=TEXTO_PRIM, expand=True),
                ft.TextButton(
                    "Excluir",
                    on_click=lambda e: self._excluir_tickers(yahoo_fallados, snack),
                    style=ft.ButtonStyle(color="#D29922"),
                ),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            bgcolor="#2D1B1B",
            duration=10000,
            action="✕",
        )
        self.page.show_snack_bar(snack)

    def _excluir_tickers(self, yahoo_tickers: list, snack: ft.SnackBar):
        for t in yahoo_tickers:
            excluir_ticker(t)
        snack.open = False
        self.page.update()
        snack2 = ft.SnackBar(
            content=ft.Text(f"Excluidos: {', '.join(yahoo_tickers)}", size=13, color="#3FB950"),
            bgcolor="#1A2E1A",
            duration=3000,
        )
        self.page.show_snack_bar(snack2)
        self.refresh_ui()

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
        if self.chart_type == "Velas" and not self.selected_ticker_velas:
            tickers = list(self.sim.posiciones.keys())
            if tickers:
                self.selected_ticker_velas = tickers[0]
        self.refresh_ui()
        self.page.update()

    def _cargar_curva_patrimonio(self):
        from core.history import obtener_curva_patrimonio
        self._curva_patrimonio = obtener_curva_patrimonio()

    def _cargar_rendimientos(self):
        from core.history import obtener_rendimientos_mensuales
        self._rendimientos_mensuales = obtener_rendimientos_mensuales()

    def _reconstruir_patrimonio(self):
        self._cargar_curva_patrimonio()
        self._cargar_rendimientos()
        from ui.charts_avanzados import _build_equity_chart, build_pnl_chart
        curva = getattr(self, '_curva_patrimonio', [])
        rends = getattr(self, '_rendimientos_mensuales', [])

        if self.rango_tiempo != "5A" and curva:
            ahora = datetime.now()
            periodos = {"H": 1, "1S": 6, "1M": 1, "3M": 3, "1A": 12, "5A": 60}
            meses = periodos.get(self.rango_tiempo, 60)
            if meses and meses < 60:
                mes_inicio = ahora.month - meses
                year_inicio = ahora.year
                while mes_inicio < 1:
                    mes_inicio += 12
                    year_inicio -= 1
                limite = datetime(year_inicio, mes_inicio, 1)
                curva = [p for p in curva if datetime.strptime(p["fecha"], "%Y-%m-%d") >= limite]
                rends = [r for r in rends if _fecha_rendimiento(r["fecha"]) >= limite]
        if self.rango_tiempo == "H":
            curva = curva[-2:] if len(curva) >= 2 else curva
            rends = rends[-2:] if len(rends) >= 2 else rends

        if self.subvista_patrimonio == "Evolucion":
            self.chart_patrimonio_container.content = _build_equity_chart(curva, self.modo_grafica)
        else:
            self.chart_patrimonio_container.content = build_pnl_chart(rends)
        try:
            self.chart_patrimonio_container.update()
        except AssertionError:
            pass

    def _toggle_modo_grafica(self):
        self.modo_grafica = "linea" if self.modo_grafica == "area" else "area"
        self._reconstruir_patrimonio()

    def _actualizar_kpis(self):
        from core.history import calcular_kpis
        from ui.charts_avanzados import build_kpi_cards
        kpis = calcular_kpis(dashboard=self)
        self.kpi_container.controls = [build_kpi_cards(kpis)]
        self.kpi_container.update()

    def _build_vs_anterior(self) -> ft.Container:
        from core.history import obtener_curva_patrimonio
        curva = obtener_curva_patrimonio()
        if len(curva) >= 2:
            prev = curva[-2]["valor"]
            curr = curva[-1]["valor"]
            delta = curr - prev
            pct = ((curr / prev) - 1) * 100 if prev else 0
            color = "#3FB950" if delta >= 0 else "#F85149"
            flecha = "▲" if delta >= 0 else "▼"
            texto = f"Vs mes anterior: {flecha} ${delta:,.2f} ({pct:+.2f}%)"
            valor = f"${curr:,.2f}"
        else:
            color = TEXTO_SEC
            texto = "Sin datos historicos"
            valor = "$0.00"
        return ft.Container(
            content=ft.Column([
                ft.Text("Patrimonio Total", size=11, color=TEXTO_SEC),
                ft.Row([
                    ft.Text(valor, size=24, weight=ft.FontWeight.BOLD, color=TEXTO_PRIM),
                    ft.Container(
                        content=ft.Text(texto, size=12, color=color),
                        padding=ft.padding.symmetric(horizontal=10, vertical=4),
                        bgcolor="#21262D",
                        border_radius=4,
                    ),
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=2),
            padding=ft.padding.symmetric(horizontal=15, vertical=12),
            bgcolor=CARD_BG,
            border_radius=6,
            border=ft.border.all(1, CARD_BORDER),
        )

    def _actualizar_vs_anterior(self):
        self.vs_anterior_container.content = self._build_vs_anterior().content
        self.vs_anterior_container.update()

    def abrir_operaciones(self, e):
        dlg = self._build_operacion_dialog()
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def _build_operacion_dialog(self):
        tickers_conocidos = sorted(set(
            list(self.sim.posiciones.keys())
            + ["AMXL.MX", "CEMEXCPO.MX", "FEMSAUBD.MX", "FMTY14.MX",
               "FUNO11.MX", "GFNORTEO.MX", "GMEXICOB.MX", "KIMBERA.MX",
               "TLEVISACPO.MX", "WALMEX.MX", "AC.MX", "BBAJIOO.MX",
               "CITIGROUP.MX", "ELEKTRA.MX", "GAPB.MX", "GCARSOA1.MX",
               "GENTERA.MX", "LABB.MX", "MEGACPO.MX", "ORBIA.MX",
               "PINFRA.MX", "SITESB1.MX", "VASCONI.MX"])
        )
        resultado = ft.Text("", size=13, color=ft.colors.GREY_400, selectable=True)

        def actualizar_sugerencias(campo, sugerencias_col):
            val = campo.value.upper()
            sugerencias_col.controls.clear()
            if val:
                matches = [t for t in tickers_conocidos if val in t][:8]
                for t in matches:
                    btn = ft.TextButton(
                        text=t,
                        on_click=lambda e, v=t: _seleccionar_ticker(campo, sugerencias_col, v),
                        style=ft.ButtonStyle(padding=ft.padding.symmetric(horizontal=8, vertical=2)),
                    )
                    sugerencias_col.controls.append(btn)
            sugerencias_col.update()

        def _seleccionar_ticker(campo, sugerencias_col, ticker):
            campo.value = ticker
            sugerencias_col.controls.clear()
            campo.update()
            sugerencias_col.update()

        def _campo_ticker():
            campo = ft.TextField(
                label="Ticker",
                width=200, height=40, text_size=13,
                border_color=ft.colors.GREY_700,
                on_change=lambda e: actualizar_sugerencias(campo, sugerencias),
            )
            sugerencias = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO)
            return campo, sugerencias

        # --- Inyectar ---
        iny_campo = ft.TextField(label="Monto MXN", width=200, height=40, text_size=13, border_color=ft.colors.GREY_700)
        def on_inyectar(e):
            try:
                monto = float(iny_campo.value)
                self.sim.inyectar_capital(monto)
                resultado.value = f"Inyectados ${monto:,.2f} MXN"
                resultado.color = ft.colors.GREEN_400
                self.refresh_ui()
            except ValueError:
                resultado.value = "Monto invalido"
                resultado.color = ft.colors.RED_400
            resultado.update()
        seccion_inyectar = ft.Container(
            content=ft.Column([
                ft.Text("Inyectar Capital", size=14, weight=ft.FontWeight.BOLD, color=ft.colors.GREEN_400),
                ft.Row([iny_campo, ft.ElevatedButton("Inyectar", on_click=on_inyectar, bgcolor=ft.colors.GREEN_700, color=ft.colors.WHITE)], spacing=8),
            ], spacing=6),
            padding=10, bgcolor="#1A2E1A", border_radius=8,
        )

        # --- Comprar ---
        compra_ticker, compra_sug = _campo_ticker()
        compra_titulos = ft.TextField(label="Titulos", width=120, height=40, text_size=13, border_color=ft.colors.GREY_700)
        compra_precio = ft.TextField(label="Precio unitario", width=140, height=40, text_size=13, border_color=ft.colors.GREY_700)
        def on_comprar(e):
            try:
                t = compra_ticker.value.upper()
                tit = int(compra_titulos.value)
                prec = float(compra_precio.value)
                r = self.sim.simular_compra(t, tit, prec)
                if "error" in r:
                    resultado.value = r["error"]
                    resultado.color = ft.colors.RED_400
                else:
                    resultado.value = f"Comprados {tit} {t} a ${prec:.2f}"
                    resultado.color = ft.colors.GREEN_400
                    self.refresh_ui()
            except ValueError:
                resultado.value = "Datos invalidos"
                resultado.color = ft.colors.RED_400
            resultado.update()
        seccion_comprar = ft.Container(
            content=ft.Column([
                ft.Text("Comprar", size=14, weight=ft.FontWeight.BOLD, color=ft.colors.BLUE_400),
                compra_ticker, compra_sug,
                ft.Row([compra_titulos, compra_precio], spacing=8),
                ft.ElevatedButton("Comprar", on_click=on_comprar, bgcolor=ft.colors.BLUE_700, color=ft.colors.WHITE),
            ], spacing=6),
            padding=10, bgcolor="#1A2430", border_radius=8,
        )

        # --- Vender ---
        venta_ticker, venta_sug = _campo_ticker()
        venta_titulos = ft.TextField(label="Titulos", width=120, height=40, text_size=13, border_color=ft.colors.GREY_700)
        venta_precio = ft.TextField(label="Precio unitario", width=140, height=40, text_size=13, border_color=ft.colors.GREY_700)
        def on_vender(e):
            try:
                t = venta_ticker.value.upper()
                tit = int(venta_titulos.value)
                prec = float(venta_precio.value)
                r = self.sim.simular_venta(t, tit, prec)
                if "error" in r:
                    resultado.value = r["error"]
                    resultado.color = ft.colors.RED_400
                else:
                    gan = r.get("ganancia", 0)
                    signo = "G" if gan >= 0 else "P"
                    resultado.value = f"Vendidos {tit} {t} a ${prec:.2f} ({signo} ${abs(gan):,.2f})"
                    resultado.color = ft.colors.GREEN_400 if gan >= 0 else ft.colors.RED_400
                    self.refresh_ui()
            except ValueError:
                resultado.value = "Datos invalidos"
                resultado.color = ft.colors.RED_400
            resultado.update()
        seccion_vender = ft.Container(
            content=ft.Column([
                ft.Text("Vender", size=14, weight=ft.FontWeight.BOLD, color=ft.colors.RED_400),
                venta_ticker, venta_sug,
                ft.Row([venta_titulos, venta_precio], spacing=8),
                ft.ElevatedButton("Vender", on_click=on_vender, bgcolor=ft.colors.RED_700, color=ft.colors.WHITE),
            ], spacing=6),
            padding=10, bgcolor="#2E1A1A", border_radius=8,
        )

        dlg = ft.AlertDialog(
            title=ft.Text("Operaciones", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Column([
                    seccion_inyectar,
                    ft.Divider(height=1, color=ft.colors.GREY_700),
                    seccion_comprar,
                    ft.Divider(height=1, color=ft.colors.GREY_700),
                    seccion_vender,
                    ft.Divider(height=1, color=ft.colors.GREY_700),
                    resultado,
                ], spacing=10, scroll=ft.ScrollMode.AUTO),
                width=420,
            ),
            actions=[ft.TextButton("Cerrar", on_click=lambda e: self._cerrar_dialogo(dlg))],
        )
        return dlg

    def _cerrar_dialogo(self, dlg):
        dlg.open = False
        self.page.update()

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
        self.efectivo_text.color = "#D29922" if historico else "#3FB950"
        self.efectivo_text.update()

        precios_a_usar = {} if historico else self.precios

        cards = []
        for i, (ticker, info) in enumerate(posiciones.items()):
            if info.get("ticker_yahoo") in TICKERS_INVALIDOS:
                continue
            precio_live = precios_a_usar.get(ticker)
            precio_prom = info.get("precio_promedio_mxn") or 0
            valor_mercado = (precio_live or precio_prom) * info["titulos"]
            color_asset = COLORES[i % len(COLORES)]

            if precio_live and precio_prom:
                diff = (precio_live - precio_prom) / precio_prom * 100
                pnl_color = "#3FB950" if diff >= 0 else "#F85149"
                pnl = f"{diff:+.2f}%"
            else:
                pnl_color = TEXTO_SEC
                pnl = "-"

            precio_str = f"${precio_live:.2f}" if precio_live else f"${precio_prom:.2f} prom"
            pnl_color_str = pnl_color

            def on_card_click(e, t=ticker):
                self.selected_ticker_velas = t
                if self.chart_type == "Velas":
                    from ui.charts_avanzados import build_candlestick
                    self.chart_container.content = build_candlestick(t)
                    self.chart_container.update()
                    self.page.update()

            card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([
                            ft.Container(width=8, height=8, border_radius=4, bgcolor=color_asset),
                            ft.Text(ticker, size=14, weight=ft.FontWeight.W_600, color=TEXTO_PRIM),
                        ], spacing=6),
                        ft.Container(
                            content=ft.Text(f"{info['titulos']} t", size=11, color=TEXTO_SEC),
                            bgcolor="#21262D",
                            border_radius=4,
                            padding=ft.padding.symmetric(horizontal=6, vertical=2),
                        ),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Divider(height=1, color="#21262D"),
                    ft.Row([
                        ft.Column([
                            ft.Text("Precio", size=10, color=TEXTO_SEC),
                            ft.Text(precio_str, size=13, weight=ft.FontWeight.W_500, color=TEXTO_PRIM),
                        ]),
                        ft.Column([
                            ft.Text("Valor", size=10, color=TEXTO_SEC),
                            ft.Text(f"${valor_mercado:,.2f}", size=13, weight=ft.FontWeight.W_500, color=TEXTO_PRIM),
                        ]),
                        ft.Column([
                            ft.Text("P&L", size=10, color=TEXTO_SEC),
                            ft.Text(pnl, size=13, weight=ft.FontWeight.W_600, color=pnl_color_str),
                        ]),
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ], spacing=4),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                bgcolor="#1C2430" if historico else CARD_BG,
                border_radius=6,
                border=ft.border.all(1, "#D29922" if historico else CARD_BORDER),
                on_click=on_card_click,
            )
            cards.append(card)

        self.panel_posiciones.controls = cards
        self.panel_posiciones.update()

        posiciones_filtradas = {
            t: info for t, info in posiciones.items()
            if info.get("ticker_yahoo") not in TICKERS_INVALIDOS
        }
        self._render_chart(posiciones_filtradas, precios_a_usar)
        if not historico:
            self._actualizar_vs_anterior()
        self.page.update()

    def _render_chart(self, posiciones: dict, precios: dict):
        t = self.chart_type

        if t == "Pastel":
            self.chart_container.content = build_pie_chart(posiciones, precios)
        elif t == "Barras":
            self.chart_container.content = build_bar_chart(posiciones, precios)
        elif t == "Treemap":
            from ui.charts_avanzados import build_treemap
            self.chart_container.content = build_treemap(posiciones, precios)
        elif t == "Velas":
            from ui.charts_avanzados import build_candlestick
            ticker = self.selected_ticker_velas or (list(posiciones.keys()) + [""])[0]
            self.chart_container.content = build_candlestick(ticker)
        else:
            self.chart_container.content = build_pie_chart(posiciones, precios)
        self.chart_container.update()

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
            self.refresh_ui()
            return result
        except Exception as ex:
            return {"error": str(ex)}

    def on_delete_import(self, import_id):
        try:
            eliminar_importacion_por_id(import_id)
            if callable(getattr(self, '_refresh_calendario', None)):
                self._refresh_calendario()
        except Exception:
            pass

def _build_selector_historico(dashboard: "Dashboard") -> ft.Control:
    """Construye el selector de año/mes dinámico."""
    anio_dropdown = ft.Dropdown(
        options=[],
        width=90,
        text_size=12,
        border_color=CARD_BORDER,
        bgcolor=CARD_BG,
        color=TEXTO_PRIM,
        hint_text="Año",
    )
    meses_row = ft.Row([], spacing=4, scroll=ft.ScrollMode.AUTO)
    calendario_actual = {}  # {anio: [{month_label, import_id, capital_total}]}
    selected_import_id = [None]

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

        def make_click(mid, ml):
            def fn(e):
                selected_import_id[0] = mid
                if mid:
                    dashboard.cargar_mes_historico(mid, ml)
                _actualizar_meses(anio_dropdown.value)
            return fn

        def make_restore(mid):
            def fn(e):
                dashboard.on_restore_snapshot(mid)
                refrescar_calendario()
            return fn

        def make_delete(mid):
            def fn(e):
                dashboard.on_delete_import(mid)
                if selected_import_id[0] == mid:
                    selected_import_id[0] = None
                refrescar_calendario()
            return fn

        for num, nombre in _MESES_NOMBRE.items():
            month_label = f"{anio}-{num}"
            if month_label not in meses_del_anio:
                continue

            import_id = meses_del_anio[month_label]["import_id"]

            mes_btn = ft.ElevatedButton(
                text=nombre,
                on_click=make_click(import_id, month_label),
                bgcolor="#1A3A5C" if import_id == selected_import_id[0] else "#21262D",
                color=TEXTO_PRIM,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=4),
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    side=ft.BorderSide(1, "#58A6FF" if import_id == selected_import_id[0] else "#30363D"),
                ),
                height=28,
            )

            controls = [mes_btn]
            if import_id == selected_import_id[0]:
                controls.append(
                    ft.IconButton(
                        icon=ft.icons.RESTORE,
                        icon_size=14,
                        icon_color=ft.colors.GREEN_400,
                        tooltip="Restaurar este mes",
                        on_click=make_restore(import_id),
                        height=28, width=28,
                    )
                )
                controls.append(
                    ft.IconButton(
                        icon=ft.icons.DELETE_OUTLINE,
                        icon_size=14,
                        icon_color=ft.colors.RED_400,
                        tooltip="Eliminar importacion",
                        on_click=make_delete(import_id),
                        height=28, width=28,
                    )
                )

            meses_row.controls.append(ft.Row(controls, spacing=2))

        meses_row.update()

    def on_anio_change(e):
        if anio_dropdown.value:
            _actualizar_meses(anio_dropdown.value)

    anio_dropdown.on_change = on_anio_change

    def on_volver(e):
        selected_import_id[0] = None
        dashboard.volver_al_actual()
        refrescar_calendario()

    selector = ft.Row(
        controls=[
            ft.Text("Historial:", size=12, color=TEXTO_SEC),
            anio_dropdown,
            meses_row,
            ft.Container(expand=True),
            ft.ElevatedButton(
                "Actual",
                on_click=on_volver,
                bgcolor="#21262D",
                color=TEXTO_PRIM,
                height=28,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=4),
                    side=ft.BorderSide(1, "#30363D"),
                    padding=ft.padding.symmetric(horizontal=10, vertical=2),
                ),
            ),
        ],
        spacing=6,
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

    def on_import_status(msg: str, is_error=False):
        pass  # no status bar

    dashboard.import_status_callback = on_import_status
    panel_import = build_import_panel(
        page, dashboard.on_import_file,
        status_callback=on_import_status,
    )

    export_picker = ft.FilePicker(on_result=lambda e: _handle_export(e, dashboard))
    page.overlay.append(export_picker)

    csv_picker = ft.FilePicker(on_result=lambda e: _handle_csv_export(e, dashboard))
    page.overlay.append(csv_picker)

    def _handle_export(e, dashboard):
        if not e.path:
            return
        import json
        estado = dashboard.sim.obtener_estado()
        data = {
            "fecha_snapshot": "",
            "efectivo_mxn": dashboard.sim.efectivo_ficticio,
            "capital_ficticio_disponible_mxn": dashboard.sim.efectivo_ficticio,
            "posiciones": [
                {"ticker": t, **info}
                for t, info in estado["posiciones"].items()
            ],
        }
        with open(e.path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _handle_csv_export(e, dashboard):
        if not e.path:
            return
        import csv
        estado = dashboard.sim.obtener_estado()
        path = e.path if e.path.endswith(".csv") else e.path + ".csv"
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Ticker", "Tipo", "Titulos", "Precio Promedio", "Costo Total"])
            for ticker, info in estado["posiciones"].items():
                writer.writerow([
                    ticker, info.get("tipo", ""), info["titulos"],
                    info.get("precio_promedio_mxn", ""), info.get("costo_total_mxn", ""),
                ])

    acciones_container = ft.Container(
        content=ft.Column([
            dashboard.acciones_header,
            dashboard.panel_acciones,
        ], spacing=6),
        padding=12,
        bgcolor=CARD_BG,
        border_radius=6,
        border=ft.border.all(1, CARD_BORDER),
        visible=False,
    )
    dashboard.acciones_container = acciones_container

    # --- Tab Portafolio ---
    vs_anterior = dashboard.vs_anterior_container
    tab_portafolio = ft.Row([
        ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("Posiciones", size=17, weight=ft.FontWeight.W_600, color=TEXTO_PRIM),
                    ft.Row([dashboard.badge_historico], spacing=6),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Container(height=4),
                dashboard.efectivo_text,
                ft.Divider(height=1, color="#21262D"),
                dashboard.panel_posiciones,
            ], spacing=6, expand=True),
            width=320,
            padding=12,
            bgcolor=CARD_BG,
            border_radius=6,
            border=ft.border.all(1, CARD_BORDER),
        ),
        ft.Container(
            content=ft.Column([
                vs_anterior,
                ft.Row([
                    ft.Text("Distribucion", size=17, weight=ft.FontWeight.W_600, color=TEXTO_PRIM),
                    dashboard.chart_selector,
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                dashboard.chart_container,
                acciones_container,
            ], spacing=6, expand=True),
            expand=True,
            padding=12,
            bgcolor=CARD_BG,
            border_radius=6,
            border=ft.border.all(1, CARD_BORDER),
        ),
    ], expand=True, spacing=8)

    # --- Tab Patrimonio ---
    try:
        dashboard._reconstruir_patrimonio()
    except Exception:
        dashboard.chart_patrimonio_container.content = ft.Text("Error al cargar patrimonio", color=TEXTO_SEC)
    from ui.charts_avanzados import build_time_selector

    def _on_rango_change(rango: str):
        dashboard.rango_tiempo = rango
        dashboard._reconstruir_patrimonio()

    def _on_toggle_modo(e):
        dashboard._toggle_modo_grafica()
        btn_toggle.text = "Linea" if dashboard.modo_grafica == "linea" else "Area"
        btn_toggle.update()

    def _on_subvista_change(e):
        dashboard.subvista_patrimonio = e.control.value
        titulo_chart.value = dashboard.subvista_patrimonio
        titulo_chart.update()
        btn_toggle.visible = dashboard.subvista_patrimonio == "Evolucion"
        btn_toggle.update()
        dashboard._reconstruir_patrimonio()

    btn_toggle = ft.ElevatedButton(
        text="Area" if dashboard.modo_grafica == "linea" else "Linea",
        on_click=_on_toggle_modo,
        bgcolor="#21262D", color=TEXTO_PRIM, height=26,
        visible=dashboard.subvista_patrimonio == "Evolucion",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=4),
            padding=ft.padding.symmetric(horizontal=8, vertical=2),
            side=ft.BorderSide(1, "#30363D"),
        ),
    )

    subvista_selector = ft.Dropdown(
        options=[
            ft.dropdown.Option("Evolucion"),
            ft.dropdown.Option("Rendimientos"),
        ],
        value="Evolucion",
        width=180,
        on_change=_on_subvista_change,
        text_size=12,
        border_color=CARD_BORDER,
        bgcolor=CARD_BG,
        color=TEXTO_PRIM,
    )

    dashboard.tiempo_selector.controls = [
        build_time_selector(dashboard.rango_tiempo, _on_rango_change),
        btn_toggle,
    ]
    dashboard.tiempo_selector.visible = True

    titulo_chart = ft.Text("Evolucion", size=15, weight=ft.FontWeight.W_600, color=TEXTO_PRIM)

    tab_patrimonio = ft.Column([
        dashboard.kpi_container,
        dashboard.tiempo_selector,
        ft.Container(
            content=ft.Column([
                ft.Row([titulo_chart, subvista_selector], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                dashboard.chart_patrimonio_container,
            ], spacing=4),
            padding=12, bgcolor=CARD_BG, border_radius=6,
            border=ft.border.all(1, CARD_BORDER), expand=True,
        ),
    ], spacing=8, expand=True)

    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=200,
        divider_color="#21262D",
        indicator_color="#58A6FF",
        label_color=TEXTO_PRIM,
        unselected_label_color=TEXTO_SEC,
        tabs=[
            ft.Tab(text="Portafolio", icon=ft.icons.ACCOUNT_BALANCE, content=tab_portafolio),
            ft.Tab(text="Patrimonio", icon=ft.icons.TRENDING_UP, content=tab_patrimonio),
        ],
        expand=True,
    )

    page.window.prevent_close = False
    page.on_close = lambda e: os._exit(0)

    BTN_STYLE = ft.ButtonStyle(
        shape=ft.RoundedRectangleBorder(radius=5),
        padding=ft.padding.symmetric(horizontal=14, vertical=8),
        side=ft.BorderSide(1, "#30363D"),
    )

    page.add(
        ft.Container(
            content=ft.Row([
                ft.ElevatedButton(
                    "Importar",
                    on_click=panel_import.pick_file,
                    icon=ft.icons.UPLOAD_FILE,
                    style=BTN_STYLE,
                    color=TEXTO_PRIM,
                    bgcolor="#21262D",
                ),
                ft.ElevatedButton(
                    "Actualizar",
                    on_click=start_refresh,
                    icon=ft.icons.REFRESH,
                    style=BTN_STYLE,
                    color=TEXTO_PRIM,
                    bgcolor="#21262D",
                ),
                ft.ElevatedButton(
                    "Exportar JSON",
                    on_click=lambda e: export_picker.save_file(
                        file_name="portfolio.json",
                        allowed_extensions=["json"],
                        dialog_title="Guardar exportacion",
                    ),
                    icon=ft.icons.DOWNLOAD,
                    style=BTN_STYLE,
                    color=TEXTO_PRIM,
                    bgcolor="#21262D",
                ),
                ft.ElevatedButton(
                    "Exportar CSV",
                    on_click=lambda e: csv_picker.save_file(
                        file_name="portfolio.csv",
                        allowed_extensions=["csv"],
                        dialog_title="Guardar exportacion CSV",
                    ),
                    icon=ft.icons.TABLE_CHART,
                    style=BTN_STYLE,
                    color=TEXTO_PRIM,
                    bgcolor="#21262D",
                ),
                ft.ElevatedButton(
                    "Operar",
                    on_click=dashboard.abrir_operaciones,
                    icon=ft.icons.SWAP_VERT,
                    style=BTN_STYLE,
                    color=TEXTO_PRIM,
                    bgcolor="#21262D",
                ),
            ], spacing=6, alignment=ft.MainAxisAlignment.START),
            padding=ft.padding.symmetric(horizontal=6, vertical=4),
        ),
        ft.Container(
            content=selector_historico,
            padding=ft.padding.symmetric(horizontal=6, vertical=4),
            bgcolor=BG,
            border_radius=6,
            border=ft.border.all(1, CARD_BORDER),
        ),
        tabs,
    )
    page.bgcolor = BG
    page.update()

    dashboard._actualizar_kpis()

    # Cargar el calendario de historial
    selector_historico.refrescar()

    start_refresh()

    def refrescar_periodico():
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
