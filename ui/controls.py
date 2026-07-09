import threading
import flet as ft

CAMPO_STYLE = ft.TextStyle(size=13)


def build_import_panel(page: ft.Page, on_import_file, status_callback=None):
    total_files = [0]
    processed = [0]

    file_picker = ft.FilePicker(
        on_result=lambda e: _handle_files(e, on_import_file, page, status_callback)
    )
    page.overlay.append(file_picker)

    def _handle_files(e, on_import_file, page, status_callback):
        if not e.files:
            return
        if len(e.files) > 12:
            if status_callback:
                status_callback(f"Máximo 12 archivos (seleccionaste {len(e.files)})", True)
            return
        total_files[0] = len(e.files)
        processed[0] = 0
        if status_callback:
            status_callback(f"Procesando 0/{total_files[0]} archivos...", False)

        def worker():
            for f in e.files:
                try:
                    if status_callback:
                        status_callback(f"Procesando {f.name} ({processed[0]+1}/{total_files[0]})...", False)
                    result = on_import_file(f.path)
                    processed[0] += 1
                    if isinstance(result, dict) and "error" in result:
                        if status_callback:
                            status_callback(f"{f.name}: {result['error']}", True)
                    else:
                        pos = len(result.get("posiciones", []))
                        cash = result.get("efectivo_mxn", 0)
                        capital = result.get("capital_ficticio_disponible_mxn", 0)
                        month = result.get("_month_label", "")
                        msg = f"{month}: {pos} pos, ${cash:,.2f} e, ${capital:,.2f} c"
                        if status_callback:
                            status_callback(f"OK {processed[0]}/{total_files[0]} - {msg}", False)
                except Exception as ex:
                    processed[0] += 1
                    if status_callback:
                        status_callback(f"{f.name}: Error {ex}", True)

        threading.Thread(target=worker, daemon=True).start()

    def pick_file(e):
        file_picker.pick_files(
            allow_multiple=True,
            allowed_extensions=["pdf", "xlsx"],
            dialog_title="Seleccionar PDF (estado cuenta) o XLSX (posición actual)",
        )

    panel = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("Importar Estado de Cuenta", size=16, weight=ft.FontWeight.BOLD, color=ft.colors.WHITE),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Divider(color=ft.colors.GREY_700, height=1),
            ft.ElevatedButton(
                "SELECCIONAR ARCHIVO PDF",
                on_click=pick_file,
                color=ft.colors.WHITE,
                bgcolor=ft.colors.AMBER_700,
                icon="upload_file",
                height=40,
            ),
        ], spacing=8),
        padding=15,
        bgcolor="#161B22",
        border_radius=10,
        border=ft.border.all(1, ft.colors.GREY_800),
    )

    panel.pick_file = pick_file
    return panel


