"""Gerador de banners da Guilda (512x1024): so o pano colorido (borda, franja e coroa de louros ficam como no modelo), sem arma.

Estilos: simples (borda fina) e coroa (borda ornamentada). O modelo vem de assets/base/banner_<estilo>.npz
(ver tools/build_banner_template.py); o bordado tom-sobre-tom do fundo vem de bordado_<estilo>.npz
(tools/build_bordado.py) e multiplica a sombra do pano (no escudo ainda soma um brilho cinza: fio de prata). As cores sao RGB 0..255 do pano ja sombreado (vermelho de referencia ~ 64,19,19).
O padrao e o branco (135,135,135): o maximo sem estourar os brilhos do pano (sombra chega a ~1.85).
O emblema (PNG com transparencia) e opcional e vai por cima, no centro da coroa de louros. Ele vira um bordado: fio com o tile
periodico do vanilla (assets/base/fio_tile.npz, ver tools/build_fio_tile.py) e, em volta, um anel de pano limpo
(sem os louros) com halo claro e granulado, como nos banners vanilla.
"""
import os

import numpy as np
from PIL import Image, ImageFilter

from ddiconstudio import app_paths
from ddiconstudio.morfologia import dilatar_mascara, distancia_ate

LARGURA, ALTURA = 512, 1024  # resolução nativa de cada textura de banner no PAK
CENTRO = (256, 425)
ESTILOS = ("simples", "coroa", "escudo")

PALETA = {
    "branco": (135, 135, 135),
    "vermelho": (64, 19, 19), "azul": (15, 40, 52), "ocre": (60, 35, 0), "verde": (29, 36, 23),
    "carmim": (71, 0, 0), "marinho": (7, 15, 50), "roxo": (40, 5, 39), "rosa": (77, 20, 45),
    "laranja": (65, 23, 0), "cinza": (40, 40, 46), "turquesa": (8, 52, 52), "preto": (8, 8, 12),
}

# Fio (medido nos banners vanilla): tom proporcional a luz do pano, variacao aditiva e quase neutra
TOM_FIO = np.array((85.0, 73.8, 60.2), np.float32)  # RGB por unidade de sombra suave (vanilla: 105,91,74 com ~1.19)
RAIO_LUZ = 12         # janela (px) da sombra do pano que ilumina o fio
RUIDO_COMUM = 18.5    # desvio (niveis) do ruido do fio comum aos 3 canais, alem do tile
RUIDO_CANAL = (6.5, 1.5, 7.5)  # ruido independente de cada canal: o vanilla varia em R e B (G quase so segue a luminancia)
CAUDA_FIO = 0.08      # fracao de pixels com ruido dobrado (caudas pesadas: curtose ~4.5)
GRAO_FORMA = 0.045    # tremor da borda do fio (px); o vanilla tem borda quase reta
BRILHO_BORDA = (3.8, 2.7)  # niveis a mais no 1o e no 2o pixel de dentro do fio (media das direcoes do vanilla)
BISEL_BORDA = 15.0    # luz de cima/esquerda: +/-12 no pixel mais externo (esq. +18, dir. -7, topo +10, base -10 no vanilla)
LUZ_BORDA = (-0.8, -0.6)  # (x, y) de onde vem a luz do bisel
BISEL_FORA = 10.0     # o pixel de pano colado ao fio tambem pega a luz (esq. +20, topo +25, dir. +8 no vanilla)
# Contorno: pano limpo em volta do fio; no vanilla o pano e trocado de forma quase plena ate ~5 px e some ~7 px do fio
RAIO_CONTORNO = 6.6
ESPALHA_CONTORNO = 0.55   # largura da transicao (logistica)
ALCANCE_CONTORNO = 10     # alem disso o pano nao e tocado
HALO_BASE, HALO_DECLIVE = 10.5, 0.35   # halo neutro do anel: 10.5 - 0.35 d niveis
GRAO_ANEL, GRAO_QUEDA = 5.0, 0.7   # granulado do anel: GRAO_ANEL * GRAO_QUEDA^(d-2) niveis (d >= 2 px); o vanilla usa ~16, aqui mais liso
FRANJA_FIO = 0.2      # cobertura do pixel vizinho a borda do fio (antialiasing do vanilla)
RAIO_JANELA = 8     # janela para reconstruir o pano sob o desenho de louros
RAIO_FECHAMENTO = 14  # maior mancha de ouro (meia largura) que ainda conta como pano

_cache = {}
_cache_pano = {}


def _modelo(estilo):
    """Carrega s (multiplicador de sombra), b (brilho RGB) e alfa; incorpora o bordado em s/b quando o arquivo existe."""
    if estilo not in ESTILOS:
        raise ValueError(f"estilo de banner desconhecido: {estilo}")
    if estilo not in _cache:
        modelo = np.load(os.path.join(app_paths.ASSETS, "base", f"banner_{estilo}.npz"))
        sombra = modelo["s"].astype(np.float32)
        brilho = modelo["b"].astype(np.float32)
        caminho_bordado = os.path.join(app_paths.ASSETS, "base", f"bordado_{estilo}.npz")
        if os.path.exists(caminho_bordado):
            bordado = np.load(caminho_bordado)
            if "brilho" in bordado:
                # so no pano (sombra ~ 0 no ouro e na franja)
                brilho = brilho + (bordado["brilho"].astype(np.float32) * np.clip(sombra / 0.5, 0, 1))[..., None]
            sombra = sombra * (1 + bordado["mod"].astype(np.float32))
        ouro = (brilho[..., 0] > brilho[..., 1] * 1.15) & (brilho[..., 1] > brilho[..., 2] * 1.2) & (brilho[..., 0] > 16)
        brilho[..., 0][ouro] *= 1.08
        ouro_central = ouro.copy()
        ouro_central[:280] = False
        ouro_central[520:] = False
        ouro_central[:, :135] = False
        ouro_central[:, 375:] = False
        brilho[..., 1][ouro_central] += 12
        brilho[..., 2][ouro_central] += 3
        _cache[estilo] = (sombra, brilho, modelo["alfa"])
    return _cache[estilo]


def _camada_centralizada(imagem, escala, dx, dy):
    imagem = imagem.convert("RGBA")
    if escala != 1.0:
        imagem = imagem.resize(
            (max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala))), Image.LANCZOS
        )
    camada = Image.new("RGBA", (LARGURA, ALTURA), (0, 0, 0, 0))
    posicao = (round(CENTRO[0] + dx - imagem.width / 2), round(CENTRO[1] + dy - imagem.height / 2))
    camada.paste(imagem, posicao, imagem.getchannel("A"))
    return camada


def _media_janela(valores, raio):
    n_janela = 2 * raio + 1
    for eixo in (0, 1):
        preenchimento = [(0, 0), (0, 0)]
        preenchimento[eixo] = (raio + 1, raio)
        acumulada = np.cumsum(np.pad(valores, preenchimento, mode="edge"), axis=eixo, dtype=np.float64)
        n = valores.shape[eixo]
        fim = np.take(acumulada, np.arange(n_janela, n_janela + n), axis=eixo)
        inicio = np.take(acumulada, np.arange(n), axis=eixo)
        valores = ((fim - inicio) / n_janela).astype(np.float32)
    return valores


def _pano_limpo(estilo):
    """Sombra/brilho do pano sem o desenho de louros (reconstruidos pela vizinhanca) e onde o pano pode ser coberto."""
    if estilo not in _cache_pano:
        sombra, brilho, alfa = _modelo(estilo)
        buraco = dilatar_mascara(((sombra <= 0.45) | (alfa == 0)).astype(np.uint8), 2)
        valido = (np.asarray(buraco) == 0).astype(np.float32)
        sombra_limpa, brilho_limpo = sombra.copy(), brilho.copy()
        pendente = valido == 0
        for raio in (RAIO_JANELA, 3 * RAIO_JANELA):
            peso = _media_janela(valido, raio)
            divisor = np.maximum(peso, 1e-3)
            furo = pendente & (peso > 0.05)
            sombra_limpa[furo] = (_media_janela(sombra * valido, raio) / divisor)[furo]
            for c in range(3):
                brilho_limpo[..., c][furo] = (_media_janela(brilho[..., c] * valido, raio) / divisor)[furo]
            pendente &= ~furo
        # a trama fina do pano nao pode sumir onde o desenho foi reconstruido: reaproveita a de outro ponto
        local = _media_janela(sombra * valido, 3) / np.maximum(_media_janela(valido, 3), 1e-3)
        trama = np.roll((sombra - local) * valido, (23, 37), axis=(0, 1))
        preenchido = (valido == 0) & ~pendente
        sombra_limpa[preenchido] += trama[preenchido]
        # fechamento: so o pano interno pode ser coberto; a borda dourada larga fica intacta
        expandido = np.asarray(dilatar_mascara((valido * 255).astype(np.uint8), RAIO_FECHAMENTO))
        fechado = 255 - np.asarray(dilatar_mascara(255 - expandido, RAIO_FECHAMENTO))
        coberto = fechado > 127
        _cache_pano[estilo] = (sombra_limpa, brilho_limpo, coberto)
    return _cache_pano[estilo]


