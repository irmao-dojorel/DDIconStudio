"""Flet-based vocation crest editor with live previews and layered weapons."""
import asyncio
import colorsys
import dataclasses
import math
import os
import random
import re

import flet as ft
from PIL import Image

from ddiconstudio import banner_gen, chanfro, icon_gen, padroes_banner, silhuetas
from ddiconstudio.pak_builder import ICONE_MAX, ICONE_MIN
from ddiconstudio.gui.dialogo_silhuetas import miniatura_silhueta
from ddiconstudio.gui.theme import (
    ACCENT, MUTED, OUTLINE, PIXEL_TRANSPARENTE, SURFACE_HIGH, TEXT, heading, image_data,
    show_error, show_message, surface,
)

BANNER_POR_MOLDURA = {"simples": "simples", "avancada": "coroa", "mestre": "escudo"}
METAL_POR_MOLDURA = {"mestre": "ouro"}
LADO_PREVIA_ICONE = 300
LADO_PREVIA_GLIFO = 72
TAMANHO_PREVIA_BANNER = (230, 460)
LADO_MINIATURA = 64
_WHEEL_SIZE = 220
_wheel_cache = {}


def _wheel_image():
    if "png" not in _wheel_cache:
        from PIL import Image
        size = _WHEEL_SIZE
        radius = size / 2
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        pixels = image.load()
        for y in range(size):
            for x in range(size):
                dx, dy = x + 0.5 - radius, y + 0.5 - radius
                distance = math.hypot(dx, dy)
                if distance <= radius:
                    hue = (math.atan2(dy, dx) / (2 * math.pi)) % 1
                    r, g, b = colorsys.hsv_to_rgb(hue, distance / radius, 1.0)
                    pixels[x, y] = (round(r * 255), round(g * 255), round(b * 255), 255)
        _wheel_cache["png"] = image_data(image)
    return _wheel_cache["png"]


def cor_para_banner(cor):
    equivalencias = {
        "vermelho": "vermelho", "ambar": "ocre", "azul": "azul", "verde": "verde",
        "roxo": "roxo", "turquesa": "turquesa", "rosa": "rosa", "cinza": "cinza",
        "preto": "preto", "osso": "branco",
    }
    ancoras = [(icon_gen.PALETA[nome], banner_gen.PALETA[destino])
               for nome, destino in equivalencias.items()]
    for origem, destino in ancoras:
        if cor == origem:
            return destino
    hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in cor))
    origin, destination = min(
        (pair for pair in ancoras if pair[0] not in (
            icon_gen.PALETA["cinza"], icon_gen.PALETA["preto"], icon_gen.PALETA["osso"])),
        key=lambda pair: abs((colorsys.rgb_to_hsv(*(channel / 255 for channel in pair[0]))[0] - hue + 0.5) % 1 - 0.5),
    )
    hue_origin, sat_origin, val_origin = colorsys.rgb_to_hsv(*(channel / 255 for channel in origin))
    hue_dest, sat_dest, val_dest = colorsys.rgb_to_hsv(*(channel / 255 for channel in destination))
    result = colorsys.hsv_to_rgb(
        (hue_dest + hue - hue_origin) % 1,
        max(0, min(1, sat_dest * saturation / sat_origin)),
        max(0, min(1, val_dest * value / val_origin)),
    )
    return tuple(round(channel * 255) for channel in result)


def nome_legivel(nome):
    return re.sub(r"^\d+_", "", nome).replace("_", " ") or "(sem arma)"


class Gerador:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.pasta_icones = app.pasta_icones
        self.numero_min = ICONE_MIN
        self.numero_max = ICONE_MAX
        self.cor_a = icon_gen.PALETA["vermelho"]
        self.cor_b = icon_gen.PALETA["azul"]
        self.moldura = (icon_gen.molduras() or ["simples"])[0]
        self.metal = "prata"
        self.metal_moldura = "bronze"
        self.dividir = False
        self.sombra = True
        self.espelhar = False
        self.transparente = False
        self.caber_na_moldura = False
        self.semente = 1
        self.camadas = [self.camada_nova()]
        self.camada_atual = 0
        self.active_color_side = "a"
        self.icone = None
        self.glifo = None
        self.banner = None
        self.banner_pattern = None
        self.scale_value_fields = {}
        self.preview = ft.Image(src=PIXEL_TRANSPARENTE, width=LADO_PREVIA_ICONE, height=LADO_PREVIA_ICONE,
                                fit=ft.BoxFit.CONTAIN)
        self.preview_glifo = ft.Image(src=PIXEL_TRANSPARENTE, width=LADO_PREVIA_GLIFO, height=LADO_PREVIA_GLIFO,
                                      fit=ft.BoxFit.CONTAIN)
        self.preview_banner = ft.Image(
            src=PIXEL_TRANSPARENTE,
            width=TAMANHO_PREVIA_BANNER[0],
            height=TAMANHO_PREVIA_BANNER[1],
            fit=ft.BoxFit.CONTAIN,
        )
        self.weapon_grid = ft.Row(
            wrap=True,
            spacing=8,
            run_spacing=8,
        )
        self.layer_list = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, height=116)
        self.help_text = ft.Text("Selecione uma silhueta para adicionar ao brasao.", size=12, color=MUTED)
        self.frame_cards = {}

    @staticmethod
    def camada_nova(escala=1.0):
        return dict(arma="", escala=escala, dx=0, dy=0, rotacao=0, espelhar=False)

    def build(self):
        self._build_weapons()
        self._build_controls()
        self.root = ft.Container(
            expand=True,
            padding=24,
            content=ft.Column(
                expand=True,
                spacing=18,
                controls=[
                    heading("Criar brasao", "Combine molduras, cores e silhuetas; a previa acompanha os ajustes."),
                    ft.Row(
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=18,
                        controls=[
                            surface(
                                ft.Column(
                                    controls=[
                                        ft.Text("Previa ao vivo", size=16, weight=ft.FontWeight.W_600),
                                        self.preview,
                                        ft.Row(
                                            controls=[
                                                ft.Column(
                                                    controls=[
                                                        ft.Text("Painel da Guilda", size=12, color=MUTED),
                                                        self.preview_glifo,
                                                    ],
                                                    spacing=4,
                                                ),
                                                ft.Column(
                                                    controls=[
                                                        ft.Text("Banner", size=12, color=MUTED),
                                                        self.preview_banner,
                                                    ],
                                                    spacing=4,
                                                ),
                                            ],
                                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                            vertical_alignment=ft.CrossAxisAlignment.START,
                                        ),
                                        ft.Button(
                                            "Salvar como icone",
                                            icon=ft.Icons.SAVE_OUTLINED,
                                            on_click=self.salvar_icone,
                                            width=300,
                                        ),
                                        ft.Text("O brasao entra no PAK com 90% da celula.", size=11, color=MUTED),
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                    spacing=12,
                                    scroll=ft.ScrollMode.AUTO,
                                ),
                                width=440,
                            ),
                            # so a coluna de ajustes rola; a previa fica fixa ao lado
                            ft.Column(
                                expand=True,
                                spacing=14,
                                scroll=ft.ScrollMode.AUTO,
                                controls=[
                                    surface(self._appearance_controls()),
                                    surface(self._composition_controls()),
                                    surface(self._banner_controls()),
                                    surface(
                                        ft.Column(
                                            controls=[
                                                ft.Row(
                                                    controls=[
                                                        ft.Text("Biblioteca de silhuetas", size=16,
                                                                weight=ft.FontWeight.W_600),
                                                        ft.Container(expand=True),
                                                        ft.Button("Importar", icon=ft.Icons.UPLOAD_FILE,
                                                                  on_click=self.importar_silhueta),
                                                        ft.Button("Remover", icon=ft.Icons.DELETE_OUTLINE,
                                                                  on_click=self.remover_silhueta),
                                                    ]
                                                ),
                                                self.weapon_grid,
                                                self.help_text,
                                            ],
                                            spacing=10,
                                        ),
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )
        asyncio.create_task(self._refresh_preview())
        return self.root

    def _appearance_controls(self):
        frames = []
        for name in icon_gen.molduras():
            image = icon_gen.render(
                moldura=name,
                cor_a=(60, 60, 70),
                metal_moldura=METAL_POR_MOLDURA.get(name, "bronze"),
            ).resize((52, 52), Image.Resampling.LANCZOS)
            card = ft.Container(
                    content=ft.Image(src=image_data(image),
                                     width=52, height=52, fit=ft.BoxFit.CONTAIN),
                    padding=4,
                    border=ft.Border.all(2, ACCENT if name == self.moldura else OUTLINE),
                    border_radius=8,
                    tooltip=name.capitalize(),
                    on_click=lambda _, selected=name: self.page.run_task(self._select_frame, selected),
                )
            self.frame_cards[name] = card
            frames.append(card)
        palette = []
        self.palette_cards = []
        for name, color in icon_gen.PALETA.items():
            hex_color = self._hex(color)
            card = ft.Container(
                    width=28,
                    height=28,
                    bgcolor=hex_color,
                    border_radius=14,
                    border=ft.Border.all(2, TEXT if color in (self.cor_a, self.cor_b) else OUTLINE),
                    tooltip=f"{name}: aplicar na cor {self.active_color_side.upper()}",
                    on_click=lambda event, selected=color: self.page.run_task(self._select_color, selected, self.active_color_side),
                )
            self.palette_cards.append((color, card))
            palette.append(card)
        self.color_a_label = ft.Text(self._hex(self.cor_a), size=11, color=MUTED)
        self.color_b_label = ft.Text(self._hex(self.cor_b), size=11, color=MUTED)
        self.color_a_chip = ft.Container(
            width=24, height=24, bgcolor=self._hex(self.cor_a), border_radius=6,
            border=ft.Border.all(1, OUTLINE),
        )
        self.color_b_chip = ft.Container(
            width=24, height=24, bgcolor=self._hex(self.cor_b), border_radius=6,
            border=ft.Border.all(1, OUTLINE),
        )
        self.divide_switch = ft.Switch(label="Dividir fundo", value=self.dividir, on_change=self._changed)
        self.color_target = ft.RadioGroup(
            value=self.active_color_side,
            content=ft.Row(
                controls=[
                    ft.Radio(value="a", label="Aplicar paleta em A"),
                    ft.Radio(value="b", label="Aplicar paleta em B"),
                ],
            ),
            on_change=self._change_color_target,
        )
        self.weapon_metal_dropdown = ft.Dropdown(
            label="Metal da arma",
            value=self.metal,
            options=[ft.DropdownOption(key=value, text=value.capitalize())
                     for value in icon_gen.METAIS],
            width=190,
            on_select=self._changed,
        )
        self.appearance_controls = {
            "color_a": self.color_a_chip,
            "color_a_label": self.color_a_label,
            "color_b": self.color_b_chip,
            "color_b_label": self.color_b_label,
            "divide": self.divide_switch,
            "weapon_metal": self.weapon_metal_dropdown,
        }
        return ft.Column(
            spacing=10,
            controls=[
                ft.Text("Aparencia", size=16, weight=ft.FontWeight.W_600),
                ft.Text("Moldura", size=12, color=MUTED),
                ft.Row(controls=frames, wrap=True, spacing=8),
                ft.Row(
                    controls=[
                        self._color_setting("Cor A", self.color_a_label, "a"),
                        self._color_setting("Cor B", self.color_b_label, "b"),
                        self.divide_switch,
                    ],
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.color_target,
                ft.Row(
                    controls=palette + [
                        ft.Button("Sortear cores", icon=ft.Icons.CASINO_OUTLINED,
                                  on_click=self.sortear_cores)
                    ],
                    wrap=True,
                    spacing=8,
                ),
                ft.Row(
                    controls=[self.weapon_metal_dropdown],
                    wrap=True,
                ),
            ],
        )

    def _color_setting(self, label, value_label, side):
        chip = self.color_a_chip if side == "a" else self.color_b_chip
        return ft.Row(
            controls=[
                ft.Text(label),
                chip,
                value_label,
                ft.IconButton(
                    icon=ft.Icons.COLORIZE,
                    tooltip="Informar cor hexadecimal",
                    on_click=lambda _, color_side=side: self.page.run_task(self._custom_color, color_side),
                ),
            ],
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _composition_controls(self):
        sliders = [
            self._slider_row("scale", "Tamanho", min=0.3, max=1.6, divisions=26, value=1.0),
            self._slider_row("dx", "Horizontal", min=-70, max=70, divisions=140, value=0),
            self._slider_row("dy", "Vertical", min=-70, max=70, divisions=140, value=0),
            self._slider_row("rotation", "Rotacao", "{value}°", min=-180, max=180, divisions=360, value=0),
        ]
        self.seed_field = ft.TextField(label="Semente da textura", value="1", width=190, dense=True,
                                       keyboard_type=ft.KeyboardType.NUMBER, on_submit=self._changed)
        self.shadow_switch = ft.Switch(label="Sombra", value=self.sombra, on_change=self._changed)
        self.mirror_switch = ft.Switch(label="Espelhar", value=self.espelhar, on_change=self._changed)
        self.transparent_switch = ft.Switch(label="Fundo transparente", value=self.transparente, on_change=self._changed)
        self.fit_switch = ft.Switch(label="Caber na moldura", value=self.caber_na_moldura, on_change=self._changed)
        self.composition_controls = {
            "shadow": self.shadow_switch,
            "mirror": self.mirror_switch,
            "transparent": self.transparent_switch,
            "fit": self.fit_switch,
        }
        return ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Composicao", size=16, weight=ft.FontWeight.W_600),
                        ft.Button("Adicionar camada", icon=ft.Icons.ADD, on_click=self.adicionar_camada),
                        ft.Button("Remover camada", icon=ft.Icons.REMOVE, on_click=self.remover_camada),
                        ft.IconButton(icon=ft.Icons.ARROW_UPWARD, tooltip="Trazer para frente",
                                      on_click=lambda _: self.page.run_task(self.mover_camada, 1)),
                        ft.IconButton(icon=ft.Icons.ARROW_DOWNWARD, tooltip="Enviar para tras",
                                      on_click=lambda _: self.page.run_task(self.mover_camada, -1)),
                    ],
                    wrap=True,
                ),
                ft.Row(
                    controls=[
                        ft.Container(content=self.layer_list, width=220),
                        ft.Column(controls=sliders, expand=True, spacing=0),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
                ft.Row(
                    controls=[
                        self.seed_field,
                        ft.Button("Sortear", icon=ft.Icons.CASINO_OUTLINED, on_click=self.sortear_semente),
                        self.shadow_switch,
                        self.mirror_switch,
                        self.transparent_switch,
                        self.fit_switch,
                    ],
                    wrap=True,
                ),
            ],
        )

    def _banner_controls(self):
        self.banner_pattern_status = ft.Text("Nenhum padrão importado", size=12, color=MUTED)
        self.remove_banner_pattern_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            tooltip="Remover padrão do banner",
            disabled=True,
            on_click=self.remover_padrao_banner,
        )
        self.banner_library_dropdown = ft.Dropdown(
            label="Biblioteca", dense=True, width=220, options=[],
            on_select=self._selecionar_padrao_banner,
        )
        self.atualizar_padroes_banner()
        padrao = [
            self._slider_row("banner_pattern_scale", "Tamanho", min=0.1, max=3.0, divisions=58, value=1.0),
            self._slider_row("banner_pattern_dx", "Horizontal", min=-256, max=256, divisions=512, value=0),
            self._slider_row("banner_pattern_dy", "Vertical", min=-512, max=512, divisions=1024, value=0),
        ]
        contorno = [
            self._slider_row("banner_contour_scale", "Tamanho", min=0.5, max=1.5, divisions=20, value=1.0),
            self._slider_row("banner_contour_dx", "Horizontal", min=-60, max=60, divisions=120, value=0),
            self._slider_row("banner_contour_dy", "Vertical", min=-60, max=60, divisions=120, value=0),
        ]
        return ft.Column(
            spacing=8,
            controls=[
                ft.Row(
                    controls=[
                        ft.Text("Banner", size=16, weight=ft.FontWeight.W_600),
                        self.banner_library_dropdown,
                        ft.Button("Importar padrão PNG", icon=ft.Icons.UPLOAD_FILE,
                                  on_click=self.importar_padrao_banner),
                        self.remove_banner_pattern_button,
                    ],
                    wrap=True,
                ),
                ft.Row(
                    controls=[
                        ft.Container(content=self.banner_pattern_status, width=220),
                        ft.Column(
                            controls=[
                                ft.Text("Padrão", size=12, color=MUTED), *padrao,
                                ft.Text("Contorno", size=12, color=MUTED), *contorno,
                            ],
                            expand=True,
                            spacing=0,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
        )

    def _slider_row(self, chave, rotulo, rotulo_valor="{value}", **opcoes):
        slider = ft.Slider(label=rotulo_valor, on_change=self._changed, expand=True, **opcoes)
        setattr(self, f"{chave}_slider", slider)
        campo = ft.TextField(
            value=self._format_slider_value(chave, slider.value),
            width=78,
            height=40,
            dense=True,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_submit=lambda event, field_key=chave: self._set_slider_from_field(field_key, event),
        )
        self.scale_value_fields[chave] = campo
        return ft.Row(
            controls=[ft.Container(content=ft.Text(rotulo, size=12), width=90), slider, campo],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

    @staticmethod
    def _format_slider_value(key, value):
        return f"{float(value):.2f}" if key.endswith("scale") else str(round(float(value)))

    def _sync_slider_value_fields(self):
        for key, field in self.scale_value_fields.items():
            slider = getattr(self, f"{key}_slider")
            field.value = self._format_slider_value(key, slider.value)

    def _set_slider_from_field(self, key, event):
        slider = getattr(self, f"{key}_slider")
        try:
            value = float(event.control.value.strip().replace(",", "."))
            if not math.isfinite(value):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            event.control.error_text = "Valor invalido"
            self.page.update()
            return
        value = min(max(value, slider.min), slider.max)
        if slider.divisions:
            step = (slider.max - slider.min) / slider.divisions
            value = slider.min + round((value - slider.min) / step) * step
        slider.value = value
        event.control.value = self._format_slider_value(key, value)
        event.control.error_text = None
        self.page.run_task(self._changed, event)

    def _build_controls(self):
        self._refresh_layers()

    def _build_weapons(self):
        self.weapon_grid.controls.clear()
        for name in [""] + icon_gen.armas():
            if name:
                with Image.open(silhuetas.caminho_da_silhueta(name)) as source:
                    image = source.convert("RGBA")
                image.thumbnail((LADO_MINIATURA - 4, LADO_MINIATURA - 4), Image.Resampling.LANCZOS)
                background = Image.new("RGBA", (LADO_MINIATURA, LADO_MINIATURA), (38, 53, 67, 255))
                background.alpha_composite(
                    image, ((LADO_MINIATURA - image.width) // 2, (LADO_MINIATURA - image.height) // 2)
                )
            else:
                background = Image.new("RGBA", (LADO_MINIATURA, LADO_MINIATURA), (29, 39, 49, 255))
            selected = any(layer["arma"] == name for layer in self.camadas)
            self.weapon_grid.controls.append(
                ft.Container(
                    content=ft.Image(
                        src=image_data(background),
                        width=LADO_MINIATURA,
                        height=LADO_MINIATURA,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    border=ft.Border.all(2, ACCENT if selected else OUTLINE),
                    border_radius=8,
                    tooltip=nome_legivel(name),
                    on_click=lambda _, weapon=name: self.page.run_task(self._select_weapon, weapon),
                )
            )
    def _refresh_layers(self):
        self.layer_list.controls = [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.LAYERS_OUTLINED, size=16, color=ACCENT if index == self.camada_atual else MUTED),
                        ft.Text(f"{index + 1}. {nome_legivel(layer['arma'])}", size=12,
                                color=TEXT if index == self.camada_atual else MUTED, expand=True),
                    ],
                    spacing=8,
                ),
                padding=8,
                bgcolor=SURFACE_HIGH if index == self.camada_atual else None,
                border_radius=6,
                on_click=lambda _, selected=index: self.page.run_task(self._select_layer, selected),
            )
            for index, layer in enumerate(self.camadas)
        ]
        if hasattr(self, "scale_slider"):
            layer = self.camadas[self.camada_atual]
            self.scale_slider.value = layer["escala"]
            self.dx_slider.value = layer["dx"]
            self.dy_slider.value = layer["dy"]
            self.rotation_slider.value = layer["rotacao"]
            self.espelhar = layer["espelhar"]
            self._sync_slider_value_fields()
        if self.page:
            self.page.update()

    async def _select_layer(self, index):
        self._store_layer_controls()
        self.camada_atual = index
        self.espelhar = self.camadas[index]["espelhar"]
        self.mirror_switch.value = self.espelhar
        self._refresh_layers()
        await self._refresh_preview()

    def _change_color_target(self, event):
        self.active_color_side = event.control.value

    async def _select_weapon(self, name):
        self._store_layer_controls()
        self._definir_silhueta(name)
        self._refresh_layers()
        self._build_weapons()
        self.help_text.value = nome_legivel(name)
        self.page.update()
        await self._refresh_preview()

    def _definir_silhueta(self, nome):
        camada = self.camadas[self.camada_atual]
        if camada["arma"] != nome:
            camada.update(arma=nome, dx=0, dy=0)

    def _store_layer_controls(self):
        if not hasattr(self, "scale_slider"):
            return
        layer = self.camadas[self.camada_atual]
        layer.update(
            escala=float(self.scale_slider.value),
            dx=int(self.dx_slider.value),
            dy=int(self.dy_slider.value),
            rotacao=int(self.rotation_slider.value),
            espelhar=self.espelhar,
        )

    async def _changed(self, _):
        self._sync_slider_value_fields()
        self.dividir = self.appearance_controls["divide"].value
        self.sombra = self.composition_controls["shadow"].value
        self.espelhar = self.composition_controls["mirror"].value
        self.transparente = self.composition_controls["transparent"].value
        self.caber_na_moldura = self.composition_controls["fit"].value
        self.metal = self.appearance_controls["weapon_metal"].value
        self._store_layer_controls()
        await self._refresh_preview()

    async def _select_frame(self, name):
        self.moldura = name
        self.metal_moldura = METAL_POR_MOLDURA.get(name, "bronze")
        for frame_name, card in self.frame_cards.items():
            card.border = ft.Border.all(2, ACCENT if frame_name == name else OUTLINE)
        self.page.update()
        await self._refresh_preview()

    async def _select_color(self, color, side):
        self.active_color_side = side
        self.color_target.value = side
        if side == "a":
            self.cor_a = color
        else:
            self.cor_b = color
            self.dividir = True
        self._build_appearance()
        for selected, card in self.palette_cards:
            card.border = ft.Border.all(
                2, TEXT if selected in (self.cor_a, self.cor_b) else OUTLINE
            )
            card.tooltip = f"Aplicar na cor {self.active_color_side.upper()}"
        self.page.update()
        await self._refresh_preview()

    async def _custom_color(self, side):
        atual = self.cor_a if side == "a" else self.cor_b
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in atual))
        state = {"h": h, "s": s, "v": v}
        result = {"color": None}
        future = asyncio.get_running_loop().create_future()

        def rgb():
            return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(state["h"], state["s"], state["v"]))

        def hex_of(rgb_value):
            return "#{:02X}{:02X}{:02X}".format(*rgb_value)

        swatch = ft.Container(height=64, border_radius=12, border=ft.Border.all(1, OUTLINE))
        field = ft.TextField(label="Cor hexadecimal", value=hex_of(atual), dense=True)
        wheel_size = _WHEEL_SIZE
        radius = wheel_size / 2
        marker = ft.Container(
            width=14, height=14, border_radius=7,
            border=ft.Border.all(2, "#FFFFFF"), bgcolor="#00000000",
            shadow=ft.BoxShadow(blur_radius=3, color="#000000"),
        )

        def refresh(update_field=True):
            swatch.bgcolor = hex_of(rgb())
            angle = state["h"] * 2 * math.pi
            marker.left = radius + math.cos(angle) * state["s"] * radius - 7
            marker.top = radius + math.sin(angle) * state["s"] * radius - 7
            if update_field:
                field.value = hex_of(rgb())
                field.error_text = None
            self.page.update()

        def on_slider(key):
            def handler(e):
                state[key] = e.control.value
                refresh()
            return handler

        sliders = {
            "h": ft.Slider(min=0, max=1, value=h, on_change=on_slider("h"), expand=True),
            "s": ft.Slider(min=0, max=1, value=s, on_change=on_slider("s"), expand=True),
            "v": ft.Slider(min=0, max=1, value=v, on_change=on_slider("v"), expand=True),
        }

        def on_wheel(e):
            position = e.local_position
            dx, dy = position.x - radius, position.y - radius
            state["h"] = (math.atan2(dy, dx) / (2 * math.pi)) % 1
            state["s"] = min(math.hypot(dx, dy) / radius, 1.0)
            sliders["h"].value = state["h"]
            sliders["s"].value = state["s"]
            refresh()

        wheel = ft.GestureDetector(
            content=ft.Stack(
                width=wheel_size, height=wheel_size,
                controls=[ft.Image(src=_wheel_image(), width=wheel_size, height=wheel_size), marker],
            ),
            on_tap_down=on_wheel,
            on_pan_update=on_wheel,
        )
        wheel_box = ft.Row([wheel], alignment=ft.MainAxisAlignment.CENTER, visible=False)

        def slider_row(label, key):
            return ft.Row([ft.Text(label, width=80, color=MUTED), sliders[key]])

        hs_box = ft.Column(
            [slider_row("Matiz", "h"), slider_row("Saturação", "s")], tight=True, spacing=8,
        )
        mode_buttons = {}

        def set_mode(mode):
            wheel_box.visible = mode == "wheel"
            hs_box.visible = mode == "sliders"
            for name, button in mode_buttons.items():
                button.style = ft.ButtonStyle(color=ACCENT if name == mode else MUTED)
            self.page.update()

        mode_buttons["sliders"] = ft.TextButton("Sliders", icon=ft.Icons.TUNE, on_click=lambda _: set_mode("sliders"))
        mode_buttons["wheel"] = ft.TextButton("Roda de cores", icon=ft.Icons.PALETTE, on_click=lambda _: set_mode("wheel"))
        mode_buttons["sliders"].style = ft.ButtonStyle(color=ACCENT)
        mode_buttons["wheel"].style = ft.ButtonStyle(color=MUTED)

        def on_hex(e):
            value = (field.value or "").strip().lstrip("#")
            if re.fullmatch(r"[0-9A-Fa-f]{6}", value):
                r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
                state["h"], state["s"], state["v"] = colorsys.rgb_to_hsv(r, g, b)
                for key, slider in sliders.items():
                    slider.value = state[key]
                field.error_text = None
                refresh(update_field=False)

        field.on_change = on_hex
        swatch.bgcolor = hex_of(atual)
        angle0 = h * 2 * math.pi
        marker.left = radius + math.cos(angle0) * s * radius - 7
        marker.top = radius + math.sin(angle0) * s * radius - 7

        def submit(_):
            value = (field.value or "").strip().lstrip("#")
            if not re.fullmatch(r"[0-9A-Fa-f]{6}", value):
                field.error_text = "Use seis digitos hexadecimais, por exemplo D9A441."
                self.page.update()
                return
            result["color"] = tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))
            self.page.pop_dialog()
            future.set_result(True)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Escolher cor personalizada"),
            content=ft.Column(
                width=360,
                tight=True,
                spacing=8,
                controls=[
                    swatch,
                    ft.Row(list(mode_buttons.values()), alignment=ft.MainAxisAlignment.CENTER),
                    hs_box,
                    wheel_box,
                    slider_row("Brilho", "v"),
                    field,
                ],
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: (self.page.pop_dialog(), future.set_result(False))),
                ft.Button("Aplicar", on_click=submit),
            ],
        )
        self.page.show_dialog(dialog)
        await future
        if result["color"] is not None:
            await self._select_color(result["color"], side)

    def _build_appearance(self):
        if hasattr(self, "appearance_controls"):
            self.color_a_chip.bgcolor = self._hex(self.cor_a)
            self.color_a_label.value = self._hex(self.cor_a)
            self.color_b_chip.bgcolor = self._hex(self.cor_b)
            self.color_b_label.value = self._hex(self.cor_b)
            self.divide_switch.value = self.dividir

    async def _refresh_preview(self):
        if not hasattr(self, "scale_slider"):
            return
        # sliders disparam muitos eventos: enquanto um render roda, os seguintes viram um unico render no fim
        if getattr(self, "_renderizando", None) is not None:
            self._render_pendente = True
            await self._renderizando.wait()
            return
        self._renderizando = asyncio.Event()
        try:
            while True:
                self._render_pendente = False
                await self._render_preview()
                if not self._render_pendente:
                    break
        finally:
            self._renderizando.set()
            self._renderizando = None

    async def _render_preview(self):
        self._store_layer_controls()
        seed = self.semente
        try:
            seed = max(1, min(99999, int(self.seed_field.value)))
            self.semente = seed
        except (TypeError, ValueError):
            pass
        camadas = [dict(layer) for layer in self.camadas]
        args_icone = dict(
            moldura=self.moldura,
            cor_a=self.cor_a,
            cor_b=self.cor_b if self.dividir else None,
            semente=seed,
            armas=camadas,
            metal=self.metal,
            sombra=self.sombra,
            metal_moldura=self.metal_moldura,
            transparente=self.transparente,
            margem=6 if self.caber_na_moldura else 0,
        )
        args_banner = dict(
            estilo=BANNER_POR_MOLDURA.get(self.moldura, "simples"),
            cor_a=cor_para_banner(self.cor_a),
            cor_b=cor_para_banner(self.cor_b) if self.dividir else None,
            emblema=self.banner_pattern,
            escala=self.banner_pattern_scale_slider.value,
            dx=self.banner_pattern_dx_slider.value,
            dy=self.banner_pattern_dy_slider.value,
            contorno_escala=self.banner_contour_scale_slider.value,
            contorno_dx=self.banner_contour_dx_slider.value,
            contorno_dy=self.banner_contour_dy_slider.value,
        )
        chave_glifo = repr(camadas)
        chave_banner = (repr(sorted((k, v) for k, v in args_banner.items() if k != "emblema")),
                        id(self.banner_pattern), self.banner_pattern)
        cache = getattr(self, "_cache_preview", {})

        def icone():
            imagem = icon_gen.render(**args_icone)
            return imagem, image_data(icon_gen.reduzir(imagem, icon_gen.PCT_BRASAO))

        def glifo():
            datas = []
            for layer in camadas:
                try:
                    datas.append(os.path.getmtime(silhuetas.caminho_da_silhueta(layer.get("arma") or "")))
                except (OSError, TypeError, ValueError):
                    datas.append(None)
            chave = (chave_glifo, tuple(datas))
            if cache.get("glifo", (None,))[0] == chave:
                return cache["glifo"][1:] + (chave,)
            imagem = icon_gen.render_glifo(camadas)
            return imagem, image_data(imagem) if imagem else PIXEL_TRANSPARENTE, chave

        def banner():
            anterior = cache.get("banner")
            if anterior and anterior[0][:2] == chave_banner[:2] and anterior[0][2] is chave_banner[2]:
                return anterior[1:]
            imagem = banner_gen.render(**args_banner)
            return imagem, image_data(imagem)

        try:
            (self.icone, src_icone), (self.glifo, src_glifo, chave_glifo), (self.banner, src_banner) = \
                await asyncio.gather(asyncio.to_thread(icone), asyncio.to_thread(glifo), asyncio.to_thread(banner))
            self._cache_preview = {"glifo": (chave_glifo, self.glifo, src_glifo),
                                   "banner": (chave_banner, self.banner, src_banner)}
            self.preview.src = src_icone
            self.preview_glifo.src = src_glifo
            self.preview_banner.src = src_banner
            self.page.update()
        except (OSError, ValueError) as erro:
            show_error(self.page, "Pre-visualizacao", str(erro))

    async def adicionar_camada(self, _):
        self._store_layer_controls()
        self.camadas.append(self.camada_nova(0.8))
        self.camada_atual = len(self.camadas) - 1
        self._refresh_layers()
        self._build_weapons()
        await self._refresh_preview()

    async def remover_camada(self, _):
        if len(self.camadas) == 1:
            self.camadas[0] = self.camada_nova()
        else:
            del self.camadas[self.camada_atual]
            self.camada_atual = min(self.camada_atual, len(self.camadas) - 1)
        self.espelhar = self.camadas[self.camada_atual]["espelhar"]
        self._refresh_layers()
        self._build_weapons()
        await self._refresh_preview()

    async def mover_camada(self, direction):
        self._store_layer_controls()
        target = self.camada_atual + direction
        if 0 <= target < len(self.camadas):
            self.camadas[self.camada_atual], self.camadas[target] = self.camadas[target], self.camadas[self.camada_atual]
            self.camada_atual = target
            self._refresh_layers()
            await self._refresh_preview()

    async def sortear_semente(self, _):
        self.semente = random.randint(1, 99999)
        self.seed_field.value = str(self.semente)
        await self._refresh_preview()

    async def sortear_cores(self, _):
        self.cor_a, self.cor_b = random.sample(list(icon_gen.PALETA.values()), 2)
        self._build_appearance()
        for selected, card in self.palette_cards:
            card.border = ft.Border.all(
                2, TEXT if selected in (self.cor_a, self.cor_b) else OUTLINE
            )
        self.page.update()
        await self._refresh_preview()

    async def salvar_icone(self, _):
        self._store_layer_controls()
        used = {
            int(name[:-4]) for name in os.listdir(self.pasta_icones)
            if name[:-4].isdigit() and name.lower().endswith(".png")
        }
        suggested = next((number for number in range(self.numero_min, self.numero_max + 1)
                          if number not in used), self.numero_min)
        number = await self.app._ask_number("Salvar brasao", suggested)
        if number is None:
            return
        if number in used and not await self.app._confirm("Substituir icone", f"O icone {number} ja existe. Substituir?"):
            return
        try:
            icon_gen.reduzir(self.icone, icon_gen.PCT_BRASAO).save(
                os.path.join(self.pasta_icones, f"{number}.png")
            )
            glyph_path = os.path.join(self.pasta_icones, f"{number}_arma.png")
            if self.glifo is not None:
                self.glifo.save(glyph_path)
            elif os.path.isfile(glyph_path):
                os.remove(glyph_path)
            if self.banner is not None:
                self.banner.save(os.path.join(self.pasta_icones, f"{number}_banner.png"))
            self.app.numero_selecionado = number
            self.app.selecionados.clear()
            show_message(self.page, f"Brasao {number} salvo.")
            self.app._show_section(0)
        except OSError as erro:
            show_error(self.page, "Salvar brasao", str(erro))

    async def importar_silhueta(self, _):
        result = await self.app.file_picker.pick_files(
            dialog_title="Importar silhueta",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["png", "webp", "bmp", "tif", "tiff"],
            allow_multiple=False,
        )
        if not result:
            return
        path = result[0].path
        if not path:
            show_error(self.page, "Importar silhueta", "O arquivo nao pode ser acessado.")
            return
        try:
            mask = await asyncio.to_thread(silhuetas.carregar_silhueta, path)
        except (OSError, ValueError) as erro:
            show_error(self.page, "Importar silhueta", str(erro))
            return
        dialog = DialogoImportacao(self, mask, path)
        self.page.show_dialog(dialog.build())

    async def importar_padrao_banner(self, _):
        result = await self.app.file_picker.pick_files(
            dialog_title="Importar padrão do banner",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["png"],
            allow_multiple=False,
        )
        if not result or not result[0].path:
            return
        path = result[0].path
        try:
            with Image.open(path) as source:
                source.verify()
            with Image.open(path) as source:
                pattern = source.convert("RGBA")
            if pattern.getchannel("A").getextrema() == (255, 255):
                pattern.putalpha(silhuetas.carregar_mascara(path))
            if pattern.getchannel("A").getbbox() is None:
                raise ValueError("A imagem não contém um padrão visível.")
        except (OSError, ValueError) as erro:
            show_error(self.page, "Padrão do banner inválido", str(erro))
            return
        self.banner_library_dropdown.value = None
        await self._definir_padrao_banner(pattern, os.path.basename(path))

    async def _definir_padrao_banner(self, pattern, rotulo):
        """Padrao do tamanho do banner fica onde foi desenhado; os demais entram centralizados e ampliados."""
        if pattern.size == padroes_banner.TAMANHO:
            pattern, dx, dy = padroes_banner.posicionar(pattern)
            escala = 1.0
        else:
            pattern = pattern.crop(pattern.getchannel("A").getbbox())
            dx = dy = 0
            escala = min(3.0, max(0.1, round(400 / max(pattern.size) / 0.05) * 0.05))
        self.banner_pattern = pattern
        self.banner_pattern_scale_slider.value = escala
        self.banner_pattern_dx_slider.value = round(dx)
        self.banner_pattern_dy_slider.value = round(dy)
        self.banner_contour_scale_slider.value = 1.0
        self.banner_contour_dx_slider.value = self.banner_contour_dy_slider.value = 0
        self._sync_slider_value_fields()
        self.banner_pattern_status.value = rotulo
        self.remove_banner_pattern_button.disabled = False
        self.page.update()
        await self._refresh_preview()

    def atualizar_padroes_banner(self):
        nomes = padroes_banner.listar()
        self.banner_library_dropdown.options = [ft.DropdownOption(key=nome, text=nome) for nome in nomes]
        if self.banner_library_dropdown.value not in nomes:
            self.banner_library_dropdown.value = None

    async def _selecionar_padrao_banner(self, event):
        await self.aplicar_padrao_banner_da_biblioteca(event.control.value)

    async def aplicar_padrao_banner_da_biblioteca(self, nome):
        if not nome:
            return
        try:
            pattern = await asyncio.to_thread(padroes_banner.carregar, nome)
            if pattern.getchannel("A").getbbox() is None:
                raise ValueError("O padrão está vazio.")
        except (OSError, ValueError) as erro:
            show_error(self.page, "Padrão do banner", str(erro))
            return
        self.banner_library_dropdown.value = nome
        await self._definir_padrao_banner(pattern, nome)

    async def remover_padrao_banner(self, _):
        self.banner_pattern = None
        self.banner_library_dropdown.value = None
        self.banner_pattern_status.value = "Nenhum padrão importado"
        self.remove_banner_pattern_button.disabled = True
        await self._refresh_preview()

    async def remover_silhueta(self, _):
        name = self.camadas[self.camada_atual]["arma"]
        if not name:
            show_message(self.page, "Selecione uma silhueta na biblioteca primeiro.")
            return
        if not await self.app._confirm(
            "Remover silhueta",
            f"Remover '{name}' do catalogo? Icones ja salvos nao serao alterados.",
        ):
            return
        try:
            await asyncio.to_thread(silhuetas.remover, name)
        except OSError as erro:
            show_error(self.page, "Remover silhueta", str(erro))
            return
        for layer in self.camadas:
            if layer["arma"] == name:
                layer["arma"] = ""
        self._refresh_layers()
        self._build_weapons()
        await self._refresh_preview()

    async def _build_after_import(self, names):
        self._build_weapons()
        self._definir_silhueta(names[0])
        self._refresh_layers()
        await self._refresh_preview()

    @staticmethod
    def _hex(color):
        return "#%02X%02X%02X" % color


PREDEFINICOES = {
    "Liso": dict(intensity=0.55, bevel=0.0, forjado=0.0, tamanho=1.0, riscos=0.0, brilho=1.0),
    "Forjado": dict(intensity=0.55, bevel=0.0, forjado=1.0, tamanho=1.0, riscos=1.0, brilho=1.0),
    "Gasto": dict(intensity=0.55, bevel=0.0, forjado=1.5, tamanho=0.7, riscos=2.5, brilho=0.6),
}


class DialogoImportacao:
    def __init__(self, generator, mask, path, ao_importar=None):
        self.generator = generator
        self.ao_importar = ao_importar
        self.page = generator.page
        self.mask = mask
        self.intensity = 0.55
        self.bevel = 0.0
        self.acabamento = chanfro.Acabamento()
        self.base_name = re.sub(
            r"[^A-Za-z0-9_]+", "_", os.path.splitext(os.path.basename(path))[0]
        ).strip("_") or "silhueta"
        self.progress = ft.ProgressBar(visible=False, color=ACCENT)
        self.name_field = ft.TextField(label="Nome", value=self.base_name, width=300)
        self.intensity_slider = ft.Slider(min=0.1, max=1.5, value=self.intensity, expand=True)
        self.bevel_slider = ft.Slider(min=0, max=1, value=self.bevel, expand=True)
        self.forge_slider = ft.Slider(min=0, max=3, divisions=30, value=self.acabamento.forjado, expand=True)
        self.size_slider = ft.Slider(min=0.5, max=2, divisions=30, value=self.acabamento.tamanho, expand=True)
        self.scratch_slider = ft.Slider(min=0, max=3, divisions=30, value=self.acabamento.riscos, expand=True)
        self.shine_slider = ft.Slider(min=0, max=2, divisions=20, value=self.acabamento.brilho, expand=True)
        self.preview_box = ft.Container(width=480, height=480, alignment=ft.Alignment.CENTER)
        self.preview_frame = surface(
            ft.Stack(
                width=480,
                height=480,
                controls=[self.preview_box, ft.Container(content=self.progress, left=16, right=16, bottom=12)],
            ),
            padding=0,
            width=480,
        )
        self._generation = 0
        self.preview_task = None

    def _build_items(self):
        self._generation += 1
        if self.preview_box.content is None:
            self.preview_box.content = ft.Text("Preparando previa...", size=12, color=MUTED)
        self.progress.visible = True
        if self.preview_task is None or self.preview_task.done():
            self.preview_task = asyncio.create_task(self._render_previews())

    async def _render_previews(self):
        # um render por vez: pedidos feitos durante o render viram um unico render com os valores mais recentes
        while True:
            generation = self._generation
            intensity, bevel, acabamento = self.intensity, self.bevel, self.acabamento
            preview = await asyncio.to_thread(miniatura_silhueta, self.mask, intensity, bevel, acabamento)
            if generation == self._generation:
                break
        self.preview_box.content = ft.Image(src=image_data(preview), width=480, height=480, fit=ft.BoxFit.CONTAIN)
        self.progress.visible = False
        self.page.update()

    def build(self):
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Importar silhueta"),
            content=ft.Row(
                vertical_alignment=ft.CrossAxisAlignment.START,
                controls=[
                    self.preview_frame,
                    ft.Column(
                        width=400,
                        spacing=18,
                        controls=[
                            ft.Column(
                                spacing=6,
                                tight=True,
                                controls=[
                                    ft.Text("Predefinicao", size=12, color=MUTED),
                                    ft.Row(
                                        controls=[
                                            ft.OutlinedButton(nome, data=nome, expand=True,
                                                              on_click=self._click_preset)
                                            for nome in PREDEFINICOES
                                        ],
                                    ),
                                ],
                            ),
                            ft.Column(
                                spacing=0,
                                tight=True,
                                controls=[
                                    ft.Row(
                                        controls=[ft.Text(rotulo, width=120), controle],
                                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                    )
                                    for rotulo, controle in (
                                        ("Intensidade da luz", self.intensity_slider),
                                        ("Chanfro", self.bevel_slider),
                                        ("Forjado", self.forge_slider),
                                        ("Tamanho amassados", self.size_slider),
                                        ("Riscos", self.scratch_slider),
                                        ("Brilho", self.shine_slider),
                                    )
                                ],
                            ),
                            ft.Row(
                                controls=[
                                    ft.Button("Aplicar", icon=ft.Icons.REFRESH, expand=True,
                                              on_click=self._apply),
                                    ft.OutlinedButton("Variar", icon=ft.Icons.SHUFFLE, expand=True,
                                                      on_click=self._vary),
                                ],
                            ),
                            self.name_field,
                        ],
                    ),
                ],
                width=900,
                height=490,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.Button("Importar", icon=ft.Icons.CHECK, on_click=self.importar),
            ],
        )
        self._build_items()
        return dialog

    def _read_sliders(self):
        self.intensity = float(self.intensity_slider.value)
        self.bevel = float(self.bevel_slider.value)
        self.acabamento = chanfro.Acabamento(
            forjado=float(self.forge_slider.value),
            tamanho=float(self.size_slider.value),
            riscos=float(self.scratch_slider.value),
            brilho=float(self.shine_slider.value),
            semente=self.acabamento.semente,
        )

    async def _vary(self, _):
        self._read_sliders()
        self.acabamento = dataclasses.replace(self.acabamento, semente=random.getrandbits(32))
        self._build_items()
        self.page.update()

    async def _click_preset(self, event):
        await self._preset(event.control.data)

    async def _preset(self, nome):
        valores = PREDEFINICOES[nome]
        self.acabamento = dataclasses.replace(self.acabamento, semente=0)
        self.intensity_slider.value = valores["intensity"]
        self.bevel_slider.value = valores["bevel"]
        self.forge_slider.value = valores["forjado"]
        self.size_slider.value = valores["tamanho"]
        self.scratch_slider.value = valores["riscos"]
        self.shine_slider.value = valores["brilho"]
        await self._apply(None)

    async def _apply(self, _):
        self._read_sliders()
        self._build_items()
        self.page.update()

    async def importar(self, _):
        name = re.sub(r"[^A-Za-z0-9_]+", "_", self.name_field.value or "").strip("_")
        if not name:
            show_message(self.page, "Informe um nome para a silhueta.")
            return
        if silhuetas.existe(name) and not await self.generator.app._confirm(
            "Substituir silhueta", f"Substituir {name}?"
        ):
            return
        try:
            await asyncio.to_thread(
                silhuetas.salvar,
                name,
                self.mask,
                self.intensity,
                self.bevel,
                acabamento=self.acabamento,
            )
        except OSError as erro:
            show_error(self.page, "Importar silhueta", str(erro))
            return
        self.page.pop_dialog()
        await self.generator._build_after_import([name])
        if self.ao_importar is not None:
            await self.ao_importar(name)
