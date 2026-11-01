"""Read and write KPKA PAK containers and their hashed entries."""
import struct

import xxhash

from ddiconstudio import uvs_ext


def _ler_pak(pak):
    """Devolve (cabecalho de 16 bytes, {nome_hex: dict(baixo, alto, attr, chk, decomp, dados)})."""
    if pak[:4] != b"KPKA":
        raise ValueError("Nao e um PAK (KPKA).")
    arquivos = {}
    for numero in range(struct.unpack_from("<I", pak, 8)[0]):
        posicao_entrada = 16 + numero * 48
        baixo, alto, deslocamento, tamanho_comprimido, decomp, attr, chk = struct.unpack_from("<IIQQQQQ", pak, posicao_entrada)
        arquivos[f"{alto:08X}{baixo:08X}"] = dict(baixo=baixo, alto=alto, attr=attr, chk=chk, decomp=decomp,
                                                  dados=bytes(pak[deslocamento:deslocamento + tamanho_comprimido]))
    return bytes(pak[:16]), arquivos


def _gravar_pak(cabecalho, arquivos):
    """Remonta o PAK com tabela de entradas e dados concatenados."""
    cabecalho_novo = bytearray(cabecalho)
    struct.pack_into("<I", cabecalho_novo, 8, len(arquivos))
    inicio_dos_dados = 16 + 48 * len(arquivos)
    tabela, dados_concatenados = bytearray(), bytearray()
    for arquivo in arquivos.values():
        tabela += struct.pack("<IIQQQQQ", arquivo["baixo"], arquivo["alto"], inicio_dos_dados + len(dados_concatenados),
                              len(arquivo["dados"]), arquivo["decomp"], arquivo["attr"], arquivo["chk"])
        dados_concatenados += arquivo["dados"]
    return bytes(cabecalho_novo) + bytes(tabela) + bytes(dados_concatenados)


def _novo_arquivo(caminho, dados):
    """Cria uma entrada sem compressao para um caminho novo no PAK."""
    baixo, alto = uvs_ext.hash_nome(caminho)
    return f"{alto:08X}{baixo:08X}", dict(baixo=baixo, alto=alto, attr=0, chk=0, decomp=len(dados), dados=dados)


def _checksum_dados(dados):
    hash_64 = xxhash.xxh64(dados, seed=0xFFFFFFFF).intdigest()
    return xxhash.xxh32(hash_64.to_bytes(8, "little"), seed=0xFFFFFFFF).intdigest()