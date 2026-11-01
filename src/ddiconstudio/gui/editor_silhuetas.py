"""Editor de silhuetas: desenha a silhueta do icone de vocacao ou o padrao bordado do banner."""
import asyncio
import math
import os
import re

import flet as ft
import flet.canvas as cv
from PIL import Image

from ddiconstudio import banner_gen, desenho, icon_gen, padroes_banner, silhuetas
from ddiconstudio.gui.icon_gen_gui import BANNER_POR_MOLDURA, DialogoImportacao
from ddiconstudio.gui.theme import (
    ACCENT, BACKGROUND, MUTED, OUTLINE, PIXEL_TRANSPARENTE, SURFACE_HIGH, TEXT, heading, image_data,
    show_error, show_message, surface,
)

LADO_TELA = 600
MIN_TELA, MAX_TELA = 380, 760
MIN_PAINEIS = 400
ESPACO = 16
# menu lateral (190 + divisoria), margens (2 x 20), barra de ferramentas (50), espacos e barra de rolagem
LARGURA_FIXA = 191 + 40 + 50 + 2 * ESPACO + 14
ICONE, BANNER = "icone", "banner"
COR_FORA = (17, 24, 32, 255)
COR_FUNDO = (36, 52, 66, 255)
COR_TINTA = (236, 240, 244)
COR_GUIA = (120, 128, 138)
COR_ADICIONAR = "#A8C5D6"
COR_RECORTAR = "#E07070"
RAIO_FECHAR = 9   # px da tela: clicar perto do primeiro ponto fecha o poligono
EXTENSOES = ["png", "webp", "bmp", "tif", "tiff", "jpg", "jpeg"]

# nome: (rotulo, icone, tecla)
FERRAMENTAS = {
    "pincel": ("Pincel", ft.Icons.BRUSH, "B"),
    "borracha": ("Borracha", ft.Icons.AUTO_FIX_NORMAL, "E"),
    "linha": ("Linha", ft.Icons.SHOW_CHART, "L"),
    "laco": ("Laço", ft.Icons.GESTURE, "A"),
    "poligono": ("Polígono", ft.Icons.POLYLINE, "P"),
    "curva": ("Curva", ft.Icons.ROUTE, "C"),
    "retangulo": ("Retângulo", ft.Icons.CROP_SQUARE, "R"),
    "elipse": ("Elipse", ft.Icons.CIRCLE_OUTLINED, "O"),
    "estrela": ("Estrela / polígono regular", ft.Icons.STAR_BORDER, "S"),
    "balde": ("Balde", ft.Icons.FORMAT_COLOR_FILL, "G"),
    "mover": ("Mover desenho", ft.Icons.OPEN_WITH, "V"),
    "mao": ("Mão (mover a vista)", ft.Icons.PAN_TOOL, "H"),
}
DICAS = {
    "pincel": "Arraste para pintar. [ e ] mudam o tamanho.",
    "borracha": "Arraste para apagar. [ e ] mudam o tamanho.",
    "linha": "Arraste do início ao fim da linha.",
    "laco": "Contorne a área à mão livre; ao soltar ela é preenchida.",
    "poligono": "Clique nos vértices. Feche no 1º ponto, com Enter ou com o botão direito.",
    "curva": "Clique nos pontos da curva suave. Feche com Enter ou com o botão direito.",
    "retangulo": "Arraste para desenhar o retângulo.",
    "elipse": "Arraste para desenhar a elipse.",
    "estrela": "Arraste do centro até uma das pontas.",
    "balde": "Clique numa área fechada para preenchê-la.",
    "mover": "Arraste para mover o desenho inteiro.",
    "mao": "Arraste para mover a vista. O botão direito também move a vista em qualquer ferramenta.",
}
SEM_MODO = {"borracha", "mover", "mao"}
POR_CLIQUES = {"poligono", "curva"}
SIMETRIAS = [("nenhuma", "Nenhuma", ft.Icons.BLOCK), ("vertical", "Vertical", ft.Icons.SWAP_HORIZ),
             ("horizontal", "Horizontal", ft.Icons.SWAP_VERT), ("ambas", "Ambas", ft.Icons.OPEN_WITH),
             ("radial", "Radial", ft.Icons.FILTER_VINTAGE)]


def _nome_seguro(texto):
    return re.sub(r"[^A-Za-z0-9_]+", "_", texto or "").strip("_")


def _atualizar(*controles):
    """update() parcial; ignora controles ainda fora da pagina."""
    for controle in controles:
        try:
            controle.update()
        except (RuntimeError, AssertionError):
            pass


