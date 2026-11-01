"""Headless smoke test for the Flet desktop screen tree and preview renderer."""
import asyncio
import base64
import inspect
import io
import os
import sys
import tempfile
from unittest.mock import patch

import flet as ft
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
from ddiconstudio import app_paths  # noqa: E402
from ddiconstudio import banner_gen, chanfro, glyph_gen, silhuetas  # noqa: E402
from ddiconstudio import icon_gen, padroes_banner  # noqa: E402
from ddiconstudio.gui.icon_gen_gui import DialogoImportacao  # noqa: E402
from ddiconstudio.gui.main_window import App  # noqa: E402
from ddiconstudio.gui.theme import PIXEL_TRANSPARENTE  # noqa: E402


class FakeWindow:
    def __init__(self):
        self.width = 0
        self.height = 0
        self.min_width = 0
        self.min_height = 0
        self.prevent_close = False
        self.closed = False
        self.on_event = None

    async def center(self):
        pass

    async def close(self):
        self.closed = True


class FakePage:
    def __init__(self):
        self.services = []
        self.window = FakeWindow()
        self.controls = []
        self.tasks = []
        self.dialogs = []

    def add(self, *controls):
        self.controls.extend(controls)

    def update(self, *_):
        pass

    def show_dialog(self, dialog):
        self.dialogs.append(dialog)

    def pop_dialog(self):
        self.dialogs.pop()

    def run_task(self, handler, *args):
        assert inspect.iscoroutinefunction(handler), handler
        self.tasks.append((handler, args))


def assert_handlers_not_dropped(root):
    for control in walk_controls(root):
        for name in ("on_click", "on_change", "on_select"):
            handler = getattr(control, name, None)
            if handler is None or inspect.iscoroutinefunction(handler):
                continue
            event = type("Event", (), {"control": control})()
            try:
                result = handler(event)
            except TypeError:
                result = handler()
            assert not inspect.iscoroutine(result), f"{type(control).__name__}.{name} descarta corrotina"


def walk_controls(control):
    yield control
    for child in getattr(control, "controls", []):
        yield from walk_controls(child)
    content = getattr(control, "content", None)
    if content is not None:
        yield from walk_controls(content)