def _silhueta(emblema, escala, dx, dy):
    alfa = _camada_centralizada(emblema, escala, dx, dy).getchannel("A")
    return alfa.point(lambda valor: 255 if valor > 127 else 0)


def _ruido_banda(sorteio, sigma_fino, sigma_grosso, forma=(ALTURA, LARGURA)):
    """Ruido (desvio 1) com energia em periodos de poucos pixels."""
    ruido = np.fft.rfft2(sorteio.normal(0, 1, forma))
    fy = np.fft.fftfreq(forma[0])[:, None]
    fx = np.fft.rfftfreq(forma[1])[None, :]
    f2 = fx * fx + fy * fy
    filtro = np.exp(-2 * np.pi ** 2 * sigma_fino ** 2 * f2) - np.exp(-2 * np.pi ** 2 * sigma_grosso ** 2 * f2)
    campo = np.fft.irfft2(ruido * filtro, s=forma).astype(np.float32)
    return campo / campo.std()


def amostrar_tile(tile, u, v):
    """Valor do tile periodico (NB x NB) nas fases u, v em [0, 1), interpolacao bilinear com dobra nas bordas."""
    nb = tile.shape[0]
    fu, fv = u * nb, v * nb
    i0, j0 = np.floor(fu).astype(int), np.floor(fv).astype(int)
    a, b = fu - i0, fv - j0
    i0, j0 = i0 % nb, j0 % nb
    i1, j1 = (i0 + 1) % nb, (j0 + 1) % nb
    return (tile[j0, i0] * (1 - a) * (1 - b) + tile[j0, i1] * a * (1 - b)
            + tile[j1, i0] * (1 - a) * b + tile[j1, i1] * a * b)


def _textura_fio():
    """Variacao aditiva do fio (H, W, 3), ruido unitario do anel (H, W) e ruido gaussiano unitario da borda (H, W).

    O tile do vanilla se repete em coordenadas da tela (fixo, nao gira com a arma); em cima dele vai um ruido de
    caudas pesadas quase neutro entre os canais. O granulado do anel em volta do fio quase nao correlaciona com o
    tile (r ~ 0.1), entao tem ruido proprio.
    """
    if "fio" not in _cache_pano:
        dados = np.load(os.path.join(app_paths.ASSETS, "base", "fio_tile.npz"))
        tile, periodo, ganho = dados["tile"], float(dados["periodo"]), dados["ganho"]
        ys, xs = np.mgrid[0:ALTURA, 0:LARGURA].astype(np.float32)
        padrao = amostrar_tile(tile, (xs / periodo) % 1, (ys / periodo) % 1)
        sorteio = np.random.default_rng(7)
        comum = _ruido_banda(sorteio, 0.5, 1.4)
        comum = comum * (1 + (sorteio.random(comum.shape) < CAUDA_FIO))
        comum *= RUIDO_COMUM / comum.std()
        variacao = np.empty((ALTURA, LARGURA, 3), np.float32)
        for c in range(3):
            variacao[..., c] = ganho[c] * (padrao + comum) + RUIDO_CANAL[c] * _ruido_banda(sorteio, 0.5, 1.4)
        grao = sorteio.normal(0, 1, (ALTURA, LARGURA)).astype(np.float32)
        _cache_pano["fio"] = (variacao, _ruido_banda(sorteio, 0.5, 1.4), grao)
    return _cache_pano["fio"]


def _luz_fio(estilo):
    """Sombra do pano (sem louros) suavizada: no vanilla o tom do fio acompanha a luz do pano (correlacao ~0.9)."""
    chave = ("luz", estilo)
    if chave not in _cache_pano:
        _cache_pano[chave] = np.clip(_media_janela(_pano_limpo(estilo)[0], RAIO_LUZ), 0.6, 1.9)
    return _cache_pano[chave]


