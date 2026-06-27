from dotenv import load_dotenv
import flet as ft
from ui.dashboard import build_dashboard

load_dotenv()


def main(page: ft.Page):
    page.title = "AltFolio"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0D1117"
    page.padding = 20
    build_dashboard(page)


ft.app(target=main)
