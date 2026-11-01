"""Biblioteca de padroes do banner (assets/padroes_banner): PNG 512x1024 branco com a forma no alfa, na posicao
em que foi desenhado sobre o banner."""
import os

from PIL import Image

from ddiconstudio import app_paths, banner_gen

PASTA = os.path.join(app_paths.ASSETS, "padroes_banner")
TAMANHO = (banner_gen.LARGURA, banner_gen.ALTURA)


def caminho(nome):
    return os.path.join(PASTA, nome + ".png")


def existe(nome):
    return os.path.isfile(caminho(nome))


def listar():
    try:
        return sorted(os.path.splitext(arquivo)[0] for arquivo in os.listdir(PASTA) if arquivo.lower().endswith(".png"))
    except OSError:
        return []


def carregar(nome):
    with Image.open(caminho(nome)) as imagem:
        return imagem.convert("RGBA")


def salvar(nome, mascara):
    """Grava a mascara L (tamanho do banner) como padrao branco com alfa."""
    if mascara.size != TAMANHO:
        raise ValueError(f"O padrao do banner deve ter {TAMANHO[0]}x{TAMANHO[1]} px.")
    imagem = Image.new("RGBA", TAMANHO, (255, 255, 255, 0))
    imagem.putalpha(mascara.convert("L"))
    os.makedirs(PASTA, exist_ok=True)
    imagem.save(caminho(nome))
    return imagem


def remover(nome):
    os.remove(caminho(nome))


def posicionar(padrao):
    """(recorte, dx, dy) de um padrao do tamanho do banner: o bordado fica exatamente onde foi desenhado."""
    caixa = padrao.getchannel("A").getbbox()
    if caixa is None:
        raise ValueError("O padrao esta vazio.")
    dx = (caixa[0] + caixa[2]) / 2 - banner_gen.CENTRO[0]
    dy = (caixa[1] + caixa[3]) / 2 - banner_gen.CENTRO[1]
    return padrao.crop(caixa), dx, dy
