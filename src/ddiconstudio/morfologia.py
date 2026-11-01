"""Operacoes morfologicas rapidas sobre mascaras: dilatacao quadrada (L) e distancia euclidiana limitada."""
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image


def dilatar_mascara(mascara, raio):
    valores = np.asarray(mascara)
    tamanho = 2 * raio + 1
    for eixo in (1, 0):
        preenchimento = [(0, 0), (0, 0)]
        preenchimento[eixo] = (raio, raio)
        preenchida = np.pad(valores, preenchimento, mode="constant", constant_values=0)
        valores = sliding_window_view(preenchida, tamanho, axis=eixo).max(axis=-1)
    return Image.fromarray(valores)


def distancia_ate(mascara, maximo):
    """Distancia euclidiana (px) de cada pixel ate o pixel ligado mais proximo; 0 nos ligados e `maximo + 1` alem do alcance.

    Exata: distancia horizontal ate `maximo`, depois minimo vertical de g^2 + dy^2. So processa a caixa da mascara
    ampliada em `maximo`.
    """
    ligado = np.asarray(mascara, bool)
    longe = maximo + 1
    resultado = np.full(ligado.shape, float(longe), np.float32)
    linhas, colunas = np.nonzero(ligado.any(1))[0], np.nonzero(ligado.any(0))[0]
    if not len(linhas):
        return resultado
    y0, y1 = max(linhas[0] - maximo, 0), min(linhas[-1] + maximo + 1, ligado.shape[0])
    x0, x1 = max(colunas[0] - maximo, 0), min(colunas[-1] + maximo + 1, ligado.shape[1])
    recorte = ligado[y0:y1, x0:x1]
    horizontal = np.where(recorte, 0, longe).astype(np.int32)
    for k in range(1, maximo + 1):
        vizinho = np.zeros_like(recorte)
        vizinho[:, k:] |= recorte[:, :-k]
        vizinho[:, :-k] |= recorte[:, k:]
        np.minimum(horizontal, np.where(vizinho, k, longe), out=horizontal)
    quadrado = horizontal * horizontal
    melhor = np.full(recorte.shape, longe * longe, np.int32)
    altura = recorte.shape[0]
    for dy in range(-maximo, maximo + 1):
        a, b = max(0, -dy), min(altura, altura - dy)
        if a < b:
            np.minimum(melhor[a:b], quadrado[a + dy:b + dy] + dy * dy, out=melhor[a:b])
    resultado[y0:y1, x0:x1] = np.sqrt(np.minimum(melhor, longe * longe))
    return resultado
