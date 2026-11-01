"""Estima o tile do fio bordado das armas dos banners vanilla e grava assets\\base\\fio_tile.npz.

O fio bege-acinzentado das armas nao e ruido: e um tile fixo que se repete a cada ~11.8 px em x e em y (a
autocorrelacao do interior das armas tem pico em 11.8, 23.6, 35.4...; o mesmo tile aparece nos 8 banners com fases
diferentes). A variacao e aditiva e quase neutra (o mesmo numero de niveis nos tres canais), nao multiplicativa.

Para cada banner o fio e separado do pano por cor (tools nao precisa da cor do pano), a variacao local de
luminancia vira amostras (x, y, valor) e o tile e estimado alternando: tile -> fase de cada banner -> tile.

Chaves do .npz: 'tile' (NB x NB, niveis de cinza aditivos, media 0), 'periodo' (px), 'ganho' (3, quanto cada canal
RGB segue o tile; media ~1). banner_gen amostra o tile na tela com periodo continuo (interpolacao bilinear).

Uso:  python tools\\build_fio_tile.py [periodo ...]   (varios periodos: grava o de maior correlacao)
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
from ddiconstudio import app_paths  # noqa: E402
from ddiconstudio.banner_gen import _media_janela, amostrar_tile  # noqa: E402
from ddiconstudio.morfologia import dilatar_mascara  # noqa: E402

# banners 4 (pano verde, a cor passa por fio) e 10 (outro desenho) nao servem para separar o fio
BANNERS = (1, 2, 3, 5, 6, 7, 8, 9)
NB = 48              # bins por periodo (0.25 px)
RAIO_LOCAL = 5       # janela da media local
PASSO_FASE = 0.5     # px
RODADAS = 3
PERIODO_PADRAO = 11.8


def _fio(img):
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    return (r > 55) & (g > 0.70 * r) & (b > 0.50 * r) & (r >= 0.8 * b) & (r < 190)


def _maioria(m):
    p = np.pad(m.astype(np.uint8), 1)
    soma = sum(p[1 + dy:1 + dy + m.shape[0], 1 + dx:1 + dx + m.shape[1]] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    return soma >= 5


def _interior(img):
    """Pixels do fio a 3 px ou mais da borda (a borda tem luz propria)."""
    t = _fio(img)
    caixa = np.zeros_like(t)
    caixa[150:700, 100:412] = True
    t = _maioria(_maioria(t & caixa))
    suave = np.asarray(
        Image.fromarray((t * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.3))
    ) > 127
    miolo = 255 - np.asarray(dilatar_mascara(255 - (suave * 255).astype(np.uint8), 3))
    return miolo > 127


def _amostras(n):
    caminho = os.path.join(RAIZ, 'referencias', 'banners', f'banner_{n:02d}.png')
    img = np.asarray(Image.open(caminho).convert('RGB')).astype(np.float32)
    miolo = _interior(img)
    peso = miolo.astype(np.float32)
    local = np.stack(
        [_media_janela(img[..., c] * peso, RAIO_LOCAL) / np.maximum(_media_janela(peso, RAIO_LOCAL), 1e-3)
         for c in range(3)], -1)
    ys, xs = np.nonzero(miolo)
    return xs.astype(np.float32), ys.astype(np.float32), (img[ys, xs] - local[ys, xs]).astype(np.float32)


def _fases(xs, ys, fase, periodo):
    return ((xs - fase[0]) / periodo) % 1, ((ys - fase[1]) / periodo) % 1


def _estimar(amostras, fases, periodo):
    soma = np.zeros(NB * NB)
    cont = np.zeros(NB * NB)
    for n, (xs, ys, d) in amostras.items():
        u, v = _fases(xs, ys, fases[n], periodo)
        idx = (np.floor(v * NB).astype(int) % NB) * NB + np.floor(u * NB).astype(int) % NB
        soma += np.bincount(idx, d.mean(1), NB * NB)
        cont += np.bincount(idx, minlength=NB * NB)
    tile = (soma / np.maximum(cont, 1)).reshape(NB, NB)
    for eixo in (0, 1):
        tile = 0.25 * np.roll(tile, 1, eixo) + 0.5 * tile + 0.25 * np.roll(tile, -1, eixo)
    return tile - tile.mean()


def _correlacao(tile, amostra, fase, periodo):
    xs, ys, d = amostra
    u, v = _fases(xs, ys, fase, periodo)
    return np.corrcoef(amostrar_tile(tile, u, v), d.mean(1))[0, 1]


def _melhor_fase(tile, amostra, periodo):
    melhor = (-2.0, 0.0, 0.0)
    for oy in np.arange(0, periodo, PASSO_FASE):
        for ox in np.arange(0, periodo, PASSO_FASE):
            c = _correlacao(tile, amostra, (ox, oy), periodo)
            if c > melhor[0]:
                melhor = (c, ox, oy)
    return melhor[1:]


def ajustar(amostras, periodo):
    ordem = list(amostras)
    fases = {ordem[0]: (0.0, 0.0)}
    tile = _estimar({ordem[0]: amostras[ordem[0]]}, fases, periodo)
    for _ in range(RODADAS):
        for n in ordem[1:]:
            fases[n] = _melhor_fase(tile, amostras[n], periodo)
        tile = _estimar(amostras, fases, periodo)
    corr = {n: _correlacao(tile, amostras[n], fases[n], periodo) for n in ordem}
    return tile, fases, corr


def main(periodos):
    amostras = {n: _amostras(n) for n in BANNERS}
    melhor = None
    for periodo in periodos:
        tile, fases, corr = ajustar(amostras, periodo)
        media = float(np.mean(list(corr.values())))
        print(f'periodo {periodo}: correlacao media {media:.3f}', {n: round(float(c), 2) for n, c in corr.items()})
        if melhor is None or media > melhor[0]:
            melhor = (media, periodo, tile)
    _, periodo, tile = melhor
    lum = np.concatenate([d.mean(1) for _, _, d in amostras.values()])
    ganho = np.array([(np.concatenate([d[:, c] for _, _, d in amostras.values()]) * lum).sum() / (lum ** 2).sum()
                      for c in range(3)])
    ganho /= ganho.mean()
    destino = os.path.join(app_paths.ASSETS, 'base', 'fio_tile.npz')
    np.savez_compressed(destino, tile=tile.astype(np.float32), periodo=np.float32(periodo), ganho=ganho.astype(np.float32))
    print(f'gravado {destino}: periodo {periodo}, desvio do tile {tile.std():.1f}, ganho RGB {ganho.round(2)}')


if __name__ == '__main__':
    main([float(p) for p in sys.argv[1:]] or [PERIODO_PADRAO])