def _caber(imagem, tamanho):
    """Imagem RGBA centralizada (contain) num quadro transparente do tamanho do documento."""
    imagem = imagem.convert("RGBA")
    fator = min(tamanho[0] / imagem.width, tamanho[1] / imagem.height)
    imagem = imagem.resize((max(1, round(imagem.width * fator)), max(1, round(imagem.height * fator))),
                           Image.Resampling.LANCZOS)
    quadro = Image.new("RGBA", tamanho, (0, 0, 0, 0))
    quadro.paste(imagem, ((tamanho[0] - imagem.width) // 2, (tamanho[1] - imagem.height) // 2))
    return quadro


class Documento:
    def __init__(self, tipo):
        self.tipo = tipo
        tamanho = desenho.TAMANHO_ICONE if tipo == ICONE else desenho.TAMANHO_BANNER
        self.desenho = desenho.Desenho(tamanho)
        self.vista = desenho.Vista((LADO_TELA, LADO_TELA), tamanho)
        self.nome = ""
        self.referencia = None
        self.opacidade_referencia = 0.4
        self.mostrar_referencia = True


class EditorSilhuetas:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.documentos = {ICONE: Documento(ICONE), BANNER: Documento(BANNER)}
        self.tipo = ICONE
        self.ferramenta = "pincel"
        self.recortar = False
        self.pontos = []          # traco, laco ou vertices do poligono/curva (documento)
        self.inicio = None        # ancora do arrasto (documento)
        self.fim = None
        self.cursor = None        # posicao do mouse (tela)
        self._arrastando = False
        self._pan_vista = None
        self._digitando = False
        self._guias_banner = {}
        self._pedido = 0
        self._tarefa = None
        self.root = None

    # ---------- estado ----------
    @property
    def doc(self):
        return self.documentos[self.tipo]

    @property
    def desenho(self):
        return self.doc.desenho

    @property
    def vista(self):
        return self.doc.vista

    @property
    def temporarias(self):
        return bool(self.pontos or self.inicio)

    def _copias(self):
        return desenho.simetrias(self.simetria, self.raios_slider.value, self.desenho.tamanho)

    @property
    def simetria(self):
        return (self.symmetry_button.selected or ["nenhuma"])[0]

    @property
    def raio_pincel(self):
        return self.size_slider.value / 2

    def _apagar(self):
        return self.ferramenta == "borracha" or (self.recortar and self.ferramenta not in SEM_MODO)

    # ---------- interface ----------
    def build(self):
        self.tool_buttons = {}
        for nome, (rotulo, icone, tecla) in FERRAMENTAS.items():
            self.tool_buttons[nome] = ft.IconButton(
                icon=icone, tooltip=f"{rotulo} ({tecla})", icon_size=20, icon_color=MUTED, width=38, height=36,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=9), padding=ft.Padding.all(4)),
                on_click=lambda _, nome=nome: self._escolher_ferramenta(nome),
            )
        grupos = [["pincel", "borracha"], ["linha", "laco", "poligono", "curva"],
                  ["retangulo", "elipse", "estrela"], ["balde", "mover", "mao"]]
        barra = []
        for grupo in grupos:
            if barra:
                barra.append(ft.Divider(height=6, color=OUTLINE))
            barra += [self.tool_buttons[nome] for nome in grupo]
        self.undo_button = ft.IconButton(ft.Icons.UNDO, icon_size=18, tooltip="Desfazer (Ctrl+Z)",
                                         on_click=self._desfazer)
        self.redo_button = ft.IconButton(ft.Icons.REDO, icon_size=18, tooltip="Refazer (Ctrl+Y)",
                                         on_click=self._refazer)
        toolbar = ft.Container(
            content=ft.Column(barra, spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                              scroll=ft.ScrollMode.AUTO),
            bgcolor=SURFACE_HIGH, border_radius=12, padding=ft.Padding.symmetric(vertical=6), width=50,
        )

        self.imagem = ft.Image(src=PIXEL_TRANSPARENTE, width=LADO_TELA, height=LADO_TELA, fit=ft.BoxFit.FILL,
                               gapless_playback=True)
        self.canvas = cv.Canvas(shapes=[], width=LADO_TELA, height=LADO_TELA)
        self.detector = ft.GestureDetector(
            content=ft.Stack([self.imagem, self.canvas]),
            mouse_cursor=ft.MouseCursor.PRECISE,
            drag_interval=16, hover_interval=30,
            on_pan_start=self._inicio, on_pan_update=self._arrasto, on_pan_end=self._fim,
            on_tap_up=self._clique, on_secondary_tap=self._clique_direito,
            on_right_pan_start=self._vista_inicio, on_right_pan_update=self._vista_arrasto,
            on_right_pan_end=self._vista_fim,
            on_scroll=self._rolagem, on_hover=self._pairar, on_exit=self._sair,
        )
        self.zoom_text = ft.Text("100%", size=12, color=TEXT, width=48, text_align=ft.TextAlign.CENTER)
        self.coords_text = ft.Text("", size=11, color=MUTED)
        self.progress = ft.ProgressBar(visible=False, color=ACCENT)
        barra_zoom = ft.Container(
            content=ft.Row([
                ft.IconButton(ft.Icons.ZOOM_OUT, icon_size=18, tooltip="Afastar (-)",
                              on_click=lambda _: self._zoom(1 / 1.25)),
                self.zoom_text,
                ft.IconButton(ft.Icons.ZOOM_IN, icon_size=18, tooltip="Aproximar (+)",
                              on_click=lambda _: self._zoom(1.25)),
                ft.IconButton(ft.Icons.FIT_SCREEN, icon_size=18, tooltip="Ajustar à tela (0)",
                              on_click=lambda _: self._ajustar_vista()),
            ], spacing=0, tight=True),
            bgcolor="#CC1A2530", border_radius=10, right=8, bottom=8,
        )
        barra_historico = ft.Container(
            content=ft.Row([self.undo_button, self.redo_button], spacing=0, tight=True),
            bgcolor="#CC1A2530", border_radius=10, left=8, top=8,
        )
        self.area = area = ft.Container(
            content=ft.Stack([
                self.detector, barra_zoom, barra_historico,
                ft.Container(content=self.coords_text, left=10, bottom=14),
                ft.Container(content=self.progress, left=0, right=0, top=0),
            ]),
            border=ft.Border.all(1, OUTLINE), border_radius=12, clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        self.tool_name = ft.Text("", size=14, weight=ft.FontWeight.W_600)
        self.tool_hint = ft.Text("", size=12, color=MUTED)
        self.centro = centro = ft.Column([area, ft.Column([self.tool_name, self.tool_hint], spacing=2)],
                           spacing=8)

        self.paineis = [self._painel_documento(), self._painel_ferramenta(), self._painel_simetria(),
                        self._painel_transformar(), self._painel_operacoes(), self._painel_referencia()]
        paineis = ft.Column(self.paineis, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
        self.root = ft.Container(
            padding=20, expand=True,
            content=ft.Column(expand=True, spacing=14, controls=[
                heading("Editor de silhuetas",
                        "Desenhe a silhueta do ícone de vocação ou o padrão bordado do banner."),
                ft.Row([toolbar, centro, paineis], expand=True, spacing=ESPACO,
                       vertical_alignment=ft.CrossAxisAlignment.START),
            ]),
        )
        self.page.on_keyboard_event = self._teclado
        self.redimensionar(renderizar=False)
        self._escolher_ferramenta(self.ferramenta, atualizar=False)
        self._sincronizar_documento()
        self._render()
        return self.root

    def _espaco_disponivel(self):
        conteudo = self.app.scaled_content
        altura = conteudo.height or self.page.height or 920
        largura = (conteudo.width or self.page.width or 1440) - LARGURA_FIXA
        lado = int(max(MIN_TELA, min(MAX_TELA, altura - 250, largura - MIN_PAINEIS)))
        return lado, max(MIN_PAINEIS, largura - lado)

    def redimensionar(self, renderizar=True):
        """A area de desenho acompanha a janela; cada vista mantem o centro e o zoom relativo."""
        lado, largura_paineis = self._espaco_disponivel()
        for painel in self.paineis:
            painel.width = largura_paineis
        if lado == getattr(self, "lado", None):
            return
        self.lado = lado
        for doc in self.documentos.values():
            vista = doc.vista
            centro = vista.para_doc((vista.tela[0] / 2, vista.tela[1] / 2))
            relativo = vista.zoom / vista.zoom_ajuste
            vista.tela = (lado, lado)
            vista.zoom = vista.zoom_ajuste * relativo
            vista.origem = (centro[0] - lado / (2 * vista.zoom), centro[1] - lado / (2 * vista.zoom))
        for controle in (self.imagem, self.canvas, self.area):
            controle.width = controle.height = lado
        self.centro.width = lado
        self._descartar()
        if renderizar:
            self._render()

    @staticmethod
    def _titulo(texto):
        return ft.Text(texto, size=15, weight=ft.FontWeight.W_600)

    def _campo(self, **opcoes):
        return ft.TextField(dense=True, on_focus=self._focar, on_blur=self._desfocar, **opcoes)

    async def _focar(self, _):
        self._digitando = True

    async def _desfocar(self, _):
        self._digitando = False

    def _painel_documento(self):
        self.type_button = ft.SegmentedButton(
            segments=[ft.Segment(value=ICONE, icon=ft.Icon(ft.Icons.SHIELD_OUTLINED), label=ft.Text("Ícone de vocação")),
                      ft.Segment(value=BANNER, icon=ft.Icon(ft.Icons.FLAG_OUTLINED), label=ft.Text("Padrão do banner"))],
            selected=[ICONE], allow_empty_selection=False, show_selected_icon=False, on_change=self._trocar_tipo,
        )
        self.name_field = self._campo(label="Nome", expand=True, on_change=self._mudar_nome)
        self.library_dropdown = ft.Dropdown(label="Biblioteca", dense=True, expand=True, options=[])
        self.size_info = ft.Text("", size=12, color=MUTED)
        self.done_button = ft.FilledButton("Concluir", icon=ft.Icons.CHECK, on_click=self.concluir)
        return surface(ft.Column(spacing=10, controls=[
            self._titulo("Documento"),
            self.type_button,
            self.size_info,
            ft.Row([self.name_field]),
            ft.Row([self.library_dropdown,
                    ft.IconButton(ft.Icons.EDIT_OUTLINED, tooltip="Editar o item da biblioteca",
                                  on_click=self._abrir_da_biblioteca)]),
            ft.Row(wrap=True, spacing=8, controls=[
                ft.OutlinedButton("Novo", icon=ft.Icons.NOTE_ADD_OUTLINED, on_click=self._novo),
                ft.OutlinedButton("Abrir imagem", icon=ft.Icons.IMAGE_OUTLINED, on_click=self._abrir_imagem),
                ft.OutlinedButton("Limpar", icon=ft.Icons.DELETE_SWEEP_OUTLINED, on_click=self._limpar),
                self.done_button,
            ]),
        ]))

    def _painel_ferramenta(self):
        self.mode_button = ft.SegmentedButton(
            segments=[ft.Segment(value="adicionar", icon=ft.Icon(ft.Icons.ADD), label=ft.Text("Adicionar")),
                      ft.Segment(value="recortar", icon=ft.Icon(ft.Icons.REMOVE), label=ft.Text("Recortar"))],
            selected=["adicionar"], allow_empty_selection=False, show_selected_icon=False,
            on_change=self._trocar_modo, tooltip="Alternar com X",
        )
        self.size_slider = ft.Slider(min=1, max=200, divisions=199, value=24, label="{value} px", expand=True,
                                     on_change=self._opcao_mudou)
        self.smooth_switch = ft.Switch(label="Suavizar traço", value=True)
        self.snap_switch = ft.Switch(label="Travar ângulo (15°)", value=False)
        self.radius_slider = ft.Slider(min=0, max=120, divisions=120, value=0, label="{value} px", expand=True)
        self.square_switch = ft.Switch(label="Proporção 1:1", value=False)
        self.center_switch = ft.Switch(label="A partir do centro", value=False)
        self.points_slider = ft.Slider(min=3, max=16, divisions=13, value=5, label="{value}", expand=True)
        self.inner_slider = ft.Slider(min=0.15, max=1.0, divisions=17, value=0.45, label="{value}", expand=True)
        self.close_button = ft.FilledButton("Fechar", icon=ft.Icons.CHECK, on_click=self._fechar)
        self.back_button = ft.OutlinedButton("Remover ponto", icon=ft.Icons.BACKSPACE_OUTLINED,
                                             on_click=self._remover_ponto)
        self.cancel_button = ft.OutlinedButton("Cancelar", icon=ft.Icons.CLOSE, on_click=self._cancelar)

        def linha(rotulo, controle):
            return ft.Row([ft.Text(rotulo, size=12, color=MUTED, width=96), controle], spacing=4)

        self.opcoes = {
            "modo": self.mode_button,
            "tamanho": linha("Tamanho", self.size_slider),
            "suavizar": self.smooth_switch,
            "travar": self.snap_switch,
            "cantos": linha("Raio dos cantos", self.radius_slider),
            "quadrado": self.square_switch,
            "centro": self.center_switch,
            "pontas": linha("Pontas", self.points_slider),
            "interno": linha("Raio interno", self.inner_slider),
            "pontos": ft.Row([self.close_button, self.back_button, self.cancel_button], wrap=True, spacing=8),
        }
        return surface(ft.Column([self._titulo("Opções da ferramenta"), *self.opcoes.values()], spacing=8))

    def _painel_simetria(self):
        self.symmetry_button = ft.SegmentedButton(
            segments=[ft.Segment(value=valor, icon=ft.Icon(icone), tooltip=rotulo) for valor, rotulo, icone in SIMETRIAS],
            selected=["nenhuma"], allow_empty_selection=False, show_selected_icon=False,
            on_change=self._opcao_mudou,
        )
        self.symmetry_label = ft.Text("Nenhuma", size=12, color=MUTED)
        self.raios_slider = ft.Slider(min=2, max=16, divisions=14, value=6, label="{value}", expand=True,
                                      on_change=self._opcao_mudou)
        self.raios_row = ft.Row([ft.Text("Repetições", size=12, color=MUTED, width=96), self.raios_slider],
                                visible=False)
        return surface(ft.Column(spacing=8, controls=[
            ft.Row([self._titulo("Simetria"), self.symmetry_label]),
            self.symmetry_button, self.raios_row,
        ]))

    def _painel_transformar(self):
        def botao(icone, dica, funcao):
            return ft.IconButton(icone, tooltip=dica, on_click=lambda _: self._operar(funcao))

        d = lambda: self.desenho  # noqa: E731 - o documento muda ao trocar o tipo
        return surface(ft.Column(spacing=4, controls=[
            self._titulo("Transformar"),
            ft.Row(wrap=True, spacing=0, controls=[
                botao(ft.Icons.SWAP_HORIZ, "Espelhar na horizontal", lambda: d().espelhar(True)),
                botao(ft.Icons.SWAP_VERT, "Espelhar na vertical", lambda: d().espelhar(False)),
                botao(ft.Icons.ROTATE_LEFT, "Girar 15° anti-horário", lambda: d().girar(-15)),
                botao(ft.Icons.ROTATE_RIGHT, "Girar 15° horário", lambda: d().girar(15)),
                botao(ft.Icons.ROTATE_90_DEGREES_CW_OUTLINED, "Girar 90°", lambda: d().girar(90)),
                botao(ft.Icons.CLOSE_FULLSCREEN, "Diminuir 10%", lambda: d().escalar(1 / 1.1)),
                botao(ft.Icons.OPEN_IN_FULL, "Aumentar 10%", lambda: d().escalar(1.1)),
                botao(ft.Icons.CENTER_FOCUS_STRONG, "Centralizar", lambda: d().centralizar(self._centro())),
                botao(ft.Icons.FIT_SCREEN, "Ajustar ao documento", lambda: d().ajustar(self._ocupacao(), self._centro())),
            ]),
        ]))

    def _painel_operacoes(self):
        self.ops_slider = ft.Slider(min=1, max=40, divisions=39, value=4, label="{value} px", expand=True)

        def botao(rotulo, icone, funcao):
            return ft.OutlinedButton(rotulo, icon=icone, on_click=lambda _: self._operar(funcao))

        px = lambda: self.ops_slider.value  # noqa: E731
        return surface(ft.Column(spacing=8, controls=[
            self._titulo("Operações"),
            ft.Row([ft.Text("Intensidade", size=12, color=MUTED, width=96), self.ops_slider]),
            ft.Row(wrap=True, spacing=8, run_spacing=8, controls=[
                botao("Engrossar", ft.Icons.LINE_WEIGHT, lambda: self.desenho.engrossar(px())),
                botao("Afinar", ft.Icons.REMOVE_CIRCLE_OUTLINE, lambda: self.desenho.afinar(px())),
                botao("Contorno", ft.Icons.CIRCLE_OUTLINED, lambda: self.desenho.contorno(px())),
                botao("Suavizar bordas", ft.Icons.BLUR_ON, lambda: self.desenho.suavizar_bordas(px())),
                botao("Tapar furos", ft.Icons.FORMAT_COLOR_FILL, lambda: self.desenho.tapar_furos()),
                botao("Inverter", ft.Icons.INVERT_COLORS, lambda: self.desenho.inverter()),
            ]),
        ]))

    def _painel_referencia(self):
        self.ref_slider = ft.Slider(min=0.05, max=1, divisions=19, value=0.4, label="{value}", expand=True,
                                    on_change=self._mudar_referencia)
        self.ref_switch = ft.Switch(label="Mostrar", value=True, on_change=self._mudar_referencia)
        self.ref_status = ft.Text("Nenhuma imagem", size=12, color=MUTED)
        self.guide_switch = ft.Switch(label="Mostrar o banner por baixo", value=True, on_change=self._mudar_referencia)
        return surface(ft.Column(spacing=8, controls=[
            self._titulo("Referência"),
            ft.Row([ft.OutlinedButton("Abrir referência", icon=ft.Icons.IMAGE_SEARCH, on_click=self._abrir_referencia),
                    ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remover referência",
                                  on_click=self._remover_referencia),
                    self.ref_status], wrap=True),
            ft.Row([ft.Text("Opacidade", size=12, color=MUTED, width=96), self.ref_slider]),
            self.ref_switch,
            self.guide_switch,
        ]))

    # ---------- sincronizacao ----------
    def _sincronizar_documento(self):
        doc = self.doc
        self.type_button.selected = [self.tipo]
        self.name_field.value = doc.nome
        largura, altura = doc.desenho.tamanho
        self.size_info.value = (f"Silhueta das armas do brasão · {largura}×{altura} px" if self.tipo == ICONE else
                                f"Bordado do banner, na posição exata · {largura}×{altura} px")
        self.done_button.content = "Importar no gerador" if self.tipo == ICONE else "Salvar e aplicar no banner"
        self.ref_slider.value = doc.opacidade_referencia
        self.ref_switch.value = doc.mostrar_referencia
        self.ref_status.value = "Imagem carregada" if doc.referencia is not None else "Nenhuma imagem"
        self.guide_switch.visible = self.tipo == BANNER
        self._atualizar_biblioteca()
        self._atualizar_estado()

    def _atualizar_biblioteca(self):
        nomes = icon_gen.armas() if self.tipo == ICONE else padroes_banner.listar()
        self.library_dropdown.options = [ft.DropdownOption(key=nome, text=nome) for nome in nomes]
        if self.library_dropdown.value not in nomes:
            self.library_dropdown.value = None

    def _atualizar_estado(self):
        self.undo_button.disabled = not self.desenho.pode_desfazer
        self.redo_button.disabled = not self.desenho.pode_refazer
        self.zoom_text.value = f"{round(self.vista.zoom / self.vista.zoom_ajuste * 100)}%"
        espera = len(self.pontos) if self.ferramenta in POR_CLIQUES else 0
        self.close_button.disabled = espera < 3
        self.back_button.disabled = self.cancel_button.disabled = espera == 0
        rotulo = next(r for v, r, _ in SIMETRIAS if v == self.simetria)
        self.symmetry_label.value = rotulo + (f" · {int(self.raios_slider.value)}" if self.simetria == "radial" else "")
        self.raios_row.visible = self.simetria == "radial"

    def _escolher_ferramenta(self, nome, atualizar=True):
        self._descartar()
        self.ferramenta = nome
        for chave, botao in self.tool_buttons.items():
            botao.bgcolor = ACCENT if chave == nome else None
            botao.icon_color = BACKGROUND if chave == nome else MUTED
        rotulo, _, tecla = FERRAMENTAS[nome]
        self.tool_name.value = f"{rotulo} ({tecla})"
        self.tool_hint.value = DICAS[nome]
        visiveis = {
            "modo": nome not in SEM_MODO,
            "tamanho": nome in ("pincel", "borracha", "linha"),
            "suavizar": nome in ("pincel", "borracha", "laco"),
            "travar": nome in ("linha", "poligono"),
            "cantos": nome == "retangulo",
            "quadrado": nome in ("retangulo", "elipse"),
            "centro": nome in ("retangulo", "elipse"),
            "pontas": nome == "estrela",
            "interno": nome == "estrela",
            "pontos": nome in POR_CLIQUES,
        }
        for chave, controle in self.opcoes.items():
            controle.visible = visiveis[chave]
        self.detector.mouse_cursor = ft.MouseCursor.GRAB if nome == "mao" else (
            ft.MouseCursor.MOVE if nome == "mover" else ft.MouseCursor.PRECISE)
        self._atualizar_estado()
        self._desenhar_sobreposicao()
        if atualizar:
            self.page.update()

    async def _trocar_tipo(self, event):
        self._descartar()
        self.tipo = (event.control.selected or [ICONE])[0]
        self._sincronizar_documento()
        self._render()
        self.page.update()

    async def _mudar_nome(self, event):
        self.doc.nome = event.control.value

    async def _trocar_modo(self, event):
        self.recortar = (event.control.selected or ["adicionar"])[0] == "recortar"
        self._desenhar_sobreposicao()

    def _alternar_modo(self):
        self.recortar = not self.recortar
        self.mode_button.selected = ["recortar" if self.recortar else "adicionar"]

    async def _opcao_mudou(self, _):
        self._atualizar_estado()
        self._desenhar_sobreposicao()
        self.page.update()

    async def _mudar_referencia(self, _):
        self.doc.opacidade_referencia = self.ref_slider.value
        self.doc.mostrar_referencia = self.ref_switch.value
        self._render()

    def _centro(self):
        return banner_gen.CENTRO if self.tipo == BANNER else None

    def _ocupacao(self):
        return 0.6 if self.tipo == BANNER else 0.85

    # ---------- render ----------
    def _guia_banner(self):
        estilo = "simples"
        if self.app.generator is not None:
            estilo = BANNER_POR_MOLDURA.get(self.app.generator.moldura, "simples")
        if estilo not in self._guias_banner:
            self._guias_banner[estilo] = banner_gen.render(cor_a=COR_GUIA, estilo=estilo).convert("RGBA")
        return self._guias_banner[estilo]

    def _compor(self):
        doc = self.doc
        camadas = []
        if doc.tipo == BANNER and self.guide_switch.value:
            camadas.append((self._guia_banner(), 0.55))
        if doc.referencia is not None and doc.mostrar_referencia:
            camadas.append((doc.referencia, doc.opacidade_referencia))
        alfa = 0.9 if camadas else 1.0
        return image_data(desenho.compor_vista(doc.desenho, doc.vista, COR_FORA, COR_FUNDO, COR_TINTA, alfa, camadas))

    def _render(self):
        """Pede um render; pedidos feitos durante um render viram um unico render seguinte."""
        self._pedido += 1
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.imagem.src = self._compor()
            return
        if self._tarefa is None or self._tarefa.done():
            self._tarefa = asyncio.create_task(self._laco_render())

    async def _laco_render(self):
        while True:
            pedido = self._pedido
            src = await asyncio.to_thread(self._compor)
            self.imagem.src = src
            self._atualizar_estado()
            self._desenhar_sobreposicao(enviar=False)
            self.page.update()
            if pedido == self._pedido:
                return

    def _apos_mudanca(self):
        self._atualizar_estado()
        self._render()

    # ---------- sobreposicao (formas temporarias em coordenadas da tela) ----------
    def _tela(self, pontos):
        return [self.vista.para_tela(p) for p in pontos]

    @staticmethod
    def _caminho(pontos, paint, fechado=True):
        if len(pontos) < 2:
            return None
        elementos = [cv.Path.MoveTo(*pontos[0])] + [cv.Path.LineTo(x, y) for x, y in pontos[1:]]
        if fechado:
            elementos.append(cv.Path.Close())
        return cv.Path(elementos, paint=paint)

    def _forma_atual(self):
        """Poligono (documento) da forma em construcao, ou None."""
        f = self.ferramenta
        if f in ("retangulo", "elipse") and self.inicio and self.fim:
            x0, y0, x1, y1 = desenho.caixa(self.inicio, self.fim, self.square_switch.value, self.center_switch.value)
            if f == "retangulo":
                return desenho.retangulo(x0, y0, x1, y1, self.radius_slider.value)
            return desenho.elipse(x0, y0, x1, y1)
        if f == "estrela" and self.inicio and self.fim:
            return desenho.estrela(self.inicio, self.fim, int(self.points_slider.value), self.inner_slider.value)
        if f == "laco" and len(self.pontos) > 2:
            return desenho.suavizar(self.pontos, 2, fechada=True) if self.smooth_switch.value else self.pontos
        return None

    def _fim_linha(self):
        if self.snap_switch.value and self.inicio and self.fim:
            return desenho.travar_angulo(self.inicio, self.fim)
        return self.fim

    def _desenhar_sobreposicao(self, enviar=True):
        if not hasattr(self, "canvas"):
            return
        formas = []
        largura, altura = self.desenho.tamanho
        guia = ft.Paint(color="#88A8C5D6", stroke_width=1, style=ft.PaintingStyle.STROKE, stroke_dash_pattern=[6, 5])
        cx, cy = largura / 2, altura / 2
        modo = self.simetria
        if modo in ("vertical", "ambas"):
            (x0, y0), (x1, y1) = self._tela([(cx, 0), (cx, altura)])
            formas.append(cv.Line(x0, y0, x1, y1, paint=guia))
        if modo in ("horizontal", "ambas"):
            (x0, y0), (x1, y1) = self._tela([(0, cy), (largura, cy)])
            formas.append(cv.Line(x0, y0, x1, y1, paint=guia))
        if modo == "radial":
            n = int(self.raios_slider.value)
            alcance = math.hypot(largura, altura)
            for k in range(n):
                angulo = -math.pi / 2 + 2 * math.pi * k / n
                (x0, y0), (x1, y1) = self._tela([(cx, cy), (cx + alcance * math.cos(angulo),
                                                            cy + alcance * math.sin(angulo))])
                formas.append(cv.Line(x0, y0, x1, y1, paint=guia))

        cor = COR_RECORTAR if self._apagar() else COR_ADICIONAR
        cheio = ft.Paint(color="#55" + cor[1:], style=ft.PaintingStyle.FILL)
        borda = ft.Paint(color=cor, stroke_width=1.5, style=ft.PaintingStyle.STROKE)
        zoom = self.vista.zoom
        copias = self._copias()
        f = self.ferramenta
        if f in ("pincel", "borracha", "linha") and (self.pontos or self.inicio):
            traco = self.pontos if f != "linha" else [self.inicio, self._fim_linha() or self.inicio]
            paint = ft.Paint(color="#99" + cor[1:], stroke_width=max(1, 2 * self.raio_pincel * zoom),
                             stroke_cap=ft.StrokeCap.ROUND, stroke_join=ft.StrokeJoin.ROUND,
                             style=ft.PaintingStyle.STROKE)
            for copia in copias:
                pontos = self._tela([copia(p) for p in traco])
                if len(pontos) == 1:
                    pontos = pontos * 2
                formas.append(self._caminho(pontos, paint, fechado=False))
        elif f in POR_CLIQUES and self.pontos:
            vertices = list(self.pontos)
            if self.cursor is not None:
                vertices.append(self._proximo_vertice(self.vista.para_doc(self.cursor)))
            contorno = desenho.curva(vertices, fechada=True) if f == "curva" else vertices
            for copia in copias:
                pontos = self._tela([copia(p) for p in contorno])
                if len(pontos) > 2:
                    formas.append(self._caminho(pontos, cheio))
                formas.append(self._caminho(pontos, borda, fechado=False))
            for i, (x, y) in enumerate(self._tela(self.pontos)):
                formas.append(cv.Circle(x, y, 5 if i == 0 else 3.5, paint=ft.Paint(color=TEXT if i else cor)))
        elif f == "mover" and self.inicio and self.fim and self.desenho.caixa():
            x0, y0, x1, y1 = self.desenho.caixa()
            dx, dy = self.fim[0] - self.inicio[0], self.fim[1] - self.inicio[1]
            (a, b), (c, d) = self._tela([(x0 + dx, y0 + dy), (x1 + dx, y1 + dy)])
            formas.append(cv.Rect(a, b, c - a, d - b, paint=ft.Paint(
                color=ACCENT, stroke_width=1.5, style=ft.PaintingStyle.STROKE, stroke_dash_pattern=[6, 4])))
        else:
            poligono = self._forma_atual()
            if poligono:
                for copia in copias:
                    pontos = self._tela([copia(p) for p in poligono])
                    formas += [self._caminho(pontos, cheio), self._caminho(pontos, borda)]

        if self.cursor is not None and f in ("pincel", "borracha", "linha") and not self._arrastando:
            x, y = self.cursor
            formas.append(cv.Circle(x, y, max(2, self.raio_pincel * zoom),
                                    paint=ft.Paint(color=cor, stroke_width=1, style=ft.PaintingStyle.STROKE)))
        self.canvas.shapes = [forma for forma in formas if forma is not None]
        if enviar:
            _atualizar(self.canvas)

    # ---------- gestos ----------
    @staticmethod
    def _posicao(event):
        return event.local_position.x, event.local_position.y

    def _proximo_vertice(self, ponto):
        if self.snap_switch.value and self.ferramenta == "poligono" and self.pontos:
            return desenho.travar_angulo(self.pontos[-1], ponto)
        return ponto

    async def _inicio(self, event):
        tela = self._posicao(event)
        self.cursor = tela
        ponto = self.vista.para_doc(tela)
        f = self.ferramenta
        if f == "mao":
            self._pan_vista = tela
            return
        if f in POR_CLIQUES or f == "balde":
            await self._clique(event)
            return
        self._arrastando = True
        if f in ("pincel", "borracha", "laco"):
            self.pontos = [ponto]
        else:
            self.inicio = self.fim = ponto
        self._desenhar_sobreposicao()

    async def _arrasto(self, event):
        tela = self._posicao(event)
        self.cursor = tela
        f = self.ferramenta
        if f == "mao":
            if self._pan_vista is not None:
                self.vista.deslocar(tela[0] - self._pan_vista[0], tela[1] - self._pan_vista[1])
                self._pan_vista = tela
                self._render()
            return
        if not self._arrastando:
            return
        ponto = self.vista.para_doc(tela)
        if f in ("pincel", "borracha", "laco"):
            if not self.pontos or math.dist(self.pontos[-1], ponto) * self.vista.zoom >= 1.5:
                self.pontos.append(ponto)
        else:
            self.fim = ponto
        self._desenhar_sobreposicao()

    async def _fim(self, _):
        if self.ferramenta == "mao":
            self._pan_vista = None
            return
        if not self._arrastando:
            return
        self._arrastando = False
        f, apagar, copias = self.ferramenta, self._apagar(), self._copias()
        mudou = False
        if f in ("pincel", "borracha") and self.pontos:
            pontos = desenho.suavizar(self.pontos, 2) if self.smooth_switch.value else self.pontos
            mudou = self.desenho.traco(pontos, self.raio_pincel, apagar, copias)
        elif f == "linha" and self.inicio:
            mudou = self.desenho.traco([self.inicio, self._fim_linha()], self.raio_pincel, apagar, copias)
        elif f == "mover" and self.inicio and self.fim:
            dx, dy = self.fim[0] - self.inicio[0], self.fim[1] - self.inicio[1]
            if abs(dx) + abs(dy) > 0.25:
                self.desenho.mover(dx, dy)
                mudou = True
        else:
            poligono = self._forma_atual()
            if poligono:
                mudou = self.desenho.preencher(poligono, apagar, copias)
        self.pontos, self.inicio, self.fim = [], None, None
        self._desenhar_sobreposicao()
        if mudou:
            self._apos_mudanca()

    async def _clique(self, event):
        tela = self._posicao(event)
        ponto = self.vista.para_doc(tela)
        f = self.ferramenta
        if f == "balde":
            if self.desenho.balde(ponto, self._apagar(), self._copias()):
                self._apos_mudanca()
            return
        if f not in POR_CLIQUES:
            return
        if len(self.pontos) >= 3 and math.dist(tela, self.vista.para_tela(self.pontos[0])) <= RAIO_FECHAR:
            await self._fechar(None)
            return
        self.pontos.append(self._proximo_vertice(ponto))
        self._atualizar_estado()
        self._desenhar_sobreposicao()
        self.page.update()

    async def _clique_direito(self, _):
        if self.ferramenta in POR_CLIQUES and self.pontos:
            await self._fechar(None)

    async def _fechar(self, _):
        if self.ferramenta not in POR_CLIQUES or len(self.pontos) < 3:
            return
        contorno = desenho.curva(self.pontos, fechada=True) if self.ferramenta == "curva" else self.pontos
        self.pontos = []
        mudou = self.desenho.preencher(contorno, self._apagar(), self._copias())
        self._desenhar_sobreposicao()
        if mudou:
            self._apos_mudanca()
        self.page.update()

    async def _remover_ponto(self, _):
        if self.pontos:
            self.pontos.pop()
            self._atualizar_estado()
            self._desenhar_sobreposicao()
            self.page.update()

    def _descartar(self):
        self.pontos, self.inicio, self.fim = [], None, None
        self._arrastando = False

    async def _cancelar(self, _):
        self._descartar()
        self._atualizar_estado()
        self._desenhar_sobreposicao()
        self.page.update()

    async def _vista_inicio(self, event):
        self._pan_vista = self._posicao(event)

    async def _vista_arrasto(self, event):
        tela = self._posicao(event)
        if self._pan_vista is not None:
            self.vista.deslocar(tela[0] - self._pan_vista[0], tela[1] - self._pan_vista[1])
            self._render()
        self._pan_vista = tela

    async def _vista_fim(self, _):
        self._pan_vista = None

    async def _rolagem(self, event):
        dy = getattr(event.scroll_delta, "y", 0) or 0
        if dy:
            self._zoom(1 / 1.15 if dy > 0 else 1.15, self._posicao(event))

    async def _pairar(self, event):
        self.cursor = self._posicao(event)
        x, y = self.vista.para_doc(self.cursor)
        self.coords_text.value = f"{x:.0f}, {y:.0f}"
        self._desenhar_sobreposicao()
        _atualizar(self.coords_text)

    async def _sair(self, _):
        self.cursor = None
        self.coords_text.value = ""
        self._desenhar_sobreposicao()
        _atualizar(self.coords_text)

    # ---------- vista ----------
    def _zoom(self, fator, ancora=None):
        self.vista.ampliar(fator, ancora)
        self._atualizar_estado()
        self._render()

    def _ajustar_vista(self):
        self.vista.ajustar()
        self._atualizar_estado()
        self._render()

    # ---------- historico e operacoes ----------
    async def _desfazer(self, _):
        self._descartar()
        self.desenho.desfazer()
        self._apos_mudanca()

    async def _refazer(self, _):
        self._descartar()
        self.desenho.refazer()
        self._apos_mudanca()

    async def _limpar(self, _):
        self._descartar()
        self.desenho.limpar()
        self._apos_mudanca()

    async def _novo(self, _):
        self._descartar()
        self.desenho.limpar()
        self.doc.nome = ""
        self.doc.vista.ajustar()
        self._sincronizar_documento()
        self._render()
        self.page.update()

    def _operar(self, funcao):
        """Transformacoes e operacoes de forma rodam fora do laco da interface."""
        if self.desenho.vazio:
            show_message(self.page, "Desenhe algo antes.")
            return None
        return asyncio.create_task(self._operar_async(funcao))

    async def _operar_async(self, funcao):
        self._descartar()
        self.progress.visible = True
        self.page.update()
        try:
            await asyncio.to_thread(funcao)
        finally:
            self.progress.visible = False
        self._apos_mudanca()
        self.page.update()

    # ---------- arquivos ----------
    async def _escolher_imagem(self, titulo):
        resultado = await self.app.file_picker.pick_files(
            dialog_title=titulo, file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=EXTENSOES, allow_multiple=False,
        )
        if not resultado or not resultado[0].path:
            return None
        return resultado[0].path

    async def _abrir_imagem(self, _):
        caminho = await self._escolher_imagem("Abrir imagem como silhueta")
        if caminho:
            await self.abrir_arquivo(caminho)

    async def abrir_arquivo(self, caminho, manter_posicao=False):
        try:
            mascara = await asyncio.to_thread(silhuetas.carregar_mascara, caminho)
            await asyncio.to_thread(self.desenho.abrir, mascara, self._ocupacao(), self._centro(), manter_posicao)
        except (OSError, ValueError) as erro:
            show_error(self.page, "Abrir imagem", str(erro))
            return
        self._descartar()
        if not self.doc.nome:
            self.doc.nome = _nome_seguro(os.path.splitext(os.path.basename(caminho))[0])
            self.name_field.value = self.doc.nome
        self._apos_mudanca()
        self.page.update()

    async def _abrir_da_biblioteca(self, _):
        nome = self.library_dropdown.value
        if not nome:
            show_message(self.page, "Escolha um item da biblioteca.")
            return
        if self.tipo == ICONE:
            caminho, manter = silhuetas.caminho_da_silhueta(nome), False
        else:
            caminho, manter = padroes_banner.caminho(nome), True
        self.doc.nome = ""
        await self.abrir_arquivo(caminho, manter)

    async def _abrir_referencia(self, _):
        caminho = await self._escolher_imagem("Abrir imagem de referência")
        if not caminho:
            return
        try:
            with Image.open(caminho) as fonte:
                referencia = await asyncio.to_thread(_caber, fonte, self.desenho.tamanho)
        except OSError as erro:
            show_error(self.page, "Abrir referência", str(erro))
            return
        self.doc.referencia = referencia
        self.doc.mostrar_referencia = self.ref_switch.value = True
        self.ref_status.value = os.path.basename(caminho)
        self._render()

    async def _remover_referencia(self, _):
        self.doc.referencia = None
        self.ref_status.value = "Nenhuma imagem"
        self._render()

    # ---------- concluir ----------
    async def concluir(self, _):
        if self.desenho.vazio:
            show_message(self.page, "Desenhe a silhueta antes de concluir.")
            return
        nome = _nome_seguro(self.name_field.value)
        if self.tipo == ICONE:
            dialogo = DialogoImportacao(self.app.garantir_gerador(), self.desenho.resultado(),
                                        f"{nome or 'silhueta'}.png", ao_importar=self._importado)
            self.page.show_dialog(dialogo.build())
            return
        if not nome:
            show_message(self.page, "Dê um nome ao padrão do banner.", error=True)
            return
        if padroes_banner.existe(nome) and not await self.app._confirm(
                "Substituir padrão", f"Já existe um padrão '{nome}'. Substituir?"):
            return
        try:
            await asyncio.to_thread(padroes_banner.salvar, nome, self.desenho.resultado(recortar=False))
        except (OSError, ValueError) as erro:
            show_error(self.page, "Salvar padrão do banner", str(erro))
            return
        self.doc.nome = self.name_field.value = nome
        self._atualizar_biblioteca()
        gerador = self.app.garantir_gerador()
        gerador.atualizar_padroes_banner()
        await gerador.aplicar_padrao_banner_da_biblioteca(nome)
        show_message(self.page, f"Padrão '{nome}' salvo e aplicado no banner do brasão.")
        self.page.update()

    async def _importado(self, nome):
        self._atualizar_biblioteca()
        show_message(self.page, f"Silhueta '{nome}' adicionada ao gerador.")
        self.page.update()

    # ---------- teclado ----------
    async def _teclado(self, event):
        if self.app.secao != self.app.SECAO_EDITOR or self._digitando or self.root is None:
            return
        tecla = (event.key or "")
        maiuscula = tecla.upper()
        if event.ctrl:
            if maiuscula == "Z":
                await (self._refazer(None) if event.shift else self._desfazer(None))
            elif maiuscula == "Y":
                await self._refazer(None)
            return
        if event.alt or event.meta:
            return
        for nome, (_, _, atalho) in FERRAMENTAS.items():
            if maiuscula == atalho:
                self._escolher_ferramenta(nome)
                return
        if maiuscula == "X":
            self._alternar_modo()
            self._desenhar_sobreposicao()
            self.page.update()
        elif tecla in ("[", "Bracket Left"):
            self.size_slider.value = max(1, round(self.size_slider.value / 1.2))
            await self._opcao_mudou(None)
        elif tecla in ("]", "Bracket Right"):
            self.size_slider.value = min(200, round(self.size_slider.value * 1.2) + 1)
            await self._opcao_mudou(None)
        elif tecla in ("Enter", "Numpad Enter"):
            await self._fechar(None)
        elif tecla == "Escape":
            await self._cancelar(None)
        elif tecla == "Backspace":
            await self._remover_ponto(None)
        elif tecla in ("+", "=", "Numpad Add", "Equal"):
            self._zoom(1.25)
        elif tecla in ("-", "Numpad Subtract", "Minus"):
            self._zoom(1 / 1.25)
        elif tecla in ("0", "Digit 0", "Numpad 0"):
            self._ajustar_vista()
