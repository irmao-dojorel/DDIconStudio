"""Render a Guild-panel weapon silhouette as a textured brass glyph."""
import zlib

import numpy as np
from PIL import Image

LADO_GLIFO = 128
ALTURA_GLIFO, LARGURA_GLIFO = 88, 74
GRAO_GLIFO = 2
COR_LATAO = np.array([136.0, 116.0, 86.0])
RUIDO_GLIFO = 0.10
MANCHA_GLIFO = 0.12
MATIZ_GLIFO = 0.05
FERRUGEM_GLIFO = 0.02
PONTOS_CLAROS_GLIFO = 0.02
REALCE_BORDA_GLIFO = 4.0
REALCE_BORDA_LUZ_GLIFO = 110.0
DESLOCAMENTO_SOMBRA_GLIFO = 1
SIGMA_Y_SOMBRA_GLIFO = 2.25
SIGMA_X_SOMBRA_GLIFO = 2.0
GANHO_SOMBRA_GLIFO = 3.0
DIRECAO_SOMBRA_GLIFO = 0.06
LIMIAR_FORMA_GLIFO = 0.4
COR_SOMBRA_GLIFO = np.array([
    (2, 85, 64, 45), (4, 58, 30, 19), (6, 58, 29, 14), (8, 60, 26, 9), (10, 60, 9, 5), (12, 40, 5, 3),
], np.float32)
CANAIS_SOMBRA_GLIFO = np.array([1.10, 1.02, 0.88])


def _distancia_ate(alvo, maximo):
    """Distancia euclidiana ate o pixel alvo mais proximo, limitada por `maximo`."""
    altura, largura = alvo.shape
    preenchida = np.pad(alvo, maximo)
    melhor = np.full(alvo.shape, maximo + 1.0, np.float32)
    for dy in range(-maximo, maximo + 1):
        for dx in range(-maximo, maximo + 1):
            distancia = float(np.hypot(dy, dx))
            if distancia > maximo:
                continue
            vizinho = preenchida[maximo + dy:maximo + dy + altura, maximo + dx:maximo + dx + largura]
            melhor = np.where(vizinho & (distancia < melhor), distancia, melhor).astype(np.float32)
    return melhor


def _desfocar_matriz(matriz, sigma, sigma_x=None):
    """Desfoque gaussiano separavel com desvios independentes nos eixos."""
    for eixo, desvio in ((0, sigma), (1, sigma if sigma_x is None else sigma_x)):
        raio = max(1, int(round(3 * desvio)))
        pesos = np.exp(-0.5 * (np.arange(-raio, raio + 1) / desvio) ** 2)
        pesos /= pesos.sum()
        matriz = np.apply_along_axis(lambda linha: np.convolve(np.pad(linha, raio, mode='edge'), pesos, 'valid'),
                                     eixo, matriz)
    return matriz


def _textura_latao(forma, gerador):
    metade = (forma.shape[0] // GRAO_GLIFO, forma.shape[1] // GRAO_GLIFO)

    def ampliar(matriz):
        return np.repeat(np.repeat(matriz, GRAO_GLIFO, 0), GRAO_GLIFO, 1)

    mancha = _desfocar_matriz(gerador.normal(0, 1, metade), 1.2)
    mancha /= max(float(mancha.std()), 1e-6)
    matiz = _desfocar_matriz(gerador.normal(0, 1, metade), 1.0)
    matiz /= max(float(matiz.std()), 1e-6)
    ruido = ampliar(gerador.normal(0, 1, metade))
    cor = COR_LATAO * (1 + RUIDO_GLIFO * ruido + MANCHA_GLIFO * ampliar(mancha))[..., None]
    cor = cor * (1 + MATIZ_GLIFO * ampliar(matiz)[..., None] * (-0.7, 0.5, -0.3))
    sorteio = ampliar(gerador.random(metade))
    cor = np.where((sorteio < FERRUGEM_GLIFO)[..., None], cor * (0.75, 0.5, 0.45), cor)
    cor = np.where((sorteio > 1 - PONTOS_CLAROS_GLIFO)[..., None], cor + (40, 36, 24), cor)

    suave = _desfocar_matriz(forma.astype(np.float32), 0.8 * GRAO_GLIFO)
    gradiente_y, gradiente_x = np.gradient(suave)
    modulo = np.maximum(np.hypot(gradiente_x, gradiente_y), 1e-6)
    voltada_luz = (gradiente_x + gradiente_y) / (np.sqrt(2) * modulo)
    profundidade = _distancia_ate(~forma, 2 * GRAO_GLIFO)
    peso_borda = np.where(profundidade <= GRAO_GLIFO, 1.0, np.where(profundidade <= 2 * GRAO_GLIFO, 0.3, 0.0))
    realce = peso_borda * (REALCE_BORDA_GLIFO + REALCE_BORDA_LUZ_GLIFO * np.maximum(voltada_luz, 0))
    return cor + realce[..., None] * (1.0, 0.95, 0.78)


def _sombra_latao(forma):
    pequena = forma[::GRAO_GLIFO, ::GRAO_GLIFO]
    deslocada = np.pad(pequena, ((DESLOCAMENTO_SOMBRA_GLIFO, 0), (0, 0)))[:pequena.shape[0]].astype(np.float32)
    espalhada = _desfocar_matriz(deslocada, SIGMA_Y_SOMBRA_GLIFO, SIGMA_X_SOMBRA_GLIFO)
    alfa = 1 - np.exp(-GANHO_SOMBRA_GLIFO * espalhada)
    maximo = int(COR_SOMBRA_GLIFO[-1, 0])
    distancia = _distancia_ate(pequena, maximo // GRAO_GLIFO + 1) * GRAO_GLIFO
    acima, lado, abaixo = (np.interp(distancia, COR_SOMBRA_GLIFO[:, 0], COR_SOMBRA_GLIFO[:, coluna]) for coluna in (1, 2, 3))
    posicao = np.clip((espalhada - _desfocar_matriz(pequena.astype(np.float32), SIGMA_Y_SOMBRA_GLIFO,
                                                    SIGMA_X_SOMBRA_GLIFO)) / DIRECAO_SOMBRA_GLIFO, -1, 1)
    cinza = np.where(posicao < 0, lado - posicao * (acima - lado), lado + posicao * (abaixo - lado))
    cor = cinza[..., None] * CANAIS_SOMBRA_GLIFO

    def ampliar(matriz):
        return np.repeat(np.repeat(matriz, GRAO_GLIFO, 0), GRAO_GLIFO, 1)

    return ampliar(alfa), ampliar(cor)


def _glifo_latao(forma):
    gerador = np.random.default_rng(zlib.crc32(np.ascontiguousarray(forma).tobytes()))
    rgb = _textura_latao(forma, gerador)
    alfa_sombra, cor_sombra = _sombra_latao(forma)
    alfa = np.where(forma, 255.0, alfa_sombra * 255)
    rgb = np.where(forma[..., None], rgb, cor_sombra)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), alfa]).astype(np.uint8), 'RGBA')


def render(mascara, tamanho=LADO_GLIFO):
    """Converte uma mascara L em glifo de latao com sombra, centralizado na celula 128x128."""
    caixa = mascara.point(lambda valor: 255 if valor > 24 else 0).getbbox()
    if not caixa:
        return None
    alfa = mascara.crop(caixa)
    escala = min(ALTURA_GLIFO / alfa.height, LARGURA_GLIFO / alfa.width)
    alfa = alfa.resize((max(1, round(alfa.width * escala)), max(1, round(alfa.height * escala))), Image.LANCZOS)
    cobertura = np.zeros((LADO_GLIFO, LADO_GLIFO), np.float32)
    topo, esquerda = (LADO_GLIFO - alfa.height) // 2, (LADO_GLIFO - alfa.width) // 2
    cobertura[topo:topo + alfa.height, esquerda:esquerda + alfa.width] = np.asarray(alfa) / 255.0
    blocos = cobertura.reshape(LADO_GLIFO // GRAO_GLIFO, GRAO_GLIFO, LADO_GLIFO // GRAO_GLIFO, GRAO_GLIFO).mean((1, 3))
    forma = np.repeat(np.repeat(blocos >= LIMIAR_FORMA_GLIFO, GRAO_GLIFO, 0), GRAO_GLIFO, 1)
    glifo = _glifo_latao(forma)
    return glifo if tamanho == LADO_GLIFO else glifo.resize((tamanho, tamanho), Image.LANCZOS)