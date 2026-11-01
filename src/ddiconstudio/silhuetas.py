"""Silhuetas de armas: carrega a mascara e grava o chanfro escolhido em assets/silhuetas."""
import os

from PIL import Image, ImageOps

from ddiconstudio import app_paths, chanfro

PASTA = os.path.join(app_paths.ASSETS, "silhuetas")
LIMIAR = 128


def carregar_mascara(caminho):
    """Mascara L da imagem: o alfa, se houver transparencia; senao a figura contra o fundo liso dos cantos."""
    imagem = Image.open(caminho).convert("RGBA")
    alfa = imagem.getchannel("A")
    if alfa.getextrema()[0] < 255:
        return alfa
    cinza = imagem.convert("L")
    cantos = [cinza.getpixel(canto) for canto in ((0, 0), (imagem.width - 1, 0),
                                                  (0, imagem.height - 1), (imagem.width - 1, imagem.height - 1))]
    fundo_claro = sum(cantos) / len(cantos) >= LIMIAR
    return ImageOps.invert(cinza) if fundo_claro else cinza


def carregar_silhueta(caminho):
    """Mascara recortada do arquivo inteiro: partes desconectadas continuam na mesma silhueta."""
    mascara = carregar_mascara(caminho)
    caixa = mascara.getbbox()
    if caixa is None:
        raise ValueError("Nenhuma silhueta encontrada na imagem.")
    return mascara.crop(caixa)


def caminho_da_silhueta(nome):
    return os.path.join(PASTA, nome + ".png")


def existe(nome):
    return os.path.isfile(caminho_da_silhueta(nome))


def remover(nome):
    """Remove a silhueta do catalogo."""
    os.remove(caminho_da_silhueta(nome))


def salvar(nome, mascara, intensidade=chanfro.INTENSIDADE_PADRAO, nivel_chanfro=0.0,
           acabamento=chanfro.Acabamento()):
    """Grava a imagem chanfrada na escala de referencia, preservando a mascara no canal alfa."""
    mascara = chanfro.normalizar(mascara)
    imagem = chanfro.aplicar(
        mascara,
        intensidade=intensidade,
        nivel_chanfro=nivel_chanfro,
        acabamento=acabamento,
    )
    os.makedirs(PASTA, exist_ok=True)
    imagem.save(caminho_da_silhueta(nome))
