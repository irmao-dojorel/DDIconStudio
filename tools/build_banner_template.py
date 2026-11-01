"""Gera assets/base/banner_<estilo>.npz a partir dos banners vanilla (referencias/banners/banner_01..09.png).

Os 9 banners do jogo dividem o mesmo pano, moldura, franja e coroa de louros; so mudam a cor do pano e a arma bordada.
Em cada pixel, cada banner k segue  v_k = s * cor_k + b  (s = sombra do pano, b = bordado/moldura que nao tinge).
O ajuste usa so os banners sem arma naquele pixel, entao o resultado sai sem armas e identico ao vanilla no resto.
Na coluna central quase todos tem arma: ali o modelo e copiado do vizinho que melhor explica os banners limpos
(casamento de patch), reajustado a eles e tem as manchas de cor de baixa frequencia removidas.

Estilos: simples = moldura fina (banners 1-4); coroa = moldura com filetes dourados extras (banners 5-9).
Saida (512x1024): s (sombra), b (RGB que nao tinge), alfa (silhueta + esmaecimento do topo).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

AQUI = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(AQUI, "..", "referencias", "banners")
BASE = os.path.join(AQUI, "..", "assets", "base")
W, H = 512, 1024
DIV = 256
GRUPOS = {"simples": (1, 2, 3, 4), "coroa": (5, 6, 7, 8, 9)}
DIVIDIDOS = (7, 8, 9)
TODOS = tuple(range(1, 10))
LUM = np.array([0.299, 0.587, 0.114], np.float32)


def _carregar():
    v, a = [], []
    for n in TODOS:
        im = np.asarray(Image.open(os.path.join(REF, f"banner_{n:02d}.png")).convert("RGBA"), np.float32)
        v.append(im[..., :3])
        a.append(im[..., 3])
    return np.stack(v), np.stack(a)


def _cores(v):
    """(K, W, 3): cor do pano por coluna (banners divididos tem esquerda/direita)."""
    esq = np.median(v[:, 560:700, 150:200].reshape(len(v), -1, 3), axis=1)
    dir_ = np.median(v[:, 560:700, 312:362].reshape(len(v), -1, 3), axis=1)
    div = np.array([n in DIVIDIDOS for n in TODOS])
    luz = np.median((esq[~div] @ LUM) / np.maximum(dir_[~div] @ LUM, 1.0))   # a direita do pano e mais escura (iluminacao)
    dir_ = np.where(div[:, None], dir_ * luz, esq)
    c = np.empty((len(v), W, 3), np.float32)
    c[:, :DIV] = esq[:, None]
    c[:, DIV:] = dir_[:, None]
    return c


def _dilatar(m, tam):
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(tam))) > 0


def _armas(v, c):
    """True onde o banner tem arma bordada (prata neutra, clara) dentro da area do emblema; o ouro (R >> B) fica de fora."""
    lum = v @ LUM
    sat = (v.max(-1) - v.min(-1)) / np.maximum(v.max(-1), 1.0)
    clum = (c @ LUM)[:, None, :]
    prata = (sat < 0.24) & ((v[..., 0] - v[..., 2]) < 0.16 * np.maximum(lum, 1.0) + 8)
    m = prata & (lum > np.maximum(1.8 * clum, 50))
    caixa = np.zeros((H, W), bool)
    caixa[150:700, 100:412] = True
    m &= caixa
    return np.stack([_dilatar(x, 13) for x in m])


def _ajustar(v, c, w, prior=None, ls=0.0, lb=0.0):
    """Minimos quadrados ponderados por pixel: v_k = s * c_k + b.
    prior=(s0, b0) puxa s/b para s0/b0 com pesos ls/lb: decide os pixels com poucos banners sem arma."""
    C = np.broadcast_to(c[:, None], v.shape)
    wk = w[..., None]
    ws = w.sum(0)
    Sc = (wk * C).sum(0)
    Sv = (wk * v).sum(0)
    Scc = (wk * C * C).sum((0, 3))
    Scv = (wk * C * v).sum((0, 3))
    if prior is None:
        s0, b0, ls, lb = np.zeros_like(ws), np.zeros_like(Sv), 0.0, 0.0
    else:
        s0, b0 = prior
    q = ws + lb + 1e-6
    den = Scc - (Sc * Sc).sum(-1) / q
    num = Scv - ((Sc * Sv).sum(-1) + lb * (Sc * b0).sum(-1)) / q + ls * s0
    s = np.clip(num / np.maximum(den + ls, 1e-3), 0.0, 3.0)    # sombra negativa nao existe: vira cor invertida
    b = (Sv - s[..., None] * Sc + lb * b0) / q[..., None]
    return s, b, ws, den


def _robusto(v, c, w, voltas=3, limiar=10.0, minimo=3, **kw):
    for _ in range(voltas):
        s, b, _, _ = _ajustar(v, c, w, **kw)
        r = np.abs(v - (s[None, ..., None] * c[:, None] + b[None])).mean(-1)
        fora = np.stack([_dilatar(x, 5) for x in (r > limiar)])
        w2 = w * (~fora)
        ok = w2.sum(0) >= minimo                # nao deixa o pixel ficar com menos banners que isso
        w = np.where(ok[None], w2, w)
    return _ajustar(v, c, w, **kw)


def _caixa(x, r, eixo):
    x = np.moveaxis(x, eixo, 0)
    p = np.concatenate([np.repeat(x[:1], r + 1, 0), x, np.repeat(x[-1:], r, 0)])
    cs = np.cumsum(p, 0, dtype=np.float64)
    return np.moveaxis(((cs[2 * r + 1:] - cs[:-2 * r - 1]) / (2 * r + 1)).astype(np.float32), 0, eixo)


def _blur(x, raio):
    r = max(1, int(round(raio)))
    for _ in range(3):
        x = _caixa(_caixa(x, r, 0), r, 1)
    return x


def _preencher(campo, conhecido):
    campo = campo.copy()
    k = conhecido.astype(np.float32)
    for raio in (1.5, 3, 6, 12, 24, 48):
        if k.min() > 0:
            break
        kb = _blur(k, raio)
        vb = _blur(campo * k[..., None], raio)
        novo = (k == 0) & (kb > 0.05)
        campo = np.where(novo[..., None], vb / np.maximum(kb, 1e-6)[..., None], campo)
        k = np.where(kb > 0.05, 1.0, k).astype(np.float32)
    return campo


def _inpaint(v, c, w, s, b, confiavel, caixa=(150, 700, 100, 412), raio=(12, 32), janela=3):
    """Pixels pouco determinados (quase todos os banners tem arma ali) copiam s/b do pixel confiavel vizinho cujo
    modelo melhor reproduz os banners sem arma em volta (casamento de patch so com as observacoes limpas)."""
    y0, y1, x0, x1 = caixa
    ry, rx = raio
    m = janela
    Y0, Y1, X0, X1 = y0 - ry - m, y1 + ry + m, x0 - rx - m, x1 + rx + m
    pred = s[None, Y0:Y1, X0:X1, None] * c[:, None, X0:X1] + b[None, Y0:Y1, X0:X1]
    conf = confiavel[Y0:Y1, X0:X1]
    sl = (slice(None), slice(ry + m, ry + m + y1 - y0), slice(rx + m, rx + m + x1 - x0))
    obs = v[:, Y0:Y1, X0:X1][sl]
    wk = w[:, Y0:Y1, X0:X1][sl]
    alvo = ~conf[sl[1:]]
    hh, ww = alvo.shape
    peso = _caixa(_caixa(wk.sum(0), m, 0), m, 1)
    melhor = np.full((hh, ww), np.inf, np.float32)
    best = np.zeros((hh, ww, 2), np.int32)
    for dy in range(-ry, ry + 1):
        for dx in range(-rx, rx + 1):
            if dy == 0 and dx == 0:
                continue
            ys = slice(ry + m + dy, ry + m + dy + hh)
            xs = slice(rx + m + dx, rx + m + dx + ww)
            d = (wk * ((obs - pred[:, ys, xs]) ** 2).sum(-1)).sum(0)
            e = _caixa(_caixa(d, m, 0), m, 1) / np.maximum(peso, 1e-3) + 0.02 * (dy * dy + dx * dx)
            e = np.where(conf[ys, xs], e, np.inf)
            troca = e < melhor
            melhor = np.where(troca, e, melhor)
            best[troca] = (dy, dx)
    yy, xx = np.nonzero(alvo)
    qy = yy + y0 + best[yy, xx, 0]
    qx = xx + x0 + best[yy, xx, 1]
    ok = np.isfinite(melhor[yy, xx])
    s, b = s.copy(), b.copy()
    s[yy[ok] + y0, xx[ok] + x0] = s[qy[ok], qx[ok]]
    b[yy[ok] + y0, xx[ok] + x0] = b[qy[ok], qx[ok]]
    refeito = np.zeros(s.shape, bool)
    refeito[y0:y1, x0:x1] = alvo
    return s, b, refeito, int((~ok).sum())


def _harmonizar(s, b, forte, raio=6):
    """Tira manchas de cor de baixa frequencia onde o ajuste tem poucos banners: a media local do b do pano (fora do
    bordado) e trocada pela interpolada das areas bem determinadas; a textura fina e o bordado ficam."""
    pano = (b @ LUM) < 20
    def media(x, m):
        k = _blur(m.astype(np.float32), raio)
        return _blur(x * m[..., None], raio) / np.maximum(k, 1e-6)[..., None], k
    lp_cur, k_cur = media(b, pano)
    lp_ref, k_ref = media(b, pano & forte)
    lp_ref = _preencher(lp_ref, k_ref > 0.3)
    alfa = np.clip(1.0 - _blur(forte.astype(np.float32), raio), 0, 1) * (k_cur > 0.05)
    caixa = np.zeros(forte.shape, np.float32)
    caixa[150:700, 100:412] = 1.0
    alfa *= _blur(caixa, raio)
    return s, b + alfa[..., None] * (lp_ref - lp_cur)


def _limpar_pontos(s, b, fraco, raio=4):
    """Nas areas fracas (poucos banners), corta picos de sombra e tira a cor do b do pano: no pano claro (branco)
    esses ruidos viram pontos brilhantes/ciano."""
    mu = _blur(s, raio)
    sd = np.sqrt(np.maximum(_blur((s - mu) ** 2, raio), 0))
    s2 = np.minimum(s, mu + 2.0 * sd)
    pano = ((b @ LUM) < 20)[..., None]
    cinza = b.mean(-1, keepdims=True)
    b2 = np.where(pano, cinza + 0.3 * (b - cinza), b)
    f = fraco[..., None]
    return np.where(fraco, s2, s), np.where(f, b2, b)


def construir():
    v, a = _carregar()
    c = _cores(v)
    limpo = (~_armas(v, c)).astype(np.float32)
    dividido = np.array([n in DIVIDIDOS for n in TODOS])
    limpo[dividido, :, DIV - 5:DIV + 5] = 0          # emenda das duas cores: nao serve de amostra
    for _ in range(2):                               # recalibra as cores pelo proprio ajuste (sombra da direita != 1)
        s0, b0, _, _ = _robusto(v[~dividido], c[~dividido], limpo[~dividido])
        for k in range(len(TODOS)):
            for lado, (x0, x1) in ((0, (150, 200)), (1, (312, 362))):
                reg = (slice(560, 700), slice(x0, x1))
                est = np.median(((v[k][reg] - b0[reg]) / np.maximum(s0[reg], 0.2)[..., None]).reshape(-1, 3), axis=0)
                if lado == 0:
                    c[k, :DIV] = est
                elif dividido[k]:
                    c[k, DIV:] = est
                else:
                    c[k, DIV:] = c[k, 0]
    # 1) ajuste com todos os 9 banners; onde quase todos tem arma (coluna central) o ajuste e mal condicionado
    s_all, b_all, n_all, den_all = _robusto(v, c, limpo)
    confiavel = (n_all >= 4) & (den_all > 1200)
    # 2) esses pixels copiam o modelo do vizinho confiavel que melhor explica os banners sem arma ali
    s_cp, b_cp, refeito, n_sem = _inpaint(v, c, limpo, s_all, b_all, confiavel)
    # 3) e voltam a ser ajustados aos banners sem arma, presos a copia (s quase fixo, b livre o bastante p/ o ouro)
    ls = 0.5 * float(np.mean((c * c).sum(-1)))
    s_rf, b_rf, _, _ = _ajustar(v, c, limpo, prior=(s_cp, b_cp), ls=ls, lb=0.5)
    s_all = np.where(refeito, s_rf, s_all)
    b_all = np.where(refeito[..., None], b_rf, b_all)
    print(f"inpaint: {int(refeito.sum())} px refeitos ({n_sem} sem candidato)")
    s_all, b_all = _harmonizar(s_all, b_all, n_all >= 6.5)
    fraco = np.zeros(refeito.shape, bool)
    fraco[150:700, 100:412] = True
    fraco &= _dilatar(refeito | (n_all < 6.5), 5)
    s_all, b_all = _limpar_pontos(s_all, b_all, fraco)
    for estilo, grupo in GRUPOS.items():
        idx = [n - 1 for n in grupo]
        # 3) o grupo so manda onde todos os banners dele estao limpos (moldura/filetes); transicao suave
        s_g, b_g, n_g, den_g = _robusto(v[idx], c[idx], limpo[idx])
        usa = _blur(((n_g >= len(idx) - 0.5) & (den_g > 500) & ~refeito).astype(np.float32), 2)
        usa = np.where(refeito, 0.0, usa)
        s = usa * s_g + (1 - usa) * s_all
        b = usa[..., None] * b_g + (1 - usa[..., None]) * b_all
        valido = confiavel | refeito
        campo = np.dstack([s, b]).astype(np.float32)
        alfa = np.median(a[idx], axis=0)
        destino = os.path.join(BASE, f"banner_{estilo}.npz")
        os.makedirs(BASE, exist_ok=True)
        np.savez_compressed(destino, s=campo[..., 0].astype(np.float16), b=campo[..., 1:].astype(np.float16),
                            alfa=np.clip(alfa, 0, 255).astype(np.uint8), div=np.int32(DIV))
        print(f"{estilo}: banners {grupo}, buracos preenchidos {int((~valido).sum())} px -> {os.path.abspath(destino)}")
        for n, k in zip(grupo, idx):
            rec = np.clip(campo[..., :1] * c[k][None] + campo[..., 1:], 0, 255)
            err = np.abs(rec - v[k]).mean(-1)[limpo[k] > 0]
            print(f"   banner_{n:02d}: erro medio {err.mean():.2f}  p99 {np.percentile(err, 99):.1f}")
    print("cores do pano (esq | dir):")
    for n in TODOS:
        print(f"   banner_{n:02d}: {c[n - 1, 0].round().astype(int).tolist()} | {c[n - 1, -1].round().astype(int).tolist()}")


if __name__ == "__main__":
    construir()
    sys.exit(0)