async def smoke():
    banner_pattern = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(banner_pattern).polygon(
        [(32, 4), (40, 25), (60, 32), (40, 39), (32, 60), (24, 39), (4, 32), (24, 25)],
        fill=(190, 160, 95, 235),
    )
    banner_base = banner_gen.render(cor_a=banner_gen.PALETA["vermelho"], estilo="simples")
    banner_with_pattern = banner_gen.render(
        cor_a=banner_gen.PALETA["vermelho"],
        estilo="simples",
        emblema=banner_pattern,
        dx=-30,
        dy=20,
        contorno_escala=1.4,
        contorno_dx=70,
        contorno_dy=50,
    )
    banner_moved_pattern = banner_gen.render(
        cor_a=banner_gen.PALETA["vermelho"], estilo="simples", emblema=banner_pattern,
        dx=40, dy=20, contorno_escala=1.4, contorno_dx=70, contorno_dy=50,
    )
    banner_moved_contour = banner_gen.render(
        cor_a=banner_gen.PALETA["vermelho"], estilo="simples", emblema=banner_pattern,
        dx=-30, dy=20, contorno_escala=1.4, contorno_dx=-70, contorno_dy=50,
    )
    assert banner_base.size == (banner_gen.LARGURA, banner_gen.ALTURA)
    assert not np.array_equal(np.asarray(banner_base), np.asarray(banner_with_pattern))
    assert not np.array_equal(np.asarray(banner_with_pattern), np.asarray(banner_moved_pattern))
    assert not np.array_equal(np.asarray(banner_with_pattern), np.asarray(banner_moved_contour))
    ring_pattern = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    ImageDraw.Draw(ring_pattern).ellipse((4, 4, 44, 44), outline=(170, 140, 80, 220), width=4)
    banner_ring = banner_gen.render(
        cor_a=banner_gen.PALETA["vermelho"], estilo="simples", emblema=ring_pattern,
    )
    assert banner_ring.getpixel(banner_gen.CENTRO) == banner_base.getpixel(banner_gen.CENTRO)

    crown_base = banner_gen.render(cor_a=banner_gen.PALETA["vermelho"], estilo="coroa")
    crown_arr = np.asarray(crown_base).astype(int)
    wreath = (crown_arr[..., 1] > 70) & (crown_arr[..., 2] < crown_arr[..., 1] * 0.7)
    wreath[:300] = wreath[560:] = False
    wreath[:, :130] = wreath[:, 380:] = False
    wy, wx = np.nonzero(wreath)
    assert len(wy), "fixture sem louros"
    py, px = int(wy[0]), int(wx[0])
    bar = Image.new("RGBA", (8, 8), (255, 255, 255, 255))
    crown_bar = banner_gen.render(
        cor_a=banner_gen.PALETA["vermelho"], estilo="coroa", emblema=bar,
        dx=px + 6 - banner_gen.CENTRO[0], dy=py - banner_gen.CENTRO[1],
    )
    covered = np.asarray(crown_bar).astype(int)[py - 2:py + 3, px - 1:px + 1, :3].reshape(-1, 3).mean(axis=0)
    assert covered[1] < 50 and covered[0] > covered[1], f"louro nao foi coberto pelo contorno: {covered}"
    sil_pixels = np.asarray(crown_bar).astype(int)[py - 3:py + 4, px + 4:px + 9, :3]
    assert sil_pixels.reshape(-1, 3).std(axis=0).max() > 3, "silhueta sem textura de fio"
    far = crown_arr[py + 40, px - 40]
    assert np.array_equal(np.asarray(crown_bar).astype(int)[py + 40, px - 40], far)

    with tempfile.TemporaryDirectory() as silhouette_dir:
        silhouette_path = os.path.join(silhouette_dir, "multi.png")
        silhouette_sheet = Image.new("L", (260, 160), 0)
        silhouette_draw = ImageDraw.Draw(silhouette_sheet)
        silhouette_draw.rectangle((10, 10, 24, 120), fill=255)
        silhouette_draw.polygon([(150, 15), (220, 15), (185, 68), (220, 122), (150, 122), (185, 68)], fill=255)
        silhouette_sheet.save(silhouette_path)
        loaded = silhuetas.carregar_silhueta(silhouette_path)
    assert loaded.size == (211, 113), loaded.size

    placeholder = Image.open(io.BytesIO(base64.b64decode(PIXEL_TRANSPARENTE))).convert("RGBA")
    assert placeholder.getpixel((0, 0))[3] == 0
    visible_sizes = []
    for index, bounds in enumerate(((31, 21, 170, 182), (13, 7, 187, 183))):
        badge = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        ImageDraw.Draw(badge).rectangle(bounds, fill=(90 + index, 30, 50, 255))
        normalized = icon_gen.reduzir(badge, icon_gen.PCT_BRASAO)
        visible_bounds = normalized.getchannel("A").getbbox()
        visible_sizes.append((visible_bounds[2] - visible_bounds[0], visible_bounds[3] - visible_bounds[1]))
    assert all(max(size) == 160 for size in visible_sizes), visible_sizes
    lighting_sample = Image.new("RGBA", (32, 32), (60, 60, 60, 255))
    ImageDraw.Draw(lighting_sample).rectangle((0, 16, 31, 31), fill=(200, 200, 200, 255))
    lit_sample = icon_gen._realcar_luz_moldura(lighting_sample)
    assert lit_sample.getpixel((16, 8))[0] < 60
    assert lit_sample.getpixel((16, 24))[0] > 200
    mestre_lit_sample = icon_gen._realcar_luz_moldura(lighting_sample, mestre=True)
    assert mestre_lit_sample.getpixel((16, 24))[0] > lit_sample.getpixel((16, 24))[0]
    assert mestre_lit_sample.getpixel((16, 8))[0] == lit_sample.getpixel((16, 8))[0]
    glyph_shape = np.zeros((glyph_gen.LADO_GLIFO, glyph_gen.LADO_GLIFO), bool)
    glyph_shape[40:88, 56:72] = True
    glyph_image = glyph_gen.render(Image.fromarray(glyph_shape.astype(np.uint8) * 255))
    glyph_alpha = np.asarray(glyph_image.getchannel("A"))
    assert glyph_alpha.shape == (glyph_gen.LADO_GLIFO, glyph_gen.LADO_GLIFO)
    assert (glyph_alpha == 255).any() and ((glyph_alpha > 0) & (glyph_alpha < 255)).any()
    assert glyph_alpha[0, 0] == 0
    weapon = icon_gen.armas()[0]
    with patch("ddiconstudio.icon_gen._montar_fundo", side_effect=AssertionError("background was discarded")):
        silhouette = icon_gen.render(arma=weapon, sem_moldura=True, usar_chanfro=False, sombra=False)
        transparent_badge = icon_gen.render(arma=weapon, transparente=True, usar_chanfro=False, sombra=False)
        rendered_glyph = icon_gen.render_glifo([dict(arma=weapon)])
    assert silhouette.getchannel("A").getbbox() is not None
    assert transparent_badge.getchannel("A").getbbox() is not None
    assert rendered_glyph is not None
    shadow_source = Image.new("RGBA", (64, 64), (220, 180, 90, 255))
    shadow_layer, weapon_layer = icon_gen._camada_da_arma(
        shadow_source, 0, 0, True, None
    )
    shadow_alpha = shadow_layer.getchannel("A").getextrema()
    assert shadow_alpha[1] == 255, shadow_alpha
    assert weapon_layer.getchannel("A").getbbox() is not None
    badge_background = Image.new("RGBA", (32, 32), (100, 40, 30, 255))
    first_weapon = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(first_weapon).rectangle((5, 5, 21, 21), fill=(220, 180, 90, 255))
    second_shadow = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(second_shadow).rectangle((10, 8, 24, 23), fill=(0, 0, 0, 128))
    second_weapon = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    ImageDraw.Draw(second_weapon).rectangle((16, 12, 27, 27), fill=(60, 170, 210, 255))
    layered_badge = icon_gen._compor_camadas_de_armas(
        badge_background, [second_shadow], [first_weapon, second_weapon]
    )
    assert layered_badge.getpixel((12, 10)) == (220, 180, 90, 255)
    assert layered_badge.getpixel((2, 2)) == (100, 40, 30, 255)

    page = FakePage()
    app = App(page)
    with tempfile.TemporaryDirectory(prefix="DDIconStudio-Rename-Check-") as icons_dir:
        for name in ("16.png", "16_arma.png", "16_banner.png", "17_banner.png"):
            with open(os.path.join(icons_dir, name), "wb") as image_file:
                image_file.write(b"test")
        rename_app = App(FakePage())
        rename_app.pasta_icones = icons_dir
        rename_app.numero_selecionado = 16

        async def ask_new_number(*_):
            return 17

        rename_app._ask_number = ask_new_number
        try:
            await rename_app._rename_icon(None)
        except OSError:
            pass
        assert os.path.isfile(os.path.join(icons_dir, "16.png"))
        assert os.path.isfile(os.path.join(icons_dir, "16_arma.png"))
        assert os.path.isfile(os.path.join(icons_dir, "16_banner.png"))
        assert os.path.isfile(os.path.join(icons_dir, "17_banner.png"))
        assert not os.path.exists(os.path.join(icons_dir, "17.png"))
        assert rename_app.numero_selecionado == 16

    with tempfile.TemporaryDirectory(prefix="DDIconStudio-Rename-Rollback-") as icons_dir:
        for name in ("16.png", "16_arma.png", "16_banner.png"):
            with open(os.path.join(icons_dir, name), "wb") as image_file:
                image_file.write(b"test")
        rename_app = App(FakePage())
        rename_app.pasta_icones = icons_dir
        rename_app.numero_selecionado = 16
        rename_app._ask_number = ask_new_number
        original_rename = os.rename
        rename_calls = 0

        def fail_second_rename(source, target):
            nonlocal rename_calls
            rename_calls += 1
            if rename_calls == 2:
                raise OSError("simulated rename failure")
            return original_rename(source, target)

        with patch("ddiconstudio.gui.main_window.os.rename", side_effect=fail_second_rename):
            await rename_app._rename_icon(None)
        for name in ("16.png", "16_arma.png", "16_banner.png"):
            assert os.path.isfile(os.path.join(icons_dir, name))
        assert not any(os.path.exists(os.path.join(icons_dir, name)) for name in ("17.png", "17_arma.png", "17_banner.png"))
        assert rename_app.numero_selecionado == 16

    assert app.body.content is not None
    assert page.window.maximized
    page.on_resize(type("ResizeEvent", (), {"width": 1920, "height": 1080})())
    assert round(app.scaled_content.scale.scale, 3) == 1.174
    assert round(app.scaled_content.width * app.scaled_content.scale.scale) == 1920
    assert round(app.scaled_content.height * app.scaled_content.scale.scale) == 1080
    page.on_resize(type("ResizeEvent", (), {"width": 1000, "height": 700})())
    assert app.scaled_content.scale.scale == 1.0
    print("biblioteca Flet aberta")

    with tempfile.TemporaryDirectory(prefix="DDIconStudio-GUI-Check-") as icons_dir:
        image = Image.new("RGBA", (200, 200), (90, 30, 50, 255))
        image.save(os.path.join(icons_dir, "16.png"))
        image.save(os.path.join(icons_dir, "16_arma.png"))
        image.save(os.path.join(icons_dir, "16_banner.png"))
        app.pasta_icones = icons_dir
        app._show_section(0)
        assert len(app.icones_na_pasta()) == 1
        assert 16 in app.icones_para_pak()
        assert 16 in app.glifos_para_pak()
        assert 16 in app.banners_para_pak()
        print("biblioteca, pre-visualizacao e entradas PAK ok")

    app._show_section(1)
    app.generator.pasta_icones = app.pasta_icones
    await asyncio.sleep(0.1)
    await app.generator._refresh_preview()
    assert app.generator.icone is not None
    assert app.generator.banner is not None
    assert isinstance(app.generator.weapon_grid, ft.Row)
    assert app.generator.weapon_grid.wrap
    assert app.generator.weapon_grid.expand is None
    with tempfile.TemporaryDirectory(prefix="DDIconStudio-Banner-Pattern-") as pattern_dir:
        pattern_path = os.path.join(pattern_dir, "pattern.png")
        pattern_image = Image.new("RGBA", (64, 800), (0, 0, 0, 0))
        ImageDraw.Draw(pattern_image).polygon(
            [(32, 2), (40, 90), (37, 690), (50, 760), (32, 735), (14, 760), (27, 690), (24, 90)],
            fill=(190, 160, 95, 235),
        )
        pattern_image.save(pattern_path)

        async def pick_banner_pattern(**_):
            return [type("PickedFile", (), {"path": pattern_path, "name": "pattern.png"})()]

        original_pick_files = app.file_picker.pick_files
        app.file_picker.pick_files = pick_banner_pattern
        app.generator.banner_pattern_dx_slider.value = 40
        app.generator.banner_contour_dy_slider.value = -20
        try:
            await app.generator.importar_padrao_banner(None)
        finally:
            app.file_picker.pick_files = original_pick_files
        assert app.generator.banner_pattern is not None
        assert app.generator.banner_pattern.size == (37, 759)
        assert app.generator.banner_pattern_scale_slider.value == 0.55
        assert app.generator.scale_value_fields["banner_pattern_scale"].value == "0.55"
        assert app.generator.banner_pattern_dx_slider.value == 0
        assert app.generator.scale_value_fields["banner_pattern_dx"].value == "0"
        assert app.generator.banner_contour_dy_slider.value == 0
        no_pattern = np.asarray(banner_gen.render(cor_a=banner_gen.PALETA["vermelho"], estilo="simples"))
        assert not np.array_equal(np.asarray(app.generator.banner), no_pattern)
        app.generator.banner_pattern_dx_slider.value = 80
        await app.generator._changed(None)
        pattern_moved = np.asarray(app.generator.banner)
        app.generator.banner_pattern_dx_slider.value = 0
        app.generator.banner_contour_dx_slider.value = 40
        await app.generator._changed(None)
        contour_moved = np.asarray(app.generator.banner)
        assert not np.array_equal(pattern_moved, contour_moved)
        await app.generator.remover_padrao_banner(None)

    app.generator.scale_value_fields["scale"].value = "1,25"
    app.generator._set_slider_from_field(
        "scale",
        type("Event", (), {"control": app.generator.scale_value_fields["scale"]})(),
    )
    assert app.generator.scale_slider.value == 1.25
    assert app.generator.scale_value_fields["scale"].value == "1.25"
    app.generator.scale_value_fields["dx"].value = "-12"
    app.generator._set_slider_from_field(
        "dx",
        type("Event", (), {"control": app.generator.scale_value_fields["dx"]})(),
    )
    assert app.generator.dx_slider.value == -12
    app.generator.scale_value_fields["rotation"].value = "999"
    app.generator._set_slider_from_field(
        "rotation",
        type("Event", (), {"control": app.generator.scale_value_fields["rotation"]})(),
    )
    assert app.generator.rotation_slider.value == 180
    app.generator.scale_value_fields["banner_pattern_dy"].value = "-37"
    app.generator._set_slider_from_field(
        "banner_pattern_dy",
        type("Event", (), {"control": app.generator.scale_value_fields["banner_pattern_dy"]})(),
    )
    assert app.generator.banner_pattern_dy_slider.value == -37
    app.generator.banner_pattern_dy_slider.value = 0
    armas = icon_gen.armas()
    assert len(armas) >= 2
    await app.generator._select_weapon(armas[0])
    app.generator.dx_slider.value, app.generator.dy_slider.value = 30, -20
    await app.generator._changed(None)
    await app.generator._select_weapon(armas[1])
    assert (app.generator.dx_slider.value, app.generator.dy_slider.value) == (0, 0)
    assert app.generator.scale_value_fields["dx"].value == "0"
    await app.generator._select_weapon("")
    app.generator.dx_slider.value = app.generator.dy_slider.value = 0
    await app.generator._changed(None)
    assert not hasattr(app.generator, "frame_metal_dropdown")
    assert app.generator.metal_moldura == "bronze"
    await app.generator._select_frame("mestre")
    assert app.generator.metal_moldura == "ouro"
    await app.generator._select_frame("avancada")
    assert app.generator.metal_moldura == "bronze"
    composition_rows = [
        control for control in walk_controls(app.generator.root)
        if isinstance(control, ft.Row) and control.wrap
    ]
    assert composition_rows
    assert all(
        not isinstance(child, ft.Container) or child.expand is None
        for row in composition_rows
        for child in row.controls
    )
    await app.generator._select_color((20, 120, 80), "a")
    await app.generator.adicionar_camada(None)
    await app.generator.mover_camada(-1)
    await app.generator.remover_camada(None)
    await app.generator.sortear_cores(None)
    assert app.generator.icone is not None
    assert_handlers_not_dropped(app.generator.root)
    assert page.tasks
    print("gerador Flet e previas ok")

    mask = Image.new("L", (48, 48), 0)
    ImageDraw.Draw(mask).polygon([(22, 2), (28, 20), (46, 22), (28, 28), (24, 46), (19, 28), (2, 24), (19, 20)], fill=255)
    import_dialog = DialogoImportacao(app.generator, mask, "manual.png")
    dialog = import_dialog.build()
    assert isinstance(dialog, ft.AlertDialog)
    await import_dialog.preview_task
    assert not hasattr(import_dialog, "holes_switch")
    assert not hasattr(import_dialog, "hole_density_slider")
    preview_before = import_dialog.preview_box.content.src
    import_dialog.forge_slider.value = 0.0
    import_dialog._read_sliders()
    assert import_dialog.acabamento.forjado == 0.0
    assert import_dialog.preview_box.content.src == preview_before
    await import_dialog._apply(None)
    await import_dialog.preview_task
    assert import_dialog.preview_box.content.src != preview_before
    await import_dialog._preset("Gasto")
    await import_dialog.preview_task
    assert import_dialog.acabamento.riscos == 2.5 and import_dialog.shine_slider.value == 0.6
    assert import_dialog.acabamento.semente == 0
    await import_dialog._vary(None)
    await import_dialog.preview_task
    assert import_dialog.acabamento.semente != 0 and import_dialog.acabamento.riscos == 2.5
    await import_dialog._preset("Liso")
    await import_dialog.preview_task
    assert import_dialog.acabamento == chanfro.Acabamento(forjado=0.0, riscos=0.0)
    base_mask = Image.new("L", (300, 300), 0)
    ImageDraw.Draw(base_mask).ellipse((20, 20, 280, 280), fill=255)
    padrao = chanfro.aplicar(base_mask).tobytes()
    assert chanfro.aplicar(base_mask, acabamento=chanfro.Acabamento()).tobytes() == padrao
    for variacao in (dict(tamanho=2.0), dict(riscos=3.0), dict(brilho=0.0), dict(semente=7)):
        assert chanfro.aplicar(base_mask, acabamento=chanfro.Acabamento(**variacao)).tobytes() != padrao
    print("dialogo de importacao Flet aberto")

    from types import SimpleNamespace as Evento
    def em(x, y):
        return Evento(local_position=Evento(x=x, y=y))
    app._show_section(app.SECAO_EDITOR)
    editor = app.editor
    assert editor is not None and app.body.content is editor.root
    def tecla(key, ctrl=False, shift=False):
        return Evento(key=key, ctrl=ctrl, shift=shift, alt=False, meta=False)
    def em_doc(x, y):
        return em(*editor.vista.para_tela((x, y)))
    async def renderizado():
        while editor._tarefa is not None and not editor._tarefa.done():
            await editor._tarefa
    await renderizado()
    assert editor.desenho.vazio and editor.undo_button.disabled and editor.imagem.src != PIXEL_TRANSPARENTE
    editor.symmetry_button.selected = ["vertical"]
    await editor._inicio(em_doc(100, 100))
    for x in range(105, 200, 5):
        await editor._arrasto(em_doc(x, 100 + x // 3))
    assert editor.temporarias and editor.canvas.shapes
    await editor._fim(None)
    saida = editor.desenho.saida()
    assert not editor.temporarias and saida.getpixel((150, 150)) == 255 and saida.getpixel((330, 150)) == 255
    editor.symmetry_button.selected = ["nenhuma"]
    await editor._teclado(tecla("P"))
    assert editor.ferramenta == "poligono" and editor.opcoes["pontos"].visible
    for ponto in ((240, 300), (300, 420), (180, 420)):
        await editor._clique(em_doc(*ponto))
    assert not editor.close_button.disabled
    await editor._clique(em_doc(241, 301))
    assert not editor.pontos and editor.desenho.saida().getpixel((240, 380)) == 255
    editor._escolher_ferramenta("elipse")
    editor._alternar_modo()
    await editor._inicio(em_doc(220, 370))
    await editor._arrasto(em_doc(260, 400))
    await editor._fim(None)
    assert editor.desenho.saida().getpixel((240, 385)) == 0
    await editor._desfazer(None)
    assert editor.desenho.saida().getpixel((240, 385)) == 255
    await editor._refazer(None)
    assert editor.desenho.saida().getpixel((240, 385)) == 0
    await editor._teclado(tecla("z", ctrl=True))
    assert editor.desenho.saida().getpixel((240, 385)) == 255
    editor._alternar_modo()
    assert not editor.recortar
    editor._escolher_ferramenta("curva")
    for ponto in ((60, 380), (120, 330), (120, 440)):
        await editor._clique(em_doc(*ponto))
    await editor._teclado(tecla("Enter"))
    assert editor.desenho.saida().getpixel((100, 385)) == 255
    editor._escolher_ferramenta("estrela")
    editor.symmetry_button.selected = ["radial"]
    editor.raios_slider.value = 4
    await editor._inicio(em_doc(380, 380))
    await editor._arrasto(em_doc(380, 350))
    await editor._fim(None)
    assert editor.desenho.saida().getpixel((380, 375)) == 255 and editor.desenho.saida().getpixel((100, 380)) == 255
    editor.symmetry_button.selected = ["nenhuma"]
    editor._escolher_ferramenta("balde")
    await editor._clique(em_doc(5, 5))
    assert editor.desenho.saida().getpixel((5, 470)) == 255
    await editor._desfazer(None)
    await editor._operar(lambda: editor.desenho.engrossar(3))
    assert editor.desenho.saida().getpixel((150, 154)) == 255
    await editor._teclado(tecla("]"))
    assert editor.size_slider.value > 24
    editor._zoom(2, (300, 300))
    assert editor.zoom_text.value == "200%"
    await editor._teclado(tecla("0"))
    await renderizado()
    await editor.concluir(None)
    assert isinstance(page.dialogs[-1], ft.AlertDialog)
    page.pop_dialog()
    editor.desenho.abrir(mask)
    assert abs(editor.desenho.resultado().size[0] - round(480 * 0.85)) <= 1

    await editor._trocar_tipo(Evento(control=Evento(selected=["banner"])))
    assert editor.desenho.tamanho == (512, 1024) and editor.desenho.vazio and editor.guide_switch.visible
    await renderizado()
    editor._escolher_ferramenta("retangulo")
    await editor._inicio(em_doc(200, 350))
    await editor._arrasto(em_doc(310, 500))
    await editor._fim(None)
    assert editor.desenho.saida().getpixel((256, 425)) == 255
    nome_teste = "zz_teste_smoke_editor"
    assert not padroes_banner.existe(nome_teste)
    editor.name_field.value = nome_teste
    try:
        await editor.concluir(None)
        assert padroes_banner.existe(nome_teste)
        gerador = app.generator
        assert gerador.banner_pattern is not None and gerador.banner_pattern_scale_slider.value == 1.0
        assert abs(gerador.banner_pattern_dx_slider.value) <= 2 and abs(gerador.banner_pattern_dy_slider.value) <= 2
        assert gerador.banner_library_dropdown.value == nome_teste
    finally:
        if padroes_banner.existe(nome_teste):
            padroes_banner.remover(nome_teste)
        app.generator.atualizar_padroes_banner()
    await editor._trocar_tipo(Evento(control=Evento(selected=["icone"])))
    assert editor.desenho.tamanho == (480, 480) and not editor.desenho.vazio
    await renderizado()
    assert_handlers_not_dropped(editor.root)
    print("editor de silhuetas ok")

    app._show_section(3)
    assert app.generate_button is not None
    assert app.icons_path_field.value == app.pasta_icones
    pak_rows = [
        control for control in walk_controls(app.body.content)
        if isinstance(control, ft.Row) and control.wrap
    ]
    assert pak_rows
    assert all(
        not isinstance(child, ft.Container) or child.expand is None
        for row in pak_rows
        for child in row.controls
    )
    assert sum(control is app.progress for control in walk_controls(app.body.content)) == 1
    assert app.progress.height == 4
    log_panel = app.body.content.content.controls[2].content.controls[1]
    assert log_panel.height is None
    assert log_panel.content.scroll is None
    print("montagem de PAK Flet aberta")

    original_config = app_paths.CONFIG
    try:
        with tempfile.TemporaryDirectory(prefix="DDIconStudio-Config-Fail-") as config_path:
            app_paths.CONFIG = config_path
            close_page = FakePage()
            App(close_page)
            close_event = type("WindowEvent", (), {"type": ft.WindowEventType.CLOSE})()
            assert close_page.window.prevent_close
            assert inspect.iscoroutinefunction(close_page.window.on_event)
            await close_page.window.on_event(close_event)
            assert len(close_page.dialogs) == 1
            assert close_page.window.prevent_close and not close_page.window.closed
            await close_page.dialogs[0].actions[0].on_click(None)
            assert not close_page.dialogs
            assert close_page.window.prevent_close and not close_page.window.closed
            await close_page.window.on_event(close_event)
            await close_page.dialogs[0].actions[1].on_click(None)
            assert not close_page.window.prevent_close and close_page.window.closed

        with tempfile.TemporaryDirectory(prefix="DDIconStudio-Config-Ok-") as config_dir:
            app_paths.CONFIG = os.path.join(config_dir, "config.json")
            close_page = FakePage()
            App(close_page)
            await close_page.window.on_event(close_event)
            assert close_page.window.closed
            assert os.path.isfile(app_paths.CONFIG)
    finally:
        app_paths.CONFIG = original_config
    print("fechamento e salvamento de preferencias ok")


asyncio.run(smoke())
