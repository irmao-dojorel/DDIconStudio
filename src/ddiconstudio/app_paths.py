"""Pastas do aplicativo (ao lado do .exe quando empacotado) e configuracao do usuario."""
import json
import os
import sys

FROZEN = getattr(sys, "frozen", False)
APP_DIR = (os.path.dirname(sys.executable) if FROZEN
           else os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
ASSETS = os.path.join(APP_DIR, "assets")
BASE_PAK = os.path.join(ASSETS, "base", "Vanilla_Icons.pak")
UVS_MODELO = os.path.join(ASSETS, "base", "UVS_job_01_base.uvs")
UVS_PAINEL = os.path.join(ASSETS, "base", "UVS_ui040101_jogo.uvs")
UVS_BANNER = os.path.join(ASSETS, "base", "UVS_ui040102_jogo.uvs")
ICONS_DEFAULT = os.path.join(APP_DIR, "icons")
CONFIG = os.path.join(APP_DIR, "config.json")


def carregar():
    """Lê config.json; arquivo ausente, JSON inválido ou raiz não-dicionário resulta em {}."""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def salvar(cfg):
    """Grava as preferências em UTF-8 e informa se a gravação foi concluída."""
    try:
        with open(CONFIG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        return False
    return True
