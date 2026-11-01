"""Gera assets/base/Vanilla_Icons.pak: PAK base sem nenhuma arte do VSB.

Mantem so a estrutura que o montar_pak espera (folhas 1..9 e UVS_job_01 da lista, mais o manifesto). As folhas saem
transparentes e o UVS usa a grade 4x4 exata; so as folhas editadas no DDIconStudio recebem arte. Os icones vanilla
(numeros 0..15) continuam na folha original do jogo, que este PAK nao toca.
Uso: python tools/build_base_vanilla.py [pak_vsb_de_origem]
"""
import os
import sys

import numpy as np
import zstandard

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(RAIZ, "src"))
from ddiconstudio import app_paths, pak_builder, uvs_ext  # noqa: E402
from ddiconstudio.bc7 import codificar  # noqa: E402
from ddiconstudio.pak_format import _checksum_dados, _gravar_pak, _ler_pak  # noqa: E402

ORIGEM_PADRAO = os.path.join(app_paths.ASSETS, "base", "Vanilla_Icons.pak")
DESTINO = os.path.join(app_paths.ASSETS, "base", "Vanilla_Icons.pak")


def main(origem):
    with open(origem, "rb") as arquivo:
        cabecalho, arquivos = _ler_pak(arquivo.read())
    largura, altura = pak_builder.LARGURA_FOLHA_LISTA, pak_builder.ALTURA_FOLHA_LISTA
    vazia = uvs_ext.cabecalho_tex(largura, altura) + codificar(np.zeros((altura, largura, 4), np.uint8))
    if len(vazia) != pak_builder.TAMANHO_TEX_FOLHA:
        raise ValueError("Tamanho da folha vazia diferente do esperado.")
    for hash_folha in pak_builder.HASH_FOLHAS.values():
        if hash_folha in arquivos:
            arquivos[hash_folha]["dados"] = vazia

    entrada = arquivos[pak_builder.HASH_UVS_LISTA]
    with open(app_paths.UVS_MODELO, "rb") as arquivo:
        uvs = bytearray(arquivo.read())
    pak_builder._ajustar_grade_do_uvs(uvs, sorted(pak_builder.HASH_FOLHAS))
    dados_uvs = bytes(uvs)
    entrada.update(dados=zstandard.ZstdCompressor(level=5).compress(dados_uvs), decomp=len(dados_uvs), attr=2,
                   chk=_checksum_dados(dados_uvs))

    with open(DESTINO, "wb") as arquivo:
        arquivo.write(_gravar_pak(cabecalho, arquivos))
    print(f"gravado: {DESTINO}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ORIGEM_PADRAO)
