"""Gera assets\\base\\banner_escudo.npz a partir do banner_10 (estilo do icone 'escudo'): tira as armas e separa pano/bordado.

O banner_10 e unico (nao ha outros com o mesmo desenho), entao nao da para ajustar por minimos quadrados como
simples/coroa: as armas (flecha, espada e tocha douradas) sao apagadas por preenchimento de textura (copia de
retalhos 9x9 do proprio banner) e o modelo e  v = s*cor + b  com s = sombra do pano e b = bordado (prata/ouro).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
from ddiconstudio import app_paths  # noqa: E402

FONTE = os.path.join(RAIZ, 'referencias', 'banners', 'banner_10.png')
DESTINO = os.path.join(app_paths.ASSETS, 'base', 'banner_escudo.npz')
CAIXA = (140, 175, 392, 640)     # x0, y0, x1, y1 onde ficam as armas
AREA = (96, 60, 416, 760)        # recorte de trabalho do preenchimento (simetrico em x=256)
CENTRO_X = (205, 310)            # faixa dos paineis do centro (divisoria em x~256)
R = 4                            # raio do retalho (9x9)
BUSCA = (1, 320)                 # meia janela de busca (dx, dy) nos paineis do centro: so na vertical, eles
#                                  se repetem e assim a divisoria continua reta
BUSCA_LARGA = 40                 # dx no pano liso (onde ficavam a flecha e a tocha)
COR_PANO = np.array([35, 28, 29], np.float32)   # mediana do pano liso do banner_10 (s = 1)
S_JOELHO, S_FIO = 1.3, 0.6      # pano: s ate S_JOELHO; bordado prateado: s cai para S_FIO (ver modelo)
SOMBRA = 1.0                     # quanto das dobras/manchas grandes do pano e aplainado (0 = nada, 1 = tudo)
RAIO_SOMBRA = 6                  # raio (caixa 2x) da sombra aplainada: menor pega dobras estreitas, maior mantem textura
LISO_MAX = 2.0                   # p0 acima disso e bordado (fora da media da sombra); abaixo e pano, inclusive brilho de dobra
VAO_BORDADO = 0.5                # quanto sobra do escuro entre os fios do bordado (1 = original)


def _morf(m, n, filtro):
    im = Image.fromarray((m * 255).astype(np.uint8))
    for _ in range(abs(n)):
        im = im.filter(filtro(3))
    return np.array(im) > 127


def _caixa(a, r):
    """Media em caixa (2r+1)^2 por soma acumulada."""
    p = np.pad(a.astype(np.float64), r + 1, mode='edge')
    c = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return (s / (k * k))[:a.shape[0], :a.shape[1]].astype(np.float32)


def _ouro(rgb):
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    return ((rgb[..., 1] - rgb[..., 2]) > 12) & (lum > 30)


def armas(rgb):
    """Mascara das armas: bordado dourado (g-b alto) dentro da CAIXA, fechado e um pouco dilatado."""
    ouro = _ouro(rgb)
    x0, y0, x1, y1 = CAIXA
    caixa = np.zeros(ouro.shape, bool)
    caixa[y0:y1, x0:x1] = True
    m = ouro & caixa
    m = _morf(_morf(m, 3, ImageFilter.MaxFilter), 3, ImageFilter.MinFilter)   # fecha o bordado
    # so componentes grandes (as tres armas), nada de pontinhos do brasao
    img = Image.fromarray((m * 255).astype(np.uint8))
    out = np.zeros(m.shape, bool)
    vistos = np.zeros(m.shape, bool)
    for y, x in zip(*np.nonzero(m)):
        if vistos[y, x]:
            continue
        t = img.copy()
        ImageDraw.floodfill(t, (int(x), int(y)), 128, thresh=0)
        comp = np.array(t) == 128
        vistos |= comp
        if comp.sum() > 1500:
            out |= comp
    # buracos pequenos dentro das armas
    inv = Image.fromarray(((~out) * 255).astype(np.uint8)).copy()   # sem copy o floodfill nao altera
    ImageDraw.floodfill(inv, (0, 0), 128, thresh=0)
    out |= np.array(inv) == 255
    return _morf(out, 4, ImageFilter.MaxFilter)   # contorno escuro e sombra do bordado


def preencher(rgb, alvo, valido, proibido, centro):
    """Preenchimento por retalhos (Criminisi simplificado): da borda para dentro, copia o melhor retalho 9x9.

    proibido: pixels que nao podem ser copiados (ouro); centro: (x0, x1) da faixa de busca so vertical."""
    img = rgb.copy()
    falta = alvo.copy()
    H, W = falta.shape
    k = 2 * R + 1
    # centros de onde se pode copiar: retalho inteiro conhecido, dentro do pano e sem ouro (coroa de baixo)
    fonte = _caixa((~alvo & valido & ~proibido).astype(np.float32), R) > 0.999
    fonte[:R + 1] = fonte[-R - 1:] = False
    fonte[:, :R + 1] = fonte[:, -R - 1:] = False
    # o banner e quase simetrico em x=256 (o recorte tambem): o espelho entra como fonte extra
    orig, espelho = rgb, rgb[:, ::-1]
    # pano liso nao copia dos paineis do centro (senao a costura pontilhada da borda deles vira uma linha)
    fora = fonte.copy()
    fora[:, centro[0] - 6:centro[1] + 7] = False
    fontes = {True: (fonte, fonte[:, ::-1]), False: (fora, fora[:, ::-1])}
    conf = (~falta).astype(np.float32)
    passos = 0

    def busca(src, ok, y, x, dxmax, P, M):
        ya, yb = max(R, y - BUSCA[1]), min(H - R - 1, y + BUSCA[1])
        xa, xb = max(R, x - dxmax), min(W - R - 1, x + dxmax)
        h, w = yb - ya + 1, xb - xa + 1
        ssd = np.zeros((h, w), np.float32)
        for dy in range(k):
            for dx in range(k):
                if M[dy, dx]:
                    janela = src[ya - R + dy:ya - R + dy + h, xa - R + dx:xa - R + dx + w]
                    ssd += ((janela - P[dy, dx]) ** 2).sum(-1)
        ssd /= max(1, M.sum())
        ssd += 0.0004 * (np.arange(ya, yb + 1)[:, None] - y) ** 2
        ssd[~ok[ya:yb + 1, xa:xb + 1]] = np.inf
        j = int(np.argmin(ssd))
        return ssd.flat[j], ya + j // w, xa + j % w

    while falta.any():
        borda = falta & _morf(~falta, 1, ImageFilter.MaxFilter)
        ys, xs = np.nonzero(borda)
        cbox = _caixa(conf, R)
        cc = cbox[ys, xs]
        i = int(np.argmax(cc))
        y, x = int(ys[i]), int(xs[i])
        y = min(max(y, R), H - R - 1)
        x = min(max(x, R), W - R - 1)
        P = img[y - R:y + R + 1, x - R:x + R + 1]
        M = ~falta[y - R:y + R + 1, x - R:x + R + 1]
        # paineis do centro: so na vertical (mantem a divisoria); pano liso: busca larga
        no_centro = centro[0] <= x <= centro[1]
        dxmax = BUSCA[0] if no_centro else BUSCA_LARGA
        f1, f2 = fontes[no_centro]
        e1, sy, sx = busca(orig, f1, y, x, dxmax, P, M)
        e2, my, mx = busca(espelho, f2, y, x, dxmax, P, M)
        S = (orig[sy - R:sy + R + 1, sx - R:sx + R + 1] if e1 <= e2
             else espelho[my - R:my + R + 1, mx - R:mx + R + 1])
        novo = ~M
        img[y - R:y + R + 1, x - R:x + R + 1][novo] = S[novo]
        conf[y - R:y + R + 1, x - R:x + R + 1][novo] = cbox[y, x]
        falta[y - R:y + R + 1, x - R:x + R + 1] = False
        passos += 1
    return img, passos


def modelo(v):
    """Separa pano (tingivel) e bordado dourado:  v ~ s*cor + b  (com cor = COR_PANO devolve o banner limpo).

    O bordado prateado (brasao, paineis do centro) e da mesma cor do pano, so mais claro: fica com um pouco
    da cor (S_FIO) e o excesso de brilho vira cinza em b, assim ele acompanha a cor nova sem estourar no branco."""
    c = COR_PANO
    lum = v @ np.array([0.299, 0.587, 0.114], np.float32)
    ouro = np.clip(((v[..., 1] - v[..., 2]) - 6) / 12, 0, 1) * np.clip((lum - 22) / 16, 0, 1)
    pano = 1 - ouro
    p0 = (v @ c) / float(c @ c)
    # sombra de baixa frequencia: o banner_10 tem dobras bem mais fundas que simples/coroa (no branco viram manchas)
    liso = (pano > 0.9) & (p0 > 0.05) & (p0 < LISO_MAX)
    w = liso.astype(np.float32)
    baixa = _caixa(_caixa(p0 * w, RAIO_SOMBRA), RAIO_SOMBRA) / np.maximum(_caixa(_caixa(w, RAIO_SOMBRA), RAIO_SOMBRA), 1e-3)
    # alvo: so a variacao vertical (media por linha do pano liso), as dobras na horizontal somem
    linha = np.array([np.median(baixa[y][liso[y]]) if liso[y].sum() > 20 else np.nan for y in range(len(p0))])
    ok = ~np.isnan(linha)
    linha = np.interp(np.arange(len(linha)), np.nonzero(ok)[0], linha[ok])
    linha = np.convolve(np.pad(linha, 40, mode='edge'), np.ones(81) / 81, mode='valid')
    ganho = np.clip(linha[:, None] / np.maximum(baixa, 0.15), 0.4, 2.5) ** SOMBRA
    # a base sobe pelo ganho todo, mas o grao so pela raiz: nas dobras fundas o ganho cheio vira riscos escuros
    base = baixa * ganho
    detalhe = (p0 - baixa) * np.sqrt(ganho)
    # vaos escuros entre os fios do bordado prateado: no branco viram pontinhos pretos (sujeira), entao suaviza
    bordado = np.clip(_caixa((p0 > 1.6).astype(np.float32), 4) * 6, 0, 1)
    detalhe = np.where(detalhe < 0, detalhe * (1 - (1 - VAO_BORDADO) * bordado), detalhe)
    p = base + detalhe
    k = S_JOELHO

    def comprimir(q):
        # acima do joelho e bordado prateado: s desce devagar ate S_FIO e o resto do brilho fica em b (cinza).
        # A queda (0.25 por unidade) e menor que b sobe, entao no branco o bordado continua mais claro que o pano.
        return np.clip(np.where(q <= k, q, np.maximum(S_FIO, k - 0.25 * (q - k))), 0, None) * pano

    # b sai da sombra original (sem aplainar), senao ele devolveria as dobras
    b = v - comprimir(p0)[..., None] * c
    cinza = b.mean(-1, keepdims=True)
    b = b * (1 - pano[..., None]) + cinza * pano[..., None]   # sem o tom do pano original no excesso
    s = comprimir(p)
    return s.astype(np.float32), b.astype(np.float32)


def construir():
    rgba = np.array(Image.open(FONTE).convert('RGBA')).astype(np.float32)
    rgb, alfa = rgba[..., :3], rgba[..., 3]
    m = armas(rgb)
    x0, y0, x1, y1 = AREA
    limpo = rgb.copy()
    limpo[y0:y1, x0:x1], passos = preencher(rgb[y0:y1, x0:x1], m[y0:y1, x0:x1], alfa[y0:y1, x0:x1] > 10,
                                            _ouro(rgb)[y0:y1, x0:x1], (CENTRO_X[0] - x0, CENTRO_X[1] - x0))
    return rgb, alfa, m, limpo, passos


def salvar(limpo, alfa, m):
    s, b = modelo(limpo)
    os.makedirs(os.path.dirname(DESTINO), exist_ok=True)
    np.savez_compressed(DESTINO, s=s.astype(np.float16), b=b.astype(np.float16),
                        alfa=np.clip(alfa, 0, 255).astype(np.uint8))
    rec = np.clip(s[..., None] * COR_PANO + b, 0, 255)
    ok = (alfa > 10) & ~m
    err = np.abs(rec - limpo).mean(-1)[ok]
    print(f'escudo -> {DESTINO}\n   erro medio {err.mean():.2f}  p99 {np.percentile(err, 99):.1f}'
          f'  s p99.9 {np.percentile(s[alfa > 10], 99.9):.2f}')


if __name__ == '__main__':
    rgb, alfa, m, limpo, passos = construir()
    print('armas', int(m.sum()), 'px, passos', passos)
    salvar(limpo, alfa, m)
