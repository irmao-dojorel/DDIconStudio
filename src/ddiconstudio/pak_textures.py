"""Compose icon and panel texture sheets and measure their BC7 round-trip quality."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LADO_CELULA_LISTA = 200
LARGURA_FOLHA_LISTA, ALTURA_FOLHA_LISTA = 800, 800
LADO_CELULA_PAINEL = 128
LARGURA_FOLHA_PAINEL, ALTURA_FOLHA_PAINEL = 512, 512


def _celula_teste(numero, quadro):
    """Cria um circulo colorido numerado para celulas de teste sem PNG."""
    celula = Image.new("RGBA", (LADO_CELULA_LISTA, LADO_CELULA_LISTA), (0, 0, 0, 0))
    matiz = quadro / 16 * 6
    fracao = matiz - math.floor(matiz)
    vermelho, verde, azul = ((1, fracao, 0), (1 - fracao, 1, 0), (0, 1, fracao),
                             (0, 1 - fracao, 1), (fracao, 0, 1), (1, 0, 1 - fracao))[int(matiz) % 6]
    cor = tuple(int(60 + 195 * canal) for canal in (vermelho, verde, azul)) + (255,)
    desenho = ImageDraw.Draw(celula)
    desenho.ellipse((10, 10, 190, 190), fill=cor, outline=(255, 255, 255, 255), width=6)
    try:
        fonte = ImageFont.truetype("arialbd.ttf", 64)
    except OSError:
        fonte = ImageFont.load_default(64)
    desenho.text((LADO_CELULA_LISTA // 2, LADO_CELULA_LISTA // 2), str(numero), fill=(255, 255, 255, 255), font=fonte, anchor="mm")
    return celula


def montar_folha(folha, icones):
    """Compõe uma folha 800x800 a partir de imagens indexadas pelo número do ícone."""
    imagem = Image.new("RGBA", (LARGURA_FOLHA_LISTA, ALTURA_FOLHA_LISTA), (0, 0, 0, 0))
    for quadro in range(16):
        numero = folha * 16 + quadro
        if numero not in icones:
            continue
        origem = icones[numero]
        if origem is None:
            celula = _celula_teste(numero, quadro)
        else:
            celula = (origem if isinstance(origem, Image.Image) else Image.open(origem)).convert("RGBA")
            if celula.size != (LADO_CELULA_LISTA, LADO_CELULA_LISTA):
                celula = celula.resize((LADO_CELULA_LISTA, LADO_CELULA_LISTA), Image.LANCZOS)
        imagem.paste(celula, ((quadro % 4) * LADO_CELULA_LISTA, (quadro // 4) * LADO_CELULA_LISTA))
    return imagem


def _psnr(original, decodificada):
    """Mede fidelidade visual da textura reconstruida, ponderando RGB pelo alfa."""
    original, decodificada = np.asarray(original, np.float64), np.asarray(decodificada, np.float64)
    rgb_original = original[..., :3] * original[..., 3:] / 255
    rgb_decodificada = decodificada[..., :3] * decodificada[..., 3:] / 255
    erro_medio = (((rgb_original - rgb_decodificada) ** 2).sum()
                  + ((original[..., 3] - decodificada[..., 3]) ** 2).sum()) / original.size
    return 99.0 if erro_medio == 0 else 10 * math.log10(255 * 255 / erro_medio)


def montar_folha_painel(folha, glifos):
    """Compõe uma folha 512x512 a partir de glifos indexados pelo número do ícone."""
    imagem = Image.new("RGBA", (LARGURA_FOLHA_PAINEL, ALTURA_FOLHA_PAINEL), (0, 0, 0, 0))
    for quadro in range(16):
        glifo = glifos.get(folha * 16 + quadro)
        if glifo is None:
            continue
        glifo = glifo.convert("RGBA")
        if glifo.size != (LADO_CELULA_PAINEL, LADO_CELULA_PAINEL):
            glifo = glifo.resize((LADO_CELULA_PAINEL, LADO_CELULA_PAINEL), Image.LANCZOS)
        imagem.paste(glifo, ((quadro % 4) * LADO_CELULA_PAINEL, (quadro // 4) * LADO_CELULA_PAINEL))
    return imagem