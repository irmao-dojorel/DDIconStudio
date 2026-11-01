"""DDIconStudio Material 3 color system and reusable Flet styles."""
import os

import flet as ft

from ddiconstudio.app_paths import ASSETS

APP_ICON_PNG = os.path.join(ASSETS, "app_icon.png")
APP_ICON_ICO = os.path.join(ASSETS, "app_icon.ico")
BACKGROUND = "#111820"
SURFACE = "#1A2530"
SURFACE_HIGH = "#243442"
TEXT = "#F2F4F7"
MUTED = "#A5B4C3"
ACCENT = "#A8C5D6"
OUTLINE = "#34495A"


def configure_page(page):
    page.title = "DDIconStudio"
    page.theme = ft.Theme(
        color_scheme_seed=ACCENT,
        use_material3=True,
        font_family="Segoe UI",
    )
    page.dark_theme = ft.Theme(
        color_scheme_seed=ACCENT,
        use_material3=True,
        font_family="Segoe UI",
    )
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BACKGROUND
    page.padding = 0
    page.window.width = 1440
    page.window.height = 920
    page.window.min_width = 1000
    page.window.min_height = 700
    page.window.maximized = True
    if os.path.isfile(APP_ICON_ICO):
        page.window.icon = APP_ICON_ICO


def app_icon(size):
    """Icone do app (assets/app_icon.png) para o cabecalho; cai no escudo generico se faltar o arquivo."""
    try:
        from PIL import Image
        with Image.open(APP_ICON_PNG) as source:
            image = source.convert("RGBA")
    except OSError:
        return ft.Icon(ft.Icons.SHIELD_MOON, color=ACCENT, size=size)
    return ft.Image(src=image_data(image), width=size, height=size, fit=ft.BoxFit.CONTAIN)


PIXEL_TRANSPARENTE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
)


def surface(content, *, padding=16, expand=False, width=None):
    return ft.Container(
        content=content,
        padding=padding,
        width=width,
        expand=expand,
        bgcolor=SURFACE,
        border=ft.Border.all(1, OUTLINE),
        border_radius=14,
    )


def heading(title, subtitle=None):
    controls = [
        ft.Text(title, size=23, weight=ft.FontWeight.W_600, color=TEXT),
    ]
    if subtitle:
        controls.append(ft.Text(subtitle, size=13, color=MUTED))
    return ft.Column(controls=controls, spacing=4, tight=True)


def image_data(image):
    """Encode a PIL image for a Flet Image control."""
    from io import BytesIO
    import base64

    output = BytesIO()
    image.save(output, format="PNG", compress_level=1)
    return base64.b64encode(output.getvalue()).decode("ascii")


def show_message(page, message, *, error=False):
    page.show_dialog(
        ft.SnackBar(
            content=ft.Text(message),
            bgcolor="#8F3D3D" if error else SURFACE_HIGH,
            show_close_icon=True,
            duration=5000,
        )
    )


def show_error(page, title, message):
    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message, selectable=True),
            actions=[
                ft.TextButton("Fechar", on_click=lambda _: page.pop_dialog()),
            ],
        )
    )
