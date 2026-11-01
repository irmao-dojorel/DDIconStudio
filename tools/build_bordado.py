"""Redesenha o bordado tom-sobre-tom do fundo dos banners e grava assets\\base\\bordado_<estilo>.npz (chave 'mod').

Nos banners vanilla o pano tem um bordado bem fraco (grade de 3 colunas: arcos com medalhao, losangos de nos,
faixas de cordao entre as fileiras). Todos os banners usam o mesmo tecido, entao nao da para limpar o desenho
pela media; aqui ele e redesenhado em vetor (4x supersample) seguindo o mesmo layout, simetrico em x=255.

banner_gen aplica  s *= 1 + mod  (so muda o pano; ouro/prata do modelo ficam iguais).
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))
from ddiconstudio import app_paths  # noqa: E402

W, H = 512, 1024
SS = 4                            # supersample do desenho
EIXO = 255.0                      # eixo de simetria do pano vanilla (x -> 2*EIXO - x)
CONT = 0.9                        # largura do contorno escuro de cada fio (px)

# grade (simples/coroa): 3 colunas de paineis, passo 86.5 como no vanilla
COLUNAS = (EIXO - 86.5, EIXO, EIXO + 86.5)
PAINEL_L = 78.0
GRADE_X = (EIXO - 130.0, EIXO + 130.0)
FAIXA_H = 24.0
ARCO_H, LOSANGO_H = 96.0, 76.0
FAIXA_Y0 = 142.0                  # primeira faixa de cordao (no vanilla: 140-168, 242-268, 455-476, 558-590)

# relevo: fio claro, contorno escuro, luz de cima/esquerda
FIO, SULCO, RELEVO = 0.064, 0.08, 0.04


class Tela:
    """Duas camadas em supersample: fio (linha bordada) e sulco (contorno). Cada fio novo apaga o que passa por
    baixo dele (fica 'por cima'), entao a ordem de desenho faz o entrelacado."""

    def __init__(self, x0=0, y0=0, w=W, h=H):
        self.x0, self.y0 = x0, y0
        self.fio = Image.new('L', (w * SS, h * SS), 0)
        self.sulco = Image.new('L', (w * SS, h * SS), 0)
        self.df, self.ds = ImageDraw.Draw(self.fio), ImageDraw.Draw(self.sulco)

    def p(self, x, y):
        return ((x - self.x0) * SS, (y - self.y0) * SS)

    def _tres(self, fn, w):
        larg = (w + 2 * CONT) * SS
        fn(self.df, 0, round(larg))
        fn(self.ds, 255, round(larg))
        fn(self.df, 255, max(1, round(w * SS)))

    def linha(self, pts, w=1.6, fechada=False):
        pts = [self.p(x, y) for x, y in pts]
        if fechada:
            pts = pts + pts[:2]
        self._tres(lambda d, c, lw: d.line(pts, fill=c, width=lw, joint='curve'), w)

    def elipse(self, cx, cy, rx, ry, w=1.6, ang=0.0):
        if ang == 0.0:
            box = [*self.p(cx - rx, cy - ry), *self.p(cx + rx, cy + ry)]
            self._tres(lambda d, c, lw: d.ellipse(box, outline=c, width=lw), w)
            return
        a = math.radians(ang)
        pts = [(cx + rx * math.cos(t) * math.cos(a) - ry * math.sin(t) * math.sin(a),
                cy + rx * math.cos(t) * math.sin(a) + ry * math.sin(t) * math.cos(a))
               for t in np.linspace(0, 2 * math.pi, 40)]
        self.linha(pts, w, fechada=True)

    def arco(self, cx, cy, r, a0, a1, w=1.6, passos=48):
        pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
               for a in np.linspace(a0, a1, passos)]
        self.linha(pts, w)

    def ponto(self, cx, cy, r):
        box = [*self.p(cx - r, cy - r), *self.p(cx + r, cy + r)]
        self.ds.ellipse([box[0] - CONT * SS, box[1] - CONT * SS, box[2] + CONT * SS, box[3] + CONT * SS], fill=255)
        self.df.ellipse(box, fill=255)

    def mapas(self):
        f = np.asarray(self.fio.resize((self.fio.width // SS, self.fio.height // SS), Image.BOX), np.float32) / 255
        s = np.asarray(self.sulco.resize((self.fio.width // SS, self.fio.height // SS), Image.BOX), np.float32) / 255
        return f, np.clip(s - f, 0, 1)


# ---------------------------------------------------------------- motivos

def moldura(t, x0, y0, x1, y1):
    t.linha([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], 1.5, fechada=True)
    t.linha([(x0 + 4, y0 + 4), (x1 - 4, y0 + 4), (x1 - 4, y1 - 4), (x0 + 4, y1 - 4)], 0.9, fechada=True)
    for x, y in ((x0 + 2, y0 + 2), (x1 - 2, y0 + 2), (x1 - 2, y1 - 2), (x0 + 2, y1 - 2)):
        t.ponto(x, y, 1.6)


def trevo(t, cx, cy, r, ang):
    """Folhinha de tres lobulos apontando para 'ang' (graus)."""
    for da in (-50, 0, 50):
        a = math.radians(ang + da)
        t.elipse(cx + r * math.cos(a), cy + r * math.sin(a), r * 0.62, r * 0.62, 1.0)
    t.ponto(cx, cy, r * 0.45)


def trama(t, topo, e1, e2, n=4, w=1.5):
    """Trancado celta dentro do losango topo + a*e1 + b*e2 (a, b em 0..1): n fios em cada direcao, alternando
    por cima/por baixo em cada cruzamento."""
    def ponto(a, b):
        return (topo[0] + a * e1[0] + b * e2[0], topo[1] + a * e1[1] + b * e2[1])
    us = [(i + 0.5) / n for i in range(n)]
    for b in us:                                  # fios na direcao e1
        t.linha([ponto(0.04, b), ponto(0.96, b)], w)
    for a in us:                                  # fios na direcao e2 (por cima de todos)
        t.linha([ponto(a, 0.04), ponto(a, 0.96)], w)
    meio = 0.42 / n
    for i, a in enumerate(us):                    # metade dos cruzamentos volta a ficar por cima o fio e1
        for j, b in enumerate(us):
            if (i + j) % 2 == 0:
                t.linha([ponto(a - meio, b), ponto(a + meio, b)], w)


def painel_losango(t, cx, y0, y1):
    x0, x1 = cx - PAINEL_L / 2, cx + PAINEL_L / 2
    cy = (y0 + y1) / 2
    moldura(t, x0, y0, x1, y1)
    rx, ry = PAINEL_L / 2 - 9, (y1 - y0) / 2 - 9
    t.linha([(cx, cy - ry), (cx + rx, cy), (cx, cy + ry), (cx - rx, cy)], 1.8, fechada=True)
    k = 0.80
    topo = (cx, cy - ry * k)
    trama(t, topo, (rx * k, ry * k), (-rx * k, ry * k), 4, 1.5)
    # cantos
    for sx in (-1, 1):
        for sy in (-1, 1):
            trevo(t, cx + sx * (rx - 6), cy + sy * (ry - 5), 4.0, math.degrees(math.atan2(-sy, -sx)))


def painel_arco(t, cx, y0, y1):
    x0, x1 = cx - PAINEL_L / 2, cx + PAINEL_L / 2
    moldura(t, x0, y0, x1, y1)
    r = PAINEL_L / 2 - 9
    topo = y0 + 9 + r
    base = y1 - 9
    # janela em arco
    t.arco(cx, topo, r, 180, 360, 1.8)
    t.linha([(cx - r, topo), (cx - r, base), (cx + r, base), (cx + r, topo)], 1.8)
    # medalhao com quadrifolio entrelacado
    my = (topo + base) / 2 + 2
    rm = min(r - 6, (base - topo) / 2 + 4)
    t.elipse(cx, my, rm, rm, 1.7)
    q = rm * 0.42
    for dx, dy in ((0, -q), (q, 0), (0, q), (-q, 0)):
        t.elipse(cx + dx, my + dy, q * 0.95, q * 0.95, 1.3)
    t.elipse(cx, my, rm * 0.22, rm * 0.22, 1.1)
    t.ponto(cx, my, 1.4)
    # folhas nos cantos de cima (fora do arco) e base
    for sx in (-1, 1):
        trevo(t, cx + sx * (r - 3), y0 + 12, 3.6, 90 if sx > 0 else 90)
        t.ponto(cx + sx * (r - 4), base - 5, 1.6)
    t.arco(cx, topo, r - 5, 200, 340, 0.9)


def faixa(t, y0, y1):
    """Faixa de cordao trancado entre as fileiras."""
    xa, xb = GRADE_X
    t.linha([(xa, y0 + 3), (xb, y0 + 3)], 1.2)
    t.linha([(xa, y1 - 3), (xb, y1 - 3)], 1.2)
    cy = (y0 + y1) / 2
    passo = 5.0
    n = int((xb - xa - 10) / passo)
    x = EIXO - n / 2 * passo
    for _ in range(n + 1):                       # cordao torcido: gomos inclinados encavalados
        t.elipse(x, cy, 5.2, 2.6, 1.1, ang=-55)
        x += passo


def grade():
    t = Tela()
    xa, xb = GRADE_X
    seq = []
    tipos = ('arco', 'losango')
    yy, k = FAIXA_Y0, 0
    while yy > -100:
        tipo = tipos[k % 2]
        h = ARCO_H if tipo == 'arco' else LOSANGO_H
        seq.append((tipo, yy - h, yy))
        yy -= h + FAIXA_H
        seq.append(('faixa', yy, yy + FAIXA_H))
        k += 1
    y, k = FAIXA_Y0 + FAIXA_H, 1
    seq.append(('faixa', FAIXA_Y0, FAIXA_Y0 + FAIXA_H))
    while y < H:
        tipo = tipos[k % 2]
        h = ARCO_H if tipo == 'arco' else LOSANGO_H
        seq.append((tipo, y, y + h))
        seq.append(('faixa', y + h, y + h + FAIXA_H))
        y += h + FAIXA_H
        k += 1
    for tipo, y0, y1 in seq:
        if tipo == 'faixa':
            faixa(t, y0, y1)
            continue
        for cx in COLUNAS:
            (painel_arco if tipo == 'arco' else painel_losango)(t, cx, y0 + 2, y1 - 2)
    # bordas verticais da grade
    for x in (xa, xb):
        t.linha([(x, -10), (x, H + 10)], 1.4)
        t.linha([(x + (4 if x == xa else -4), -10), (x + (4 if x == xa else -4), H + 10)], 0.9)
    return t.mapas()


# ---------------------------------------------------------------- relevo

def _desloca(a, dx, dy):
    return np.roll(np.roll(a, dy, 0), dx, 1)


def _suave(a, r=1):
    p = np.pad(a, r, mode='edge')
    out = np.zeros_like(a)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out += p[r + dy:r + dy + a.shape[0], r + dx:r + dx + a.shape[1]]
    return out / (2 * r + 1) ** 2


def relevo(fio, sulco):
    """mod = fio claro - sulco escuro + relevo (luz de cima/esquerda), simetrico em x=EIXO."""
    alt = fio - 0.6 * sulco
    luz = alt - _desloca(alt, 1, 1)                  # borda de cima/esquerda clara, de baixo/direita escura
    mod = FIO * fio - SULCO * sulco + RELEVO * _suave(luz, 1)
    return mod.astype(np.float32)


def salvar(nome, mod, brilho=None):
    caminho = os.path.join(app_paths.ASSETS, 'base', f'bordado_{nome}.npz')
    dados = {'mod': mod.astype(np.float16)}
    if brilho is not None:
        dados['brilho'] = brilho.astype(np.float16)
    np.savez_compressed(caminho, **dados)
    print(f'{nome} -> {caminho}  mod {mod.min():+.2f}..{mod.max():+.2f}')


def main():
    fio, sulco = grade()
    mod = relevo(fio, sulco)
    for nome in ('simples', 'coroa'):
        salvar(nome, mod)


if __name__ == '__main__':
    main()