def _luz_na_normal(forma):
    """Componente da luz do bisel na normal externa da borda de `forma` (0..1): ~+1 voltada para a luz, ~-1 oposta."""
    suave = np.asarray(Image.fromarray((forma * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5)), np.float32)
    gy, gx = np.gradient(suave)
    return -(gx * LUZ_BORDA[0] + gy * LUZ_BORDA[1]) / np.maximum(np.hypot(gx, gy), 1e-3)


def _bordar(camada, estilo):
    """Fio bege-acinzentado: tom da luz do pano + tile periodico + ruido, com bisel claro em cima/esquerda e escuro embaixo/direita."""
    rgba = np.asarray(camada, np.float32)
    alfa = rgba[..., 3] / 255
    if not (alfa > 0.1).any():
        return camada
    variacao, _, grao = _textura_fio()
    forma = np.clip((alfa - 0.5) * 2.4 + 0.5 + GRAO_FORMA * grao, 0, 1)
    forma = np.maximum(forma, FRANJA_FIO * (distancia_ate(forma >= 0.5, 2) <= 1.5))
    dentro = distancia_ate(forma < 0.5, 3)
    luz = _luz_na_normal(forma)
    borda = (np.select([dentro <= 1.5, dentro <= 2.5], [BRILHO_BORDA[0] + BISEL_BORDA * luz,
                                                        BRILHO_BORDA[1] + 0.35 * BISEL_BORDA * luz], 0.0) * (forma > 0.5))
    cor_fio = TOM_FIO[None, None] * _luz_fio(estilo)[..., None] + variacao + borda[..., None]
    return Image.fromarray(np.dstack([np.rint(np.clip(cor_fio, 0, 255)), forma * 255]).astype(np.uint8), "RGBA")


def render(cor_a=PALETA["branco"], cor_b=None, divisao=256, estilo="simples", emblema=None, escala=1.0,
           dx=0, dy=0, contorno_escala=1.0, contorno_dx=0, contorno_dy=0):
    """Gera um banner RGBA de 512x1024.

    Cores sao tuplas RGB (0..255); `cor_b` opcional divide o pano na coluna `divisao` (px).
    `emblema` e RGBA opcional. `escala`/`dx`/`dy` posicionam o bordado (silhueta com textura de fio). O contorno e o anel
    de tecido em volta da silhueta que cobre a arte atras; `contorno_escala`/`contorno_dx`/`contorno_dy` o ajustam
    em relacao a silhueta.
    """
    sombra, brilho, alfa = _modelo(estilo)
    cor = np.empty((LARGURA, 3), np.float32)
    cor[:] = cor_a
    if cor_b is not None:
        cor[divisao:] = cor_b
    rgb = np.clip(sombra[..., None] * cor[None] + brilho, 0, 255)
    if emblema is not None:
        sombra_limpa, brilho_limpo, coberto = _pano_limpo(estilo)
        silhueta = np.asarray(_silhueta(emblema, escala * contorno_escala, dx + contorno_dx, dy + contorno_dy)) > 0
        distancia = distancia_ate(silhueta, ALCANCE_CONTORNO)
        limpo = 1 / (1 + np.exp((distancia - RAIO_CONTORNO) / ESPALHA_CONTORNO))
        limpo *= (distancia <= ALCANCE_CONTORNO) & coberto
        _, anel, _ = _textura_fio()
        queda = GRAO_QUEDA ** np.maximum(distancia - 2, 0)
        halo = np.clip(HALO_BASE - HALO_DECLIVE * distancia, 0, None) + GRAO_ANEL * queda * anel
        halo += BISEL_FORA * _luz_na_normal(silhueta) * ((distancia > 0) & (distancia <= 1.5))
        tecido = np.clip(sombra_limpa[..., None] * cor[None] + brilho_limpo + halo[..., None], 0, 255)
        rgb = rgb + (tecido - rgb) * limpo[..., None]
    img = Image.fromarray(np.dstack([rgb, alfa]).astype(np.uint8), "RGBA")
    if emblema is not None:
        img = Image.alpha_composite(img, _bordar(_camada_centralizada(emblema, escala, dx, dy), estilo))
    return img
