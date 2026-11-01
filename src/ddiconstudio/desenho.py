"""Modelo do editor de silhuetas: mascara L superamostrada, historico, geometria das ferramentas, simetria,
operacoes de forma e composicao da vista.

As coordenadas sao pixels do documento (tamanho de saida). A mascara interna tem SUPERAMOSTRA vezes esse tamanho e a
reducao na saida suaviza o serrilhado."""
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ddiconstudio.morfologia import distancia_ate

SUPERAMOSTRA = 2
LIMITE_HISTORICO = 30
TAMANHO_ICONE = (480, 480)
TAMANHO_BANNER = (512, 1024)
PONTOS_ELIPSE = 160
AMOSTRAS_CURVA = 14


# ---------- geometria (pontos do documento) ----------
def caixa(c0, c1, proporcional=False, do_centro=False):
    """Cantos (x0, y0, x1, y1) do arrasto: 1:1 opcional e/ou com c0 no centro."""
    (ax, ay), (bx, by) = c0, c1
    dx, dy = bx - ax, by - ay
    if proporcional:
        lado = max(abs(dx), abs(dy))
        dx, dy = math.copysign(lado, dx or 1), math.copysign(lado, dy or 1)
    if do_centro:
        return ax - abs(dx), ay - abs(dy), ax + abs(dx), ay + abs(dy)
    return min(ax, ax + dx), min(ay, ay + dy), max(ax, ax + dx), max(ay, ay + dy)


def elipse(x0, y0, x1, y1, n=PONTOS_ELIPSE):
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def retangulo(x0, y0, x1, y1, raio=0.0):
    raio = min(raio, (x1 - x0) / 2, (y1 - y0) / 2)
    if raio <= 0.5:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pontos = []
    for cx, cy, inicio in ((x1 - raio, y0 + raio, -90), (x1 - raio, y1 - raio, 0),
                           (x0 + raio, y1 - raio, 90), (x0 + raio, y0 + raio, 180)):
        for k in range(13):
            angulo = math.radians(inicio + 90 * k / 12)
            pontos.append((cx + raio * math.cos(angulo), cy + raio * math.sin(angulo)))
    return pontos


def estrela(centro, ponta, pontas, interno):
    """Estrela com `pontas` pontas; `interno` (0..1) e o raio dos vales; 1 vira poligono regular."""
    cx, cy = centro
    raio = math.dist(centro, ponta)
    inicio = math.atan2(ponta[1] - cy, ponta[0] - cx)
    if interno >= 0.995:
        return [(cx + raio * math.cos(inicio + 2 * math.pi * i / pontas),
                 cy + raio * math.sin(inicio + 2 * math.pi * i / pontas)) for i in range(pontas)]
    pontos = []
    for i in range(2 * pontas):
        r = raio if i % 2 == 0 else raio * interno
        angulo = inicio + math.pi * i / pontas
        pontos.append((cx + r * math.cos(angulo), cy + r * math.sin(angulo)))
    return pontos


