"""DDIconStudio: gerador de icones de vocacao do DDCore (Dragon's Dogma 2)."""
import os
import sys
import flet as ft

def autoteste(saida):
    """Sem abrir janela, gera um ícone e um PAK de teste em `saida`; devolve 0 em sucesso e 1 em falha."""
    from ddiconstudio import icon_gen, pak_builder
    os.makedirs(saida, exist_ok=True)
    with open(os.path.join(saida, "selftest.log"), "w", encoding="utf-8") as log:
        try:
            armas = icon_gen.armas()
            img = icon_gen.render(moldura="avancada", cor_a=icon_gen.PALETA["vermelho"], arma=armas[0] if armas else None, semente=1)
            img.save(os.path.join(saida, "gerado.png"))
            pak_builder.montar_pak({16: os.path.join(saida, "gerado.png"), 17: None}, saida, log=lambda s: log.write(s + "\n"))
            log.write("OK\n")
        except Exception as e:  # noqa: BLE001
            log.write(f"FALHOU: {type(e).__name__}: {e}\n")
            return 1
    return 0


def main():
    """Ponto de entrada da GUI; `--selftest <pasta>` executa a verificação sem interface."""
    if "--selftest" in sys.argv:
        return autoteste(sys.argv[sys.argv.index("--selftest") + 1])
    from ddiconstudio.gui.main_window import main as gui_main
    ft.run(gui_main)
    return 0


if __name__ == "__main__":
    sys.exit(main())
