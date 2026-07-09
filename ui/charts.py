import flet as ft

COLORES_VIVOS = [
    ft.colors.CYAN_400, ft.colors.GREEN_400, ft.colors.AMBER_400,
    ft.colors.DEEP_PURPLE_400, ft.colors.RED_400, ft.colors.TEAL_400,
    ft.colors.PINK_400, ft.colors.INDIGO_400, ft.colors.LIME_400,
    ft.colors.ORANGE_400, ft.colors.LIGHT_BLUE_400, ft.colors.PURPLE_400,
]

COLORES = [
    "#58A6FF", "#3FB950", "#D29922", "#BC8CFF",
    "#F85149", "#56D4DD", "#A5D6A7", "#FFA657",
    "#79C0FF", "#7EE787", "#E3B341", "#D2A8FF",
]


def build_pie_chart(posiciones, precios):
    total = 0
    sectores = []
    for ticker, info in posiciones.items():
        precio = precios.get(ticker) or info.get("precio_promedio_mxn") or 0
        valor = info["titulos"] * precio
        total += valor
        sectores.append((ticker, valor))

    if total == 0:
        return ft.Text("Sin datos", color="#8B949E")

    charts = []
    for i, (ticker, valor) in enumerate(sectores):
        pct = (valor / total * 100)
        color = COLORES[i % len(COLORES)]
        charts.append(
            ft.PieChartSection(
                value=valor,
                title=f"{ticker}\n{pct:.1f}%" if pct > 3 else "",
                color=color,
                radius=150,
                title_style=ft.TextStyle(size=11, color=ft.colors.WHITE, weight=ft.FontWeight.BOLD),
                title_position=1,
            )
        )

    pie = ft.PieChart(
        sections=charts,
        sections_space=2,
        center_space_radius=55,
        expand=True,
    )
    return ft.Container(content=pie, padding=5, expand=True)


def build_bar_chart(posiciones, precios):
    total = 0
    sectores = []
    for ticker, info in posiciones.items():
        precio = precios.get(ticker) or info.get("precio_promedio_mxn") or 0
        valor = info["titulos"] * precio
        total += valor
        sectores.append((ticker, valor))

    if total == 0:
        return ft.Text("Sin datos", color="#8B949E")

    n = len(sectores)
    bar_width = max(28, min(50, 240 // n))
    font_size = max(7, min(11, 180 // n))

    bar_groups = []
    max_valor = max(v for _, v in sectores) if sectores else 1

    for i, (ticker, valor) in enumerate(sectores):
        color = COLORES[i % len(COLORES)]
        pct = (valor / total * 100)
        bar_groups.append(
            ft.BarChartGroup(
                x=i,
                bar_rods=[
                    ft.BarChartRod(
                        from_y=0,
                        to_y=valor,
                        color=color,
                        tooltip=f"{ticker}\n${valor:,.2f}\n({pct:.1f}%)",
                        border_radius=ft.border_radius.only(top_left=3, top_right=3),
                        width=bar_width,
                    )
                ],
            )
        )

    chart = ft.BarChart(
        bar_groups=bar_groups,
        border=ft.Border(bottom=ft.BorderSide(1, "#30363D")),
        left_axis=ft.ChartAxis(labels_size=50, labels_interval=max_valor / 4),
        bottom_axis=ft.ChartAxis(
            labels=[
                ft.ChartAxisLabel(
                    value=i,
                    label=ft.Container(
                        ft.Text(ticker, size=font_size, weight=ft.FontWeight.W_600, color="#E6EDF3",
                                no_wrap=False),
                        padding=ft.padding.only(top=4),
                    ),
                )
                for i, (ticker, _) in enumerate(sectores)
            ],
            labels_size=36,
        ),
        max_y=max_valor * 1.12,
        interactive=True,
        tooltip_bgcolor=ft.colors.with_opacity(0.9, "#161B22"),
        expand=True,
    )

    ancho_min = max(300, n * (bar_width + 18))

    return ft.Column([
        ft.Container(
            content=chart,
            padding=ft.padding.only(left=5, right=5, top=8, bottom=5),
            expand=True,
        ),
        ft.Container(
            content=ft.Row(
                [ft.Container(
                    content=ft.Row([
                        ft.Container(width=8, height=8, border_radius=4, bgcolor=COLORES[i % len(COLORES)]),
                        ft.Text(f"{t}: ${v:,.0f} ({v/total*100:.1f}%)", size=9, color="#8B949E"),
                    ], spacing=4),
                ) for i, (t, v) in enumerate(sectores)],
                wrap=True, spacing=12,
            ),
            padding=ft.padding.only(left=12, right=12, bottom=8),
        ),
    ], expand=True)