def curva(pontos, fechada=True, amostras=AMOSTRAS_CURVA):
    """Catmull-Rom pelos pontos: a curva passa por todos os vertices clicados."""
    n = len(pontos)
    if n < 3:
        return list(pontos)
    resultado = []
    segmentos = n if fechada else n - 1
    for i in range(segmentos):
        if fechada:
            p0, p1, p2, p3 = pontos[i - 1], pontos[i], pontos[(i + 1) % n], pontos[(i + 2) % n]
        else:
            p0 = pontos[max(i - 1, 0)]
            p1, p2 = pontos[i], pontos[i + 1]
            p3 = pontos[min(i + 2, n - 1)]
        for k in range(amostras):
            t = k / amostras
            t2, t3 = t * t, t * t * t
            resultado.append(tuple(
                0.5 * (2 * p1[j] + (p2[j] - p0[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                       + (3 * p1[j] - p0[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    if not fechada:
        resultado.append(tuple(pontos[-1]))
    return resultado


def suavizar(pontos, iteracoes=2, fechada=False):
    """Chaikin: corta os cantos do traco feito a mao (estabilizador)."""
    for _ in range(iteracoes):
        if len(pontos) < 3:
            return pontos
        pares = zip(pontos, pontos[1:] + pontos[:1]) if fechada else zip(pontos, pontos[1:])
        novos = [] if fechada else [pontos[0]]
        for (ax, ay), (bx, by) in pares:
            novos += [(0.75 * ax + 0.25 * bx, 0.75 * ay + 0.25 * by), (0.25 * ax + 0.75 * bx, 0.25 * ay + 0.75 * by)]
        if not fechada:
            novos.append(pontos[-1])
        pontos = novos
    return pontos


def travar_angulo(origem, ponto, passo=15):
    angulo = math.atan2(ponto[1] - origem[1], ponto[0] - origem[0])
    angulo = math.radians(round(math.degrees(angulo) / passo) * passo)
    raio = math.dist(origem, ponto)
    return origem[0] + raio * math.cos(angulo), origem[1] + raio * math.sin(angulo)


def simetrias(modo, raios, tamanho):
    """Funcoes ponto -> ponto de cada copia; o centro da simetria e o centro do documento."""
    cx, cy = tamanho[0] / 2, tamanho[1] / 2
    copias = [lambda p: p]
    if modo in ("vertical", "ambas"):
        copias.append(lambda p: (2 * cx - p[0], p[1]))
    if modo in ("horizontal", "ambas"):
        copias.append(lambda p: (p[0], 2 * cy - p[1]))
    if modo == "ambas":
        copias.append(lambda p: (2 * cx - p[0], 2 * cy - p[1]))
    if modo == "radial":
        for k in range(1, max(2, int(raios))):
            angulo = 2 * math.pi * k / max(2, int(raios))
            c, s = math.cos(angulo), math.sin(angulo)
            copias.append(lambda p, c=c, s=s: (cx + (p[0] - cx) * c - (p[1] - cy) * s,
                                               cy + (p[0] - cx) * s + (p[1] - cy) * c))
    return copias


# ---------- documento ----------
class Desenho:
    def __init__(self, tamanho):
        self.tamanho = tuple(tamanho)
        self.mascara = Image.new("L", self._interno, 0)
        self._saida = None
        self._desfazer = []
        self._refazer = []

    @property
    def _interno(self):
        return self.tamanho[0] * SUPERAMOSTRA, self.tamanho[1] * SUPERAMOSTRA

    @property
    def pode_desfazer(self):
        return bool(self._desfazer)

    @property
    def pode_refazer(self):
        return bool(self._refazer)

    @property
    def vazio(self):
        return self.mascara.getbbox() is None

    def _mudou(self):
        self._saida = None

    def _guardar(self):
        self._desfazer.append(self.mascara.copy())
        del self._desfazer[:-LIMITE_HISTORICO]
        self._refazer.clear()

    def _trocar(self, nova):
        self._guardar()
        self.mascara = nova
        self._mudou()

    def desfazer(self):
        if self._desfazer:
            self._refazer.append(self.mascara)
            self.mascara = self._desfazer.pop()
            self._mudou()

    def refazer(self):
        if self._refazer:
            self._desfazer.append(self.mascara)
            self.mascara = self._refazer.pop()
            self._mudou()

    def limpar(self):
        if not self.vazio:
            self._trocar(Image.new("L", self._interno, 0))

    def saida(self):
        """Mascara no tamanho do documento (em cache ate a proxima mudanca)."""
        if self._saida is None:
            self._saida = self.mascara.resize(self.tamanho, Image.Resampling.BOX)
        return self._saida

    def caixa(self):
        """Caixa (x0, y0, x1, y1) do desenho em pixels do documento, ou None."""
        caixa = self.mascara.getbbox()
        return None if caixa is None else tuple(v / SUPERAMOSTRA for v in caixa)

    def resultado(self, recortar=True):
        saida = self.saida()
        caixa = saida.getbbox()
        if caixa is None:
            raise ValueError("Desenhe a silhueta antes de concluir.")
        return saida.crop(caixa) if recortar else saida.copy()

    def abrir(self, mascara, ocupacao=0.85, centro=None, manter_posicao=False):
        """Troca o desenho pela mascara: no lugar (mesmo tamanho do documento) ou recortada e centralizada."""
        if mascara.getbbox() is None:
            raise ValueError("Nenhuma silhueta encontrada na imagem.")
        if manter_posicao and mascara.size == self.tamanho:
            self._trocar(mascara.convert("L").resize(self._interno, Image.Resampling.LANCZOS))
            return
        mascara = mascara.convert("L").crop(mascara.getbbox())
        fator = min(self._interno) * ocupacao / max(mascara.size)
        tamanho = (max(1, round(mascara.width * fator)), max(1, round(mascara.height * fator)))
        mascara = mascara.resize(tamanho, Image.Resampling.LANCZOS)
        cx, cy = ((self.tamanho[0] / 2, self.tamanho[1] / 2) if centro is None else centro)
        nova = Image.new("L", self._interno, 0)
        nova.paste(mascara, (round(cx * SUPERAMOSTRA - tamanho[0] / 2), round(cy * SUPERAMOSTRA - tamanho[1] / 2)))
        self._trocar(nova)

    # ---------- pintura ----------
    @staticmethod
    def _interna(pontos):
        return [(x * SUPERAMOSTRA, y * SUPERAMOSTRA) for x, y in pontos]

    def preencher(self, poligono, apagar=False, copias=None):
        if len(poligono) < 3:
            return False
        self._guardar()
        caneta = ImageDraw.Draw(self.mascara)
        for copia in copias or [lambda p: p]:
            caneta.polygon(self._interna([copia(p) for p in poligono]), fill=0 if apagar else 255)
        self._mudou()
        return True

    def traco(self, pontos, raio, apagar=False, copias=None):
        """Traco de largura 2*raio com pontas e juntas redondas."""
        if not pontos:
            return False
        self._guardar()
        caneta = ImageDraw.Draw(self.mascara)
        cor = 0 if apagar else 255
        r = max(0.5, raio * SUPERAMOSTRA)
        for copia in copias or [lambda p: p]:
            grupo = self._interna([copia(p) for p in pontos])
            if len(grupo) > 1:
                caneta.line(grupo, fill=cor, width=max(1, round(2 * r)), joint="curve")
            for x, y in (grupo if len(grupo) < 400 else grupo[::2] + [grupo[-1]]):
                caneta.ellipse((x - r, y - r, x + r, y + r), fill=cor)
        self._mudou()
        return True

    def balde(self, ponto, apagar=False, copias=None):
        """Preenche a regiao conectada (vazia ou cheia) sob o ponto."""
        alvo = 0 if apagar else 255
        binaria = self.mascara.point(lambda v: 255 if v >= 128 else 0)
        antes = binaria.copy()
        mudou = False
        for copia in copias or [lambda p: p]:
            x, y = (round(v * SUPERAMOSTRA) for v in copia(ponto))
            if 0 <= x < binaria.width and 0 <= y < binaria.height and binaria.getpixel((x, y)) != alvo:
                ImageDraw.floodfill(binaria, (x, y), alvo)
                mudou = True
        if not mudou:
            return False
        regiao = ImageChops.difference(binaria, antes)
        nova = self.mascara.copy()
        nova.paste(alvo, mask=regiao)
        self._trocar(nova)
        return True

    # ---------- operacoes de forma ----------
    def _binaria(self):
        return np.asarray(self.mascara) >= 128

    def _de_binaria(self, ligado):
        self._trocar(Image.fromarray(np.where(ligado, 255, 0).astype(np.uint8)))

    def engrossar(self, px):
        r = max(1, round(px * SUPERAMOSTRA))
        self._de_binaria(distancia_ate(self._binaria(), r) <= r)

    def afinar(self, px):
        r = max(1, round(px * SUPERAMOSTRA))
        self._de_binaria(distancia_ate(~self._binaria(), r) > r)

    def contorno(self, px):
        """Mantem so a faixa interna de `px` da borda (silhueta vazada)."""
        r = max(1, round(px * SUPERAMOSTRA))
        ligado = self._binaria()
        self._de_binaria(ligado & (distancia_ate(~ligado, r) <= r))

    def suavizar_bordas(self, px):
        """Arredonda bordas e serrilhado: desfoque e corte no meio do tom."""
        borrada = self.mascara.filter(ImageFilter.GaussianBlur(max(0.5, px * SUPERAMOSTRA)))
        self._trocar(borrada.point(lambda v: 255 if v >= 128 else 0))

    def tapar_furos(self):
        ligado = self._binaria()
        moldura = Image.fromarray(np.pad(np.where(ligado, 255, 0).astype(np.uint8), 1))
        ImageDraw.floodfill(moldura, (0, 0), 128)
        furos = np.asarray(moldura)[1:-1, 1:-1] == 0
        if furos.any():
            self._de_binaria(ligado | furos)

    def inverter(self):
        """Inverte dentro da caixa do desenho (o fundo de fora continua vazio)."""
        caixa = self.mascara.getbbox()
        if caixa is None:
            return
        nova = self.mascara.copy()
        nova.paste(ImageChops.invert(self.mascara.crop(caixa)), caixa)
        self._trocar(nova)

    # ---------- transformacoes ----------
    def _centro_desenho(self):
        caixa = self.mascara.getbbox()
        if caixa is None:
            return None
        return (caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2

    def _afim(self, a, b, c, d, e, f):
        """Saida(x, y) = entrada(a x + b y + c, d x + e y + f), em pixels internos."""
        self._trocar(self.mascara.transform(self.mascara.size, Image.Transform.AFFINE, (a, b, c, d, e, f),
                                            resample=Image.Resampling.BICUBIC, fillcolor=0))

    def mover(self, dx, dy):
        if abs(dx) + abs(dy) >= 1 / SUPERAMOSTRA and not self.vazio:
            self._afim(1, 0, -dx * SUPERAMOSTRA, 0, 1, -dy * SUPERAMOSTRA)

    def espelhar(self, horizontal=True):
        caixa = self.mascara.getbbox()
        if caixa is None:
            return
        regiao = self.mascara.crop(caixa).transpose(
            Image.Transpose.FLIP_LEFT_RIGHT if horizontal else Image.Transpose.FLIP_TOP_BOTTOM)
        nova = self.mascara.copy()
        nova.paste(regiao, caixa)
        self._trocar(nova)

    def girar(self, graus):
        """Gira no sentido horario em volta do centro do desenho."""
        centro = self._centro_desenho()
        if centro is None or not graus % 360:
            return
        self._trocar(self.mascara.rotate(-graus, resample=Image.Resampling.BICUBIC, center=centro, fillcolor=0))

    def escalar(self, fator):
        centro = self._centro_desenho()
        if centro is None or fator <= 0 or fator == 1:
            return
        cx, cy = centro
        self._afim(1 / fator, 0, cx - cx / fator, 0, 1 / fator, cy - cy / fator)

    def centralizar(self, centro=None):
        caixa = self.caixa()
        if caixa is None:
            return
        cx, cy = (self.tamanho[0] / 2, self.tamanho[1] / 2) if centro is None else centro
        self.mover(cx - (caixa[0] + caixa[2]) / 2, cy - (caixa[1] + caixa[3]) / 2)

    def ajustar(self, ocupacao=0.85, centro=None):
        """Escala e centraliza o desenho para ocupar `ocupacao` do menor lado do documento."""
        if not self.vazio:
            self.abrir(self.mascara, ocupacao, centro)


# ---------- vista ----------
class Vista:
    """Zoom e origem (canto superior esquerdo visivel, em pixels do documento) de uma tela de `tamanho` px."""

    def __init__(self, tamanho_tela, tamanho_doc):
        self.tela = tamanho_tela
        self.doc = tamanho_doc
        self.ajustar()

    @property
    def zoom_ajuste(self):
        return min(self.tela[0] / self.doc[0], self.tela[1] / self.doc[1]) * 0.96

    def ajustar(self):
        self.zoom = self.zoom_ajuste
        self.origem = (self.doc[0] / 2 - self.tela[0] / (2 * self.zoom),
                       self.doc[1] / 2 - self.tela[1] / (2 * self.zoom))

    def para_doc(self, ponto):
        return self.origem[0] + ponto[0] / self.zoom, self.origem[1] + ponto[1] / self.zoom

    def para_tela(self, ponto):
        return (ponto[0] - self.origem[0]) * self.zoom, (ponto[1] - self.origem[1]) * self.zoom

    def ampliar(self, fator, ancora=None):
        ancora = ancora or (self.tela[0] / 2, self.tela[1] / 2)
        fixo = self.para_doc(ancora)
        self.zoom = min(max(self.zoom * fator, self.zoom_ajuste * 0.25), 32.0)
        self.origem = (fixo[0] - ancora[0] / self.zoom, fixo[1] - ancora[1] / self.zoom)

    def deslocar(self, dx_tela, dy_tela):
        self.origem = (self.origem[0] - dx_tela / self.zoom, self.origem[1] - dy_tela / self.zoom)


_reduzidas = {}


def _na_vista(imagem, escala, vista, reamostrar=Image.Resampling.BILINEAR):
    """Recorte da `imagem` (escala px por px do documento) visivel na vista; reduz antes se a vista estiver longe."""
    passo = max(1, int(escala / vista.zoom))
    if passo > 1:
        chave = (id(imagem), passo)
        if chave not in _reduzidas or _reduzidas[chave][0] is not imagem:
            if len(_reduzidas) > 16:
                _reduzidas.clear()
            _reduzidas[chave] = (imagem, imagem.reduce(passo))
        imagem = _reduzidas[chave][1]
        escala /= passo
    a = escala / vista.zoom
    vazio = 0 if imagem.mode == "L" else (0, 0, 0, 0)
    return imagem.transform(vista.tela, Image.Transform.AFFINE,
                            (a, 0, vista.origem[0] * escala, 0, a, vista.origem[1] * escala),
                            resample=reamostrar, fillcolor=vazio)


def compor_vista(desenho, vista, fundo_fora, fundo, tinta, alfa_tinta=1.0, camadas=()):
    """RGBA da tela: fundo do documento, camadas de apoio (RGBA do tamanho do documento, opacidade) e a tinta."""
    imagem = Image.new("RGBA", vista.tela, fundo_fora)
    x0, y0 = vista.para_tela((0, 0))
    x1, y1 = vista.para_tela(desenho.tamanho)
    ImageDraw.Draw(imagem).rectangle((round(x0), round(y0), round(x1) - 1, round(y1) - 1), fill=fundo)
    for camada, opacidade in camadas:
        if camada is None or opacidade <= 0:
            continue
        visivel = _na_vista(camada, 1, vista)
        if opacidade < 1:
            visivel.putalpha(visivel.getchannel("A").point(lambda v: round(v * opacidade)))
        imagem.alpha_composite(visivel)
    escala = SUPERAMOSTRA
    fonte = desenho.mascara
    if vista.zoom < SUPERAMOSTRA:
        fonte, escala = desenho.saida(), 1
    tinta_visivel = _na_vista(fonte, escala, vista)
    if alfa_tinta < 1:
        tinta_visivel = tinta_visivel.point(lambda v: round(v * alfa_tinta))
    imagem.paste(tinta, mask=tinta_visivel)
    return imagem
