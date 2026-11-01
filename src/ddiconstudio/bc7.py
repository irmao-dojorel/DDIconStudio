"""BC7 mode 6 texture encoding and decoding."""
import io
import struct

import numpy as np
from PIL import Image

PESOS_INTERPOLACAO_4BITS = np.array([0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64], np.int64)
BLOCOS_POR_LOTE = 2048
LARGURA_PADRAO, ALTURA_PADRAO = 800, 800


def _bits(valores, quantidade_bits):
    """Expande os bits menos significativos de cada valor na ordem de serializacao BC7."""
    return (valores[:, None] >> np.arange(quantidade_bits)) & 1


def _suavizar_cor_dos_transparentes(pixels):
    """Usa a media dos pixels opacos nos canais RGB transparentes, sem alterar o alfa."""
    opacos = pixels[:, :, 3] > 0
    quantidade_opacos = opacos.sum(1)
    cor_media = (pixels[:, :, :3] * opacos[:, :, None]).sum(1) // np.maximum(quantidade_opacos, 1)[:, None]
    bloco_misto = (quantidade_opacos > 0) & (quantidade_opacos < 16)
    transparentes = bloco_misto[:, None] & ~opacos
    pixels[:, :, :3] = np.where(transparentes[:, :, None], cor_media[:, None, :], pixels[:, :, :3])


def _eixo_principal(pixels_centralizados):
    """Direcao de maior variacao das cores de cada bloco, por iteracao de potencia."""
    quantidade_blocos = len(pixels_centralizados)
    covariancia = np.einsum("nia,nib->nab", pixels_centralizados, pixels_centralizados)
    eixo = np.ones((quantidade_blocos, 4))
    for _ in range(8):
        proximo_eixo = np.einsum("nab,nb->na", covariancia, eixo)
        comprimento = np.sqrt((proximo_eixo * proximo_eixo).sum(1))
        eixo_valido = comprimento >= 1e-9
        eixo = np.where(eixo_valido[:, None], proximo_eixo / np.where(eixo_valido, comprimento, 1.0)[:, None], eixo)
    return eixo


def _quantizar_extremo(extremo, quantidade_blocos):
    """Quantiza um extremo RGBA para 7 bits por canal mais o bit P de menor erro."""
    melhor = None
    for bit_p in (0, 1):
        quantizado = np.minimum((extremo - bit_p + 1) // 2, 127)
        reconstruido = quantizado * 2 + bit_p
        erro = ((reconstruido - extremo) ** 2).sum(1)
        if melhor is None:
            melhor = [quantizado, reconstruido, np.full(quantidade_blocos, bit_p, np.int64), erro]
        else:
            melhorou = erro < melhor[3]
            melhor = [np.where(melhorou[:, None], quantizado, melhor[0]), np.where(melhorou[:, None], reconstruido, melhor[1]),
                      np.where(melhorou, bit_p, melhor[2]), np.where(melhorou, erro, melhor[3])]
    return melhor[0], melhor[1], melhor[2]


def _codificar_blocos(blocos_pixels):
    """Codifica blocos RGBA `(quantidade, 16, 4)` em BC7 modo 6."""
    quantidade_blocos = len(blocos_pixels)
    pixels = blocos_pixels.astype(np.int64)
    _suavizar_cor_dos_transparentes(pixels)

    pixels_centralizados = pixels - pixels.mean(1)[:, None, :]
    eixo = _eixo_principal(pixels_centralizados)
    projecao = np.einsum("nia,na->ni", pixels_centralizados, eixo)
    indices_blocos = np.arange(quantidade_blocos)
    quantizados, reconstruidos, bits_p = [], [], []
    for extremo in (pixels[indices_blocos, projecao.argmin(1)], pixels[indices_blocos, projecao.argmax(1)]):
        quantizado, reconstruido, bit_p = _quantizar_extremo(extremo, quantidade_blocos)
        quantizados.append(quantizado)
        reconstruidos.append(reconstruido)
        bits_p.append(bit_p)

    paleta = ((64 - PESOS_INTERPOLACAO_4BITS)[None, :, None] * reconstruidos[0][:, None, :]
              + PESOS_INTERPOLACAO_4BITS[None, :, None] * reconstruidos[1][:, None, :] + 32) >> 6
    indices = (((paleta[:, None, :, :] - pixels[:, :, None, :]) ** 2).sum(-1)).argmin(2)
    trocar_extremos = indices[:, 0] >= 8
    quantizado_0 = np.where(trocar_extremos[:, None], quantizados[1], quantizados[0])
    quantizado_1 = np.where(trocar_extremos[:, None], quantizados[0], quantizados[1])
    bit_p_0 = np.where(trocar_extremos, bits_p[1], bits_p[0])
    bit_p_1 = np.where(trocar_extremos, bits_p[0], bits_p[1])
    indices = np.where(trocar_extremos[:, None], 15 - indices, indices)

    campos = [_bits(np.full(quantidade_blocos, 0x40, np.int64), 7)]
    for canal in range(4):
        campos += [_bits(quantizado_0[:, canal], 7), _bits(quantizado_1[:, canal], 7)]
    campos += [_bits(bit_p_0, 1), _bits(bit_p_1, 1), _bits(indices[:, 0], 3)]
    campos += [_bits(indices[:, indice], 4) for indice in range(1, 16)]
    return np.packbits(np.concatenate(campos, 1).astype(np.uint8), axis=1, bitorder="little")


def codificar(rgba):
    """Converte RGBA `(altura, largura, 4)` em bytes BC7 com pitch alinhado a 256 bytes."""
    altura, largura = rgba.shape[:2]
    blocos_alto, blocos_largo = altura // 4, largura // 4
    pitch = (blocos_largo * 16 + 255) & ~255
    blocos = rgba.reshape(blocos_alto, 4, blocos_largo, 4, 4).transpose(0, 2, 1, 3, 4).reshape(blocos_alto * blocos_largo, 16, 4)
    codificado = np.empty((blocos_alto * blocos_largo, 16), np.uint8)
    for inicio in range(0, len(blocos), BLOCOS_POR_LOTE):
        codificado[inicio:inicio + BLOCOS_POR_LOTE] = _codificar_blocos(blocos[inicio:inicio + BLOCOS_POR_LOTE])
    linhas = np.zeros((blocos_alto, pitch), np.uint8)
    linhas[:, :blocos_largo * 16] = codificado.reshape(blocos_alto, blocos_largo * 16)
    return linhas.tobytes()


def decodificar(dados, largura=LARGURA_PADRAO, altura=ALTURA_PADRAO):
    """Decodifica bytes BC7 via cabecalho DDS e o decodificador do Pillow."""
    pitch = ((largura // 4) * 16 + 255) & ~255
    linhas = b"".join(dados[linha * pitch:linha * pitch + largura // 4 * 16] for linha in range(altura // 4))
    cabecalho = b"DDS " + struct.pack("<7I", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, altura, largura, len(linhas), 0, 1)
    cabecalho += b"\0" * 44 + struct.pack("<2I4s5I", 32, 4, b"DX10", 0, 0, 0, 0, 0) + struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    cabecalho += struct.pack("<5I", 98, 3, 0, 1, 0)
    return Image.open(io.BytesIO(cabecalho + linhas)).convert("RGBA")