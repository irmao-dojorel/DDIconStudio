"""Flet desktop interface for browsing vocation icons and building the game PAK."""
import asyncio
import os
import re
import shutil
import sys
import webbrowser

import flet as ft
from PIL import Image

from ddiconstudio import app_paths, icon_gen, pak_builder
from ddiconstudio.gui import editor_silhuetas, icon_gen_gui
from ddiconstudio.gui.theme import (
    ACCENT, BACKGROUND, MUTED, OUTLINE, SURFACE_HIGH, app_icon, configure_page,
    heading, image_data, show_error, show_message, surface,
)
from ddiconstudio.pak_builder import ICONE_MAX, ICONE_MIN

class App:
    SECAO_EDITOR = 2

    def __init__(self, page: ft.Page):
        self.page = page
        configure_page(page)
        page.window.prevent_close = True
        page.window.on_event = self._on_window_event
        self._layout_width = page.window.width
        self._layout_height = page.window.height
        configuracao = app_paths.carregar()
        self.pasta_icones = configuracao.get("icons_dir") or app_paths.ICONS_DEFAULT
        try:
            os.makedirs(self.pasta_icones, exist_ok=True)
        except OSError as erro:
            show_error(page, "Pasta de icones", str(erro))
            self.pasta_icones = app_paths.ICONS_DEFAULT
            os.makedirs(self.pasta_icones, exist_ok=True)

        self.pak_base = configuracao.get("base_pak")
        if os.path.basename(self.pak_base or "").casefold() == "vsb_vocation_icons.pak":
            self.pak_base = app_paths.BASE_PAK
        if not self.pak_base or not os.path.isfile(self.pak_base):
            self.pak_base = app_paths.BASE_PAK
        self.file_picker = ft.FilePicker()
        page.services.append(self.file_picker)
        self.secao = 0
        self.generator = None
        self.editor = None
        self.numero_selecionado = None
        self.selecionados = set()
        self.modo_teste = False
        self.gerando = False
        self.log = ft.Text("Pronto para gerar.", size=12, color=MUTED, selectable=True)
        self.status = ft.Text("Pronto", size=12, color=MUTED)
        self.content = ft.Container(expand=True)
        self.rail = ft.NavigationRail(
            selected_index=0,
            extended=True,
            min_extended_width=190,
            bgcolor=BACKGROUND,
            indicator_color="#263846",
            selected_label_text_style=ft.TextStyle(color=ACCENT, weight=ft.FontWeight.W_600),
            unselected_label_text_style=ft.TextStyle(color=MUTED),
            on_change=self._on_navigation,
            destinations=[
                ft.NavigationRailDestination(icon=ft.Icons.GRID_VIEW_OUTLINED,
                                             selected_icon=ft.Icons.GRID_VIEW, label="Biblioteca"),
                ft.NavigationRailDestination(icon=ft.Icons.AUTO_FIX_HIGH_OUTLINED,
                                             selected_icon=ft.Icons.AUTO_FIX_HIGH, label="Criar brasao"),
                ft.NavigationRailDestination(icon=ft.Icons.DRAW_OUTLINED,
                                             selected_icon=ft.Icons.DRAW, label="Editor de silhuetas"),
                ft.NavigationRailDestination(icon=ft.Icons.BUILD_CIRCLE_OUTLINED,
                                             selected_icon=ft.Icons.BUILD_CIRCLE, label="Montar PAK"),
            ],
        )
        self.body = ft.Container(expand=True)
        self._compose()
        page.on_resize = self._on_resize
        self._show_section(0)

    def _compose(self):
        self.scaled_content = ft.Container(
            width=self._layout_width,
            height=self._layout_height,
            scale=ft.Scale(scale=1, alignment=ft.Alignment.CENTER),
            content=ft.Column(
                expand=True,
                spacing=0,
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                app_icon(32),
                                ft.Column(
                                    controls=[
                                        ft.Text("DDIconStudio", size=19, weight=ft.FontWeight.BOLD),
                                        ft.Text("Dragon's Dogma 2  ·  Gerenciador de icones", size=11, color=MUTED),
                                    ],
                                    spacing=0,
                                    tight=True,
                                ),
                                ft.Container(expand=True),
                                self.status,
                            ],
                            spacing=12,
                        ),
                        padding=ft.Padding(left=24, top=14, right=24, bottom=14),
                        border=ft.Border.only(bottom=ft.BorderSide(1, OUTLINE)),
                    ),
                    ft.Row(
                        expand=True,
                        spacing=0,
                        controls=[
                            self.rail,
                            ft.VerticalDivider(width=1, color=OUTLINE),
                            self.body,
                        ],
                    ),
                ],
            ),
        )
        self.page.add(
            ft.Container(
                content=self.scaled_content,
                expand=True,
                alignment=ft.Alignment.CENTER,
            )
        )

    def _on_resize(self, event):
        width = getattr(event, "width", None) or self.page.width or self._layout_width
        height = getattr(event, "height", None) or self.page.height or self._layout_height
        scale = max(1.0, min(width / self._layout_width, height / self._layout_height))
        self.scaled_content.width = width / scale
        self.scaled_content.height = height / scale
        self.scaled_content.scale = ft.Scale(scale=scale, alignment=ft.Alignment.CENTER)
        if self.editor is not None:
            self.editor.redimensionar()
        self.page.update()

    async def _on_navigation(self, event):
        self._show_section(int(event.control.selected_index))

    def garantir_gerador(self):
        """O gerador recebe as silhuetas importadas; o editor pode importar antes de a secao ser aberta."""
        if self.generator is None:
            self.generator = icon_gen_gui.Gerador(self)
            self.generator.build()
        return self.generator

    def _show_section(self, index):
        self.secao = index
        self.rail.selected_index = index
        if index == 0:
            self.body.content = self._build_library()
        elif index == 1:
            self.body.content = self.garantir_gerador().root
        elif index == self.SECAO_EDITOR:
            if self.editor is None:
                self.editor = editor_silhuetas.EditorSilhuetas(self)
                self.body.content = self.editor.build()
            else:
                self.body.content = self.editor.root
        else:
            self.body.content = self._build_pak()
        self.page.update()

    def _build_library(self):
        icons = self.icones_na_pasta()
        if not icons:
            list_content = ft.Container(
                content=ft.Column(
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                    controls=[
                        ft.Icon(ft.Icons.IMAGE_SEARCH, size=42, color=MUTED),
                        ft.Text("Sua biblioteca ainda esta vazia", size=16, weight=ft.FontWeight.W_600),
                        ft.Text("Crie um brasao ou importe um arquivo PNG para comecar.", color=MUTED),
                    ],
                    spacing=8,
                ),
                expand=True,
                alignment=ft.Alignment.CENTER,
            )
        else:
            rows = []
            for numero, nome in sorted(icons.items()):
                fora = not ICONE_MIN <= numero <= ICONE_MAX
                rows.append(
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Checkbox(
                                    value=numero in self.selecionados,
                                    on_change=lambda e, n=numero: self.page.run_task(self._toggle_selection, n, e),
                                ),
                                ft.Container(
                                    content=ft.Text(str(numero), weight=ft.FontWeight.BOLD, color=ACCENT),
                                    width=48,
                                ),
                                ft.Column(
                                    controls=[
                                        ft.Text(nome, weight=ft.FontWeight.W_500),
                                        ft.Text(f"Folha {numero // 16}  ·  Celula {numero % 16}", size=11, color=MUTED),
                                    ],
                                    spacing=2,
                                    expand=True,
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.VISIBILITY_OUTLINED,
                                    tooltip="Pre-visualizar",
                                    on_click=lambda _, n=numero: self.page.run_task(self._select_icon, n),
                                ),
                            ],
                            spacing=8,
                        ),
                        padding=ft.Padding(left=10, top=5, right=10, bottom=5),
                        border=ft.Border.only(bottom=ft.BorderSide(1, OUTLINE)),
                        bgcolor=SURFACE_HIGH if numero == self.numero_selecionado else None,
                        on_click=lambda _, n=numero: self.page.run_task(self._select_icon, n),
                    )
                )
                if fora:
                    rows[-1].content.controls[2].controls.append(
                        ft.Text(f"Fora do intervalo {ICONE_MIN}..{ICONE_MAX}", size=10, color="#E5A05A")
                    )
            list_content = ft.ListView(controls=rows, spacing=0, expand=True)

        preview = self._build_icon_preview(self.numero_selecionado)
        actions = ft.Row(
            wrap=True,
            controls=[
                ft.Button("Adicionar PNG", icon=ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED,
                          on_click=self._add_pngs),
                ft.Button("Criar brasao", icon=ft.Icons.AUTO_FIX_HIGH, on_click=self._go_generator),
                ft.Button("Trocar numero", icon=ft.Icons.SWAP_HORIZ, on_click=self._rename_icon,
                          disabled=self.numero_selecionado is None),
                ft.Button("Remover selecionados", icon=ft.Icons.DELETE_OUTLINE,
                          on_click=self._remove_icons, disabled=not self.selecionados),
                ft.IconButton(icon=ft.Icons.FOLDER_OPEN_OUTLINED, tooltip="Abrir pasta de icones",
                              on_click=self._open_icons_folder),
            ],
        )
        return ft.Container(
            padding=24,
            expand=True,
            content=ft.Column(
                expand=True,
                spacing=16,
                controls=[
                    heading("Biblioteca de icones", "Organize seus brasoes e confira os arquivos associados."),
                    actions,
                    ft.Row(
                        expand=True,
                        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                        spacing=16,
                        controls=[
                            surface(
                                ft.Column(
                                    controls=[
                                        ft.Row(
                                            controls=[
                                                ft.Text(f"{len(icons)} icone(s)", color=MUTED, expand=True),
                                                ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Atualizar",
                                                              on_click=self._refresh_library),
                                            ]
                                        ),
                                        list_content,
                                    ],
                                    expand=True,
                                    spacing=8,
                                ),
                                expand=True,
                            ),
                            surface(preview, width=320),
                        ],
                    ),
                ],
            ),
        )

    def _build_icon_preview(self, numero):
        if numero is None:
            return ft.Column(
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Text("Pre-visualizacao", size=16, weight=ft.FontWeight.W_600),
                    ft.Icon(ft.Icons.IMAGE_OUTLINED, size=48, color=MUTED),
                    ft.Text("Selecione um icone na lista.", color=MUTED),
                ],
                spacing=12,
            )
        caminho = os.path.join(self.pasta_icones, f"{numero}.png")
        try:
            imagem = Image.open(caminho).convert("RGBA")
            imagem = icon_gen.reduzir(imagem, icon_gen.PCT_BRASAO)
            imagem.thumbnail((220, 220), Image.Resampling.LANCZOS)
            brasao = ft.Image(src=image_data(imagem), width=220, height=220,
                              fit=ft.BoxFit.CONTAIN)
        except (OSError, ValueError) as erro:
            brasao = ft.Text(f"Nao foi possivel ler o PNG:\n{erro}", color="#F08080")
        glifo = self.caminho_glifo(numero)
        banner = self.caminho_banner(numero)
        extras = []
        if os.path.isfile(glifo):
            try:
                with Image.open(glifo) as image:
                    extras.append(ft.Image(src=image_data(image.convert('RGBA')),
                                           width=84, height=84, fit=ft.BoxFit.CONTAIN))
            except OSError:
                extras.append(ft.Text("Painel ilegivel", size=11, color="#F08080"))
        else:
            extras.append(ft.Text("Painel: usa o brasao", size=11, color=MUTED))
        if os.path.isfile(banner):
            try:
                with Image.open(banner) as image:
                    extras.append(ft.Image(src=image_data(image.convert('RGBA')),
                                           width=64, height=128, fit=ft.BoxFit.CONTAIN))
            except OSError:
                extras.append(ft.Text("Banner ilegivel", size=11, color="#F08080"))
        else:
            extras.append(ft.Text("Sem banner", size=11, color=MUTED))
        return ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(f"Icone {numero}", size=16, weight=ft.FontWeight.W_600),
                brasao,
                ft.Text(f"Folha {numero // 16}   ·   Celula {numero % 16}", size=12, color=MUTED),
                ft.Row(controls=extras, alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.START),
            ],
            spacing=12,
            tight=True,
        )

    def _build_pak(self):
        self.icons_path_field = ft.TextField(
            label="Pasta de icones",
            value=self.pasta_icones,
            read_only=True,
            expand=True,
            dense=True,
        )
        self.pak_path_field = ft.TextField(
            label="PAK base (vanilla)",
            value=self.pak_base,
            expand=True,
            dense=True,
        )
        self.test_switch = ft.Switch(
            label="Gerar circulos de teste (16..31)",
            value=self.modo_teste,
            on_change=lambda e: setattr(self, "modo_teste", bool(e.control.value)),
        )
        self.progress = ft.ProgressBar(visible=False, color=ACCENT, height=4)
        self.generate_button = ft.Button(
            "Gerar PAK",
            icon=ft.Icons.BUILD_CIRCLE,
            on_click=self._generate_pak,
            disabled=self.gerando,
        )
        layout = ft.Container(
            padding=24,
            expand=True,
            content=ft.Column(
                spacing=18,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    heading("Montar PAK", "Gere o pacote de icones, simbolos do painel e banners."),
                    surface(
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        self.icons_path_field,
                                        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Selecionar pasta",
                                                      on_click=self._choose_icons_folder),
                                    ]
                                ),
                                ft.Row(
                                    controls=[
                                        self.pak_path_field,
                                        ft.IconButton(icon=ft.Icons.FOLDER_OPEN, tooltip="Selecionar PAK base",
                                                      on_click=self._choose_base_pak),
                                    ]
                                ),
                                ft.Row(
                                    controls=[
                                        self.test_switch,
                                        ft.Button("Abrir saida", icon=ft.Icons.FOLDER_OPEN_OUTLINED,
                                                  on_click=self._open_output),
                                        ft.Button("Ver folhas", icon=ft.Icons.GRID_ON, on_click=self._show_sheets),
                                        self.generate_button,
                                    ],
                                    wrap=True,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                self.progress,
                            ],
                            spacing=12,
                        ),
                    ),
                    surface(
                        ft.Column(
                            controls=[
                                ft.Row(
                                    controls=[
                                        ft.Text("Log de processamento", size=15, weight=ft.FontWeight.W_600),
                                        ft.Container(expand=True),
                                    ]
                                ),
                                ft.Container(
                                    content=ft.Column(
                                        controls=[self.log],
                                        tight=True,
                                    ),
                                    bgcolor="#10161D",
                                    padding=14,
                                    border_radius=8,
                                ),
                            ],
                            spacing=10,
                        ),
                    ),
                ],
            ),
        )
        return layout

    def icones_na_pasta(self):
        arquivos = {}
        for nome in os.listdir(self.pasta_icones):
            achou = re.fullmatch(r"(\d+)\.png", nome, re.I)
            if achou:
                arquivos[int(achou.group(1))] = nome
        return arquivos

    async def _toggle_selection(self, numero, event):
        if event.control.value:
            self.selecionados.add(numero)
        else:
            self.selecionados.discard(numero)
        self._show_section(0)

    async def _select_icon(self, numero):
        self.numero_selecionado = numero
        self._show_section(0)

    async def _go_generator(self, _):
        self._show_section(1)

    async def _refresh_library(self, _):
        self._show_section(0)

    async def _add_pngs(self, _):
        try:
            result = await self.file_picker.pick_files(
                dialog_title="Importar icones PNG",
                file_type=ft.FilePickerFileType.IMAGE,
                allowed_extensions=["png"],
                allow_multiple=True,
            )
            if not result:
                return
            last_added = None
            for picked in result:
                if not picked.path:
                    raise OSError(f"Nao foi possivel acessar {picked.name}.")
                in_use = self.icones_na_pasta()
                match = re.fullmatch(r"(\d+)\.png", os.path.basename(picked.path), re.I)
                suggested = int(match.group(1)) if match and ICONE_MIN <= int(match.group(1)) <= ICONE_MAX else self.primeiro_numero_livre(in_use)
                if suggested is None:
                    show_error(self.page, "Biblioteca cheia", f"Todos os numeros de icone ({ICONE_MIN}..{ICONE_MAX}) ja estao em uso.")
                    break
                number = await self._ask_number(os.path.basename(picked.path), suggested)
                if number is None:
                    continue
                if number in in_use and not await self._confirm("Substituir icone", f"O icone {number} ja existe. Substituir?"):
                    continue
                try:
                    with Image.open(picked.path) as image:
                        image.verify()
                except (OSError, ValueError) as erro:
                    show_error(self.page, "PNG invalido", f"{picked.name}: {erro}")
                    continue
                shutil.copyfile(picked.path, os.path.join(self.pasta_icones, f"{number}.png"))
                self.apagar_glifo(number)
                last_added = number
            self.numero_selecionado = last_added
            self.selecionados.clear()
            self._show_section(0)
        except (OSError, ValueError) as erro:
            show_error(self.page, "Importar PNG", str(erro))

    async def _rename_icon(self, _):
        if self.numero_selecionado is None:
            show_message(self.page, "Selecione um icone.")
            return
        new_number = await self._ask_number("Trocar numero", self.numero_selecionado)
        old_number = self.numero_selecionado
        if new_number is None or new_number == old_number:
            return
        if new_number in self.icones_na_pasta():
            show_error(self.page, "Numero em uso", f"O icone {new_number} ja existe.")
            return
        moves = [(os.path.join(self.pasta_icones, f"{old_number}.png"),
                  os.path.join(self.pasta_icones, f"{new_number}.png"))]
        moves.extend((
            (self.caminho_glifo(old_number), self.caminho_glifo(new_number)),
            (self.caminho_banner(old_number), self.caminho_banner(new_number)),
        ))
        moves = [(source, target) for source, target in moves if source.endswith(".png") and os.path.isfile(source)]
        conflicts = [target for _, target in moves if os.path.exists(target)]
        if conflicts:
            show_error(self.page, "Numero em uso", f"Um arquivo associado ao icone {new_number} ja existe.")
            return

        moved = []
        try:
            for source, target in moves:
                os.rename(source, target)
                moved.append((source, target))
        except OSError as erro:
            rollback_errors = []
            for source, target in reversed(moved):
                try:
                    os.rename(target, source)
                except OSError as rollback_error:
                    rollback_errors.append(f"{target}: {rollback_error}")
            detalhe = str(erro)
            if rollback_errors:
                detalhe += "\nFalha ao restaurar: " + "; ".join(rollback_errors)
            show_error(self.page, "Trocar numero", detalhe)
            return
        self.numero_selecionado = new_number
        self._show_section(0)

    async def _remove_icons(self, _):
        targets = sorted(self.selecionados)
        if not targets:
            return
        if not await self._confirm("Remover icones", f"Remover {len(targets)} icone(s) da pasta?"):
            return
        try:
            for number in targets:
                os.remove(os.path.join(self.pasta_icones, f"{number}.png"))
                self.apagar_glifo(number)
        except OSError as erro:
            show_error(self.page, "Remover icones", str(erro))
            return
        self.selecionados.clear()
        if self.numero_selecionado in targets:
            self.numero_selecionado = None
        self._show_section(0)

    async def _choose_icons_folder(self, _):
        path = await self.file_picker.get_directory_path(
            dialog_title="Selecionar pasta de icones",
            initial_directory=self.pasta_icones,
        )
        if path:
            self.pasta_icones = os.path.normpath(path)
            os.makedirs(self.pasta_icones, exist_ok=True)
            if self.generator is not None:
                self.generator.pasta_icones = self.pasta_icones
            self._show_section(self.secao)

    async def _choose_base_pak(self, _):
        result = await self.file_picker.pick_files(
            dialog_title="Selecionar PAK base",
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["pak"],
            allow_multiple=False,
        )
        if result and result[0].path:
            self.pak_base = result[0].path
            self.pak_path_field.value = self.pak_base
            self.page.update()

    async def _open_icons_folder(self, _):
        await self._open_path(self.pasta_icones)

    async def _open_output(self, _):
        os.makedirs(self.pasta_saida, exist_ok=True)
        await self._open_path(self.pasta_saida)

    @staticmethod
    async def _open_path(path):
        if sys.platform == "win32":
            os.startfile(path)
        else:
            webbrowser.open(f"file://{path}")

    async def _show_sheets(self, _):
        names = sorted(
            name for name in os.listdir(self.pasta_saida)
            if re.fullmatch(r"preview_sheet_\d+\.png", name)
        ) if os.path.isdir(self.pasta_saida) else []
        if not names:
            show_message(self.page, "Nenhuma folha gerada ainda.")
            return
        selector = ft.Dropdown(
            label="Folha",
            value=names[0],
            options=[ft.DropdownOption(key=name, text=name) for name in names],
            width=280,
        )
        with Image.open(os.path.join(self.pasta_saida, names[0])) as image:
            first_image = image.convert("RGBA")
        preview = ft.Image(
            src=image_data(first_image),
            width=560,
            height=560,
            fit=ft.BoxFit.CONTAIN,
        )

        def change_sheet(event):
            with Image.open(os.path.join(self.pasta_saida, event.control.value)) as image:
                preview.src = image_data(image.convert("RGBA"))
            self.page.update()

        selector.on_select = change_sheet
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Folhas geradas"),
                content=ft.Column([selector, preview], tight=True, scroll=ft.ScrollMode.AUTO),
                actions=[ft.TextButton("Fechar", on_click=lambda _: self.page.pop_dialog())],
            )
        )

    async def _generate_pak(self, _):
        if self.gerando:
            return
        try:
            if self.modo_teste:
                icons = {number: None for number in range(16, 32)}
                glyphs = banners = None
            else:
                icons = self.icones_para_pak()
                glyphs = self.glifos_para_pak()
                banners = self.banners_para_pak()
                if not icons:
                    show_message(self.page, f"Adicione um PNG entre {ICONE_MIN} e {ICONE_MAX} ou ative o modo de teste.")
                    return
            self.gerando = True
            self.generate_button.disabled = True
            self.progress.visible = True
            self.log.value = "Gerando PAK...\n"
            self.status.value = "Gerando..."
            self.page.update()
            messages = []
            await asyncio.to_thread(
                pak_builder.montar_pak,
                icons,
                self.pasta_saida,
                base_pak=(self.pak_path_field.value or "").strip() or None,
                glifos=glyphs,
                banners=banners or None,
                log=messages.append,
            )
            self.log.value = "\n".join(messages + ["Concluido."])
            self.status.value = "PAK gerado"
            show_message(self.page, "PAK gerado com sucesso.")
        except Exception as erro:
            self.log.value = f"Falha: {type(erro).__name__}: {erro}"
            self.status.value = "Falha ao gerar"
            show_error(self.page, "Falha ao gerar PAK", str(erro))
        finally:
            self.gerando = False
            if hasattr(self, "generate_button"):
                self.generate_button.disabled = False
                self.progress.visible = False
            self.page.update()

    def icones_para_pak(self):
        lado = pak_builder.LADO_CELULA_LISTA
        icones = {}
        for numero in self.icones_na_pasta():
            if ICONE_MIN <= numero <= ICONE_MAX:
                with Image.open(os.path.join(self.pasta_icones, f"{numero}.png")) as source:
                    imagem = source.convert("RGBA")
                if imagem.size != (lado, lado):
                    imagem = imagem.resize((lado, lado), Image.Resampling.LANCZOS)
                icones[numero] = icon_gen.reduzir(imagem, icon_gen.PCT_BRASAO)
        return icones

    def glifos_para_pak(self):
        glifos = {}
        for numero in self.icones_na_pasta():
            if ICONE_MIN <= numero <= ICONE_MAX:
                origem = self.caminho_glifo(numero)
                if not os.path.isfile(origem):
                    origem = os.path.join(self.pasta_icones, f"{numero}.png")
                with Image.open(origem) as image:
                    glifos[numero] = image.convert("RGBA")
        return glifos

    def banners_para_pak(self):
        banners = {}
        for numero in self.icones_na_pasta():
            origem = self.caminho_banner(numero)
            if pak_builder.BANNER_MIN <= numero <= pak_builder.BANNER_MAX and os.path.isfile(origem):
                with Image.open(origem) as image:
                    banners[numero] = image.convert("RGBA")
        return banners

    def primeiro_numero_livre(self, em_uso):
        return next((numero for numero in range(ICONE_MIN, ICONE_MAX + 1) if numero not in em_uso), None)

    def caminho_glifo(self, numero):
        return os.path.join(self.pasta_icones, f"{numero}_arma.png")

    def caminho_banner(self, numero):
        return os.path.join(self.pasta_icones, f"{numero}_banner.png")

    def apagar_glifo(self, numero):
        for caminho in (self.caminho_glifo(numero), self.caminho_banner(numero)):
            if os.path.isfile(caminho):
                os.remove(caminho)

    @property
    def pasta_saida(self):
        return os.path.join(self.pasta_icones, "out")

    async def _ask_number(self, title, suggested):
        number_field = ft.TextField(
            label=f"Numero do icone ({ICONE_MIN}..{ICONE_MAX})",
            value=str(suggested),
            keyboard_type=ft.KeyboardType.NUMBER,
            autofocus=True,
        )
        result = {"number": None}

        def submit(_):
            try:
                number = int(number_field.value)
                if not ICONE_MIN <= number <= ICONE_MAX:
                    raise ValueError
            except (TypeError, ValueError):
                number_field.error_text = f"Informe um numero de {ICONE_MIN} a {ICONE_MAX}."
                self.page.update()
                return
            number_field.error_text = None
            result["number"] = number
            self.page.pop_dialog()
            if not future.done():
                future.set_result(True)

        future = asyncio.get_running_loop().create_future()
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=number_field,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self._close_prompt(future, None)),
                ft.Button("Continuar", on_click=submit),
            ],
        )
        self.page.show_dialog(dialog)
        await future
        return result["number"]

    async def _confirm(self, title, message):
        result = {"confirmed": False}
        future = asyncio.get_running_loop().create_future()

        def finish(confirmed):
            result["confirmed"] = confirmed
            self.page.pop_dialog()
            if not future.done():
                future.set_result(True)

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: finish(False)),
                ft.Button("Confirmar", on_click=lambda _: finish(True)),
            ],
        )
        self.page.show_dialog(dialog)
        await future
        return result["confirmed"]

    def _close_prompt(self, future, _value):
        self.page.pop_dialog()
        if not future.done():
            future.set_result(True)

    async def _on_window_event(self, event):
        if event.type != ft.WindowEventType.CLOSE:
            return
        base_pak = self.pak_base
        if getattr(self, "pak_path_field", None) is not None:
            base_pak = self.pak_path_field.value or base_pak
        configuracao = {
            "icons_dir": self.pasta_icones,
            "base_pak": base_pak,
        }
        if app_paths.salvar(configuracao):
            await self._fechar_janela()
            return

        async def permanecer(_):
            self.page.pop_dialog()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Preferências não salvas"),
                content=ft.Text("Não foi possível salvar config.json. Você pode continuar no aplicativo ou fechar sem salvar."),
                actions=[
                    ft.TextButton("Permanecer aberto", on_click=permanecer),
                    ft.Button("Fechar sem salvar", on_click=self._fechar_sem_salvar),
                ],
            )
        )

    async def _fechar_sem_salvar(self, _event=None):
        self.page.pop_dialog()
        await self._fechar_janela()

    async def _fechar_janela(self, _event=None):
        self.page.window.prevent_close = False
        await self.page.window.close()


def main(page: ft.Page):
    App(page)
