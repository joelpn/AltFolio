import flet as ft


COLORES = [
    ft.colors.BLUE_400, ft.colors.GREEN_400, ft.colors.ORANGE_400,
    ft.colors.PURPLE_400, ft.colors.RED_400, ft.colors.TEAL_400,
    ft.colors.YELLOW_400, ft.colors.CYAN_400, ft.colors.PINK_400,
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
        return ft.Text("Sin datos", color=ft.colors.GREY_400)

    normal_radius = 100
    title_style = ft.TextStyle(size=12, color=ft.colors.WHITE, weight=ft.FontWeight.BOLD)

    charts = []
    for i, (ticker, valor) in enumerate(sectores):
        pct = (valor / total * 100)
        color = COLORES[i % len(COLORES)]
        charts.append(
            ft.PieChartSection(
                value=valor,
                title=f"{ticker}\n{pct:.1f}%",
                color=color,
                radius=130,
                title_style=title_style,
                title_position=1,
            )
        )

    pie = ft.PieChart(
        sections=charts,
        sections_space=2,
        center_space_radius=40,
        expand=True,
    )
    return ft.Container(content=pie, padding=20, expand=True)


def build_bar_chart(posiciones, precios):
    total = 0
    sectores = []
    for ticker, info in posiciones.items():
        precio = precios.get(ticker) or info.get("precio_promedio_mxn") or 0
        valor = info["titulos"] * precio
        total += valor
        sectores.append((ticker, valor))

    if total == 0:
        return ft.Text("Sin datos", color=ft.colors.GREY_400)

    bar_groups = []
    max_valor = 0
    for i, (ticker, valor) in enumerate(sectores):
        if valor > max_valor:
            max_valor = valor
        color = COLORES[i % len(COLORES)]
        bar_groups.append(
            ft.BarChartGroup(
                x=i,
                bar_rods=[
                    ft.BarChartRod(
                        from_y=0,
                        to_y=valor,
                        color=color,
                        tooltip=f"{ticker}\n${valor:,.2f}",
                        border_radius=4,
                        width=30,
                    )
                ],
            )
        )
    
    chart_width = max(len(sectores) * 80, 500)

    chart = ft.BarChart(
        bar_groups=bar_groups,
        border=ft.Border(bottom=ft.BorderSide(1, ft.colors.GREY_700)),
        left_axis=ft.ChartAxis(labels_size=60),
        bottom_axis=ft.ChartAxis(
            labels=[
                ft.ChartAxisLabel(value=i, label=ft.Container(ft.Text(ticker, size=11, weight=ft.FontWeight.BOLD), padding=ft.padding.only(top=5))) for i, (ticker, _) in enumerate(sectores)
            ],
            labels_size=40,
        ),
        max_y=max_valor * 1.1 if max_valor > 0 else 100,
        interactive=True,
        tooltip_bgcolor=ft.colors.with_opacity(0.8, ft.colors.GREY_900),
        expand=True,
    )
    
    return ft.Row(
        controls=[ft.Container(content=chart, width=chart_width, padding=20)],
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
