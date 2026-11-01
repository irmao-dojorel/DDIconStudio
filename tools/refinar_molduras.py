"""Refina molduras de assets\\molduras: contorno anti-serrilhado (alfa e mascara) e emenda moldura/interior.

As molduras extraidas de icones do jogo (avancada, simples) ficam guardadas em referencias\\molduras
e o refino sempre parte delas, entao rodar de novo nao acumula.
"""
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
from ddiconstudio import app_paths  # noqa: E402

MOLDURAS = os.path.join(app_paths.ASSETS, 'molduras')
ORIG = os.path.join(RAIZ, 'referencias', 'molduras')
DO_JOGO = ('avancada', 'simples')
SUPER = 4          # supersample do contorno
SIGMA = 0.55       # suavizacao do contorno (px da imagem final)


def _f(a):
    return Image.fromarray(np.asarray(a, np.float32), 'F')


def _blur(a, r):
    """Blur gaussiano separavel em float (o PIL nao desfoca modo F)."""
    k = np.arange(-int(3 * r + 1), int(3 * r + 1) + 1, dtype=np.float32)
    k = np.exp(-k * k / (2 * r * r))
    k /= k.sum()
    p = len(k) // 2
    b = np.pad(a.astype(np.float32), p, mode='edge')
    b = sum(k[i] * b[:, i:i + a.shape[1]] for i in range(len(k)))
    return sum(k[i] * b[i:i + a.shape[0], :] for i in range(len(k)))


def contorno_liso(a):
    """Alfa 0-255 -> mesmo formato com o contorno (limiar 50%) suavizado e anti-serrilhado."""
    h, w = a.shape
    up = np.clip(np.array(_f(a).resize((w * SUPER, h * SUPER), Image.BICUBIC)), 0, 255)
    duro = (_blur(up, SIGMA * SUPER) > 127).astype(np.float32) * 255
    return np.array(_f(duro).resize((w, h), Image.BOX), np.float32)


def _preencher_cor(g, a):
    """Estende o cinza para pixels quase sem alfa (media ponderada pelo alfa da vizinhanca)."""
    out = g.copy()
    falta = a < 8
    for r in (1.0, 2.0, 4.0):
        num, den = _blur(g * a, r), _blur(a, r)
        ok = falta & (den > 1)
        out[ok] = num[ok] / den[ok]
        falta &= ~ok
    return out


def _buracos(m):
    """Fecha buracos pequenos (nao ligados a borda) de uma mascara booleana."""
    inv = Image.fromarray(((~m) * 255).astype(np.uint8)).copy()
    ImageDraw.floodfill(inv, (0, 0), 128, thresh=0)
    return m | (np.array(inv) == 255)


def refinar(fr, mask):
    """fr: RGBA cinza; mask: L. Devolve (fr, mask) refinados."""
    g = np.array(fr.convert('L'), np.float32)
    a0 = np.array(fr.getchannel('A'), np.float32)
    m0 = np.array(mask.convert('L'), np.float32)

    a = contorno_liso(a0)
    g = _preencher_cor(g, a0)

    m = contorno_liso(m0)
    dentro = _buracos(m > 127)
    m = np.maximum(m, dentro * 255.0)
    # a mascara entra 1,5 px por baixo da moldura: sem fresta onde a borda interna e semitransparente
    sob = Image.fromarray(m.astype(np.uint8)).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(0.5))
    m = np.where(a > 8, np.maximum(m, np.array(sob, np.float32)), m)

    g8 = np.clip(g, 0, 255).round().astype(np.uint8)
    a8 = np.clip(a, 0, 255).round().astype(np.uint8)
    out = Image.merge('RGBA', [Image.fromarray(g8)] * 3 + [Image.fromarray(a8)])
    return out, Image.fromarray(np.clip(m, 0, 255).round().astype(np.uint8), 'L')


def main():
    os.makedirs(ORIG, exist_ok=True)
    for nome in DO_JOGO:
        for suf in ('', '_mask'):
            orig = os.path.join(ORIG, nome + suf + '.png')
            if not os.path.isfile(orig):
                shutil.copy2(os.path.join(MOLDURAS, nome + suf + '.png'), orig)
        fr, mk = refinar(Image.open(os.path.join(ORIG, nome + '.png')).convert('RGBA'),
                         Image.open(os.path.join(ORIG, nome + '_mask.png')))
        fr.save(os.path.join(MOLDURAS, nome + '.png'))
        mk.save(os.path.join(MOLDURAS, nome + '_mask.png'))
        print('refinada', nome)


if __name__ == '__main__':
    main()
