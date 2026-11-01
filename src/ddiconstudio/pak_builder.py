"""Monta o DDCore_Icons.pak: folhas de icones (BC7) sobre o PAK base vanilla, sem arte do VSB (KPKA 4.2) e as folhas do painel direito da Guilda.

Numero do icone = folha*16 + quadro (grade 4x4). Lista da Guilda: folhas 800x800 de celulas de 200 px (UVS_job_01.uvs).
Painel direito: folhas 512x512 de celulas de 128 px com o desenho da arma (UVS_ui040101.uvs estendido, mesmo numero).

Ordem do trabalho em montar_pak: ler o PAK base -> trocar as folhas da lista -> ajustar o UVS da lista
-> criar as folhas do painel -> criar os banners -> gravar o PAK novo e o relatorio.
"""
import os
import struct

import numpy as np
import zstandard
from PIL import Image

from ddiconstudio import app_paths
from ddiconstudio import uvs_ext
from ddiconstudio.bc7 import codificar, decodificar
from ddiconstudio.pak_format import _checksum_dados, _gravar_pak, _ler_pak, _novo_arquivo
from ddiconstudio.pak_textures import (
    ALTURA_FOLHA_LISTA, ALTURA_FOLHA_PAINEL, LADO_CELULA_LISTA, LARGURA_FOLHA_LISTA, LARGURA_FOLHA_PAINEL, _psnr, montar_folha, montar_folha_painel,
)

ICONE_MIN, ICONE_MAX = 16, 85   # mesmo intervalo dos banners (70 itens); folhas 1..5 do PAK do VSB, 16 icones cada
TAMANHO_CABECALHO_TEX = 56
TAMANHO_TEX_FOLHA = 665656   # 56 bytes de cabecalho + 200 linhas de blocos com pitch alinhado de 3328 bytes
PAINEL_DIR = "Gui/ui04/ui0401/"
PAINEL_UVS = "natives/stm/" + PAINEL_DIR + "UVS_ui040101.uvs.8"
BANNER_UVS = "natives/stm/" + PAINEL_DIR + "UVS_ui040102.uvs.8"
BANNER_LARGURA, BANNER_ALTURA = 512, 1024
BANNER_PRIMEIRA_SEQUENCIA = 16    # os banners custom usam a sequencia igual ao numero do icone (16..85)
BANNER_MIN, BANNER_MAX = ICONE_MIN, ICONE_MAX   # banner n = icone n (16..85): 70 banners
HASH_FOLHAS = {
    1: "83798D5B37A82DF0", 2: "F003691DAE4EB781", 3: "238D8EFFE06CE315", 4: "7EC420DB76B34469", 5: "60145D92D603B7E8",
    6: "3E39D23389A0F585", 7: "D7F1A5D662750504", 8: "3513AC4604295017", 9: "21EF8C0EC312CBFB",
}
HASH_UVS_LISTA = "D76F4EECCD99FE97"
UVS_ASSINATURA = b".SVU"
def _ajustar_grade_do_uvs(dados_uvs, numeros_das_folhas):
    """Ajusta para uma grade 4x4 exata os patterns das folhas editadas pelo PAK. Devolve quantos valores mudaram.

    O UVS do VSB usa altura de 99% em algumas folhas; esta correção iguala as folhas novas à sequência vanilla.
    """
    inicio_dos_patterns = struct.unpack_from("<Q", dados_uvs, 0x28)[0]
    valores_alterados = 0
    for folha in numeros_das_folhas:
        for quadro in range(16):
            u0, v0 = (quadro % 4) * 0.25, (quadro // 4) * 0.25
            novo = (u0, v0, u0 + 0.25, v0 + 0.25)
            posicao_do_pattern = inicio_dos_patterns + (folha * 16 + quadro) * 32 + 8
            valores_alterados += sum(antigo != atual for antigo, atual
                                     in zip(struct.unpack_from("<4f", dados_uvs, posicao_do_pattern), novo))
            struct.pack_into("<4f", dados_uvs, posicao_do_pattern, *novo)
    return valores_alterados


def _atualizar_folhas_da_lista(arquivos, icones, saida, relatorio, log):
    """Codifica as folhas da lista que tem icones e troca os pixels delas no PAK. Devolve os numeros das folhas."""
    folhas = sorted({numero // 16 for numero in icones})
    for folha in folhas:
        entrada = arquivos.get(HASH_FOLHAS.get(folha, ""))
        if entrada is None:
            raise ValueError(f"Folha {folha} nao esta no PAK base.")
        if entrada["attr"] != 0 or len(entrada["dados"]) != TAMANHO_TEX_FOLHA:
            raise ValueError(f"Entrada da folha {folha} inesperada (comprimida ou de outro tamanho).")
        log(f"Folha {folha}: codificando BC7...")
        imagem = montar_folha(folha, icones)
        dados = codificar(np.asarray(imagem, np.uint8))
        if len(dados) + TAMANHO_CABECALHO_TEX != TAMANHO_TEX_FOLHA:
            raise ValueError("Tamanho da folha diferente do original.")
        entrada["dados"] = entrada["dados"][:TAMANHO_CABECALHO_TEX] + dados   # o cabecalho original fica
        previa = decodificar(dados)
        previa.save(os.path.join(saida, f"preview_sheet_{folha}.png"))
        numeros = ",".join(str(numero) for numero in sorted(icones) if numero // 16 == folha)
        relatorio.append(f"folha {folha}: icones {numeros}; psnr {_psnr(imagem, previa):.1f} dB")
    return folhas


def _atualizar_uvs_da_lista(arquivos, folhas, uvs_modelo, relatorio):
    """Troca o UVS da lista (UVS_job_01) pelo modelo com a grade 4x4 exata nas folhas montadas."""
    entrada = arquivos.get(HASH_UVS_LISTA)
    if entrada is None:
        raise ValueError("UVS_job_01.uvs nao esta no PAK base.")
    with open(uvs_modelo, "rb") as arquivo:
        uvs = bytearray(arquivo.read())
    if len(uvs) != entrada["decomp"] or uvs[:4] != UVS_ASSINATURA:
        raise ValueError("UVS modelo diferente do UVS do PAK base.")
    valores_alterados = _ajustar_grade_do_uvs(uvs, folhas)
    dados_uvs = bytes(uvs)
    entrada.update(
        dados=zstandard.ZstdCompressor(level=5).compress(dados_uvs),
        decomp=len(dados_uvs),
        attr=2,
        chk=_checksum_dados(dados_uvs),
    )
    relatorio.append(f"uvs: {valores_alterados} valores de UV ajustados para a grade exata 25% nas folhas montadas")


def _montar_painel(arquivos, glifos, uvs_painel, saida, relatorio, log):
    """Uma textura BC7 512x512 por folha de glifos e o UVS_ui040101 estendido (numero n = folha*16 + quadro)."""
    validos = {numero: glifo for numero, glifo in glifos.items() if ICONE_MIN <= numero <= ICONE_MAX}
    if not validos:
        mensagem = f"painel: nenhum glifo com numero valido ({ICONE_MIN}..{ICONE_MAX})"
        relatorio.append(mensagem)
        log(mensagem)
        return
    ultima_folha = max(numero // 16 for numero in validos)
    caminhos = []
    for folha in range(1, ultima_folha + 1):
        log(f"Painel, folha {folha}: codificando BC7...")
        imagem = montar_folha_painel(folha, validos)
        dados = codificar(np.asarray(imagem, np.uint8))
        caminho = f"{PAINEL_DIR}VBS_cus_pnl_ico_sheet_{folha}.tex"
        nome, entrada = _novo_arquivo(f"natives/stm/{caminho}.{uvs_ext.TEX_VERSION}",
                                      uvs_ext.cabecalho_tex(LARGURA_FOLHA_PAINEL, ALTURA_FOLHA_PAINEL) + dados)
        arquivos[nome] = entrada
        caminhos.append(caminho)
        previa = decodificar(dados, LARGURA_FOLHA_PAINEL, ALTURA_FOLHA_PAINEL)
        previa.save(os.path.join(saida, f"preview_painel_{folha}.png"))
        numeros = ",".join(str(numero) for numero in sorted(validos) if numero // 16 == folha) or "(vazia)"
        relatorio.append(f"painel, folha {folha}: desenhos {numeros}; psnr {_psnr(imagem, previa):.1f} dB")
    with open(uvs_painel, "rb") as arquivo:
        uvs_base = arquivo.read()
    nome, entrada = _novo_arquivo(PAINEL_UVS, uvs_ext.estender_uvs(uvs_base, caminhos))
    arquivos[nome] = entrada
    relatorio.append(f"uvs do painel: {len(caminhos)} sequencias novas (numero n = folha*16 + quadro, como na lista)")


def _montar_banners(arquivos, banners, uvs_banner, saida, relatorio, log):
    """Uma textura BC7 512x1024 por banner e o UVS_ui040102 estendido: a sequencia n mostra o banner do icone n.
    Sequencias 10..15 (sem icone) e numeros sem arquivo repetem o proximo banner; depois do ultimo, repetem o ultimo."""
    validos = {numero: imagem for numero, imagem in banners.items() if BANNER_MIN <= numero <= BANNER_MAX}
    if not validos:
        relatorio.append(f"banners: nenhum numero valido ({BANNER_MIN}..{BANNER_MAX})")
        return
    caminhos = {}
    for numero in sorted(validos):
        log(f"Banner {numero}: codificando BC7...")
        imagem = validos[numero].convert("RGBA")
        if imagem.size != (BANNER_LARGURA, BANNER_ALTURA):
            imagem = imagem.resize((BANNER_LARGURA, BANNER_ALTURA), Image.LANCZOS)
        dados = codificar(np.asarray(imagem, np.uint8))
        caminho = f"{PAINEL_DIR}VBS_cus_banner_{numero}.tex"
        nome, entrada = _novo_arquivo(f"natives/stm/{caminho}.{uvs_ext.TEX_VERSION}",
                                      uvs_ext.cabecalho_tex(BANNER_LARGURA, BANNER_ALTURA) + dados)
        arquivos[nome] = entrada
        caminhos[numero] = caminho
        previa = decodificar(dados, BANNER_LARGURA, BANNER_ALTURA)
        previa.save(os.path.join(saida, f"preview_banner_{numero}.png"))
        relatorio.append(f"banner {numero}: psnr {_psnr(imagem, previa):.1f} dB")
    ultima_sequencia = BANNER_MAX
    with open(uvs_banner, "rb") as arquivo:
        uvs_base = arquivo.read()
    sequencias_base = uvs_ext.ler_uvs(uvs_base)
    quantidade_base = sequencias_base[0]
    if quantidade_base > BANNER_PRIMEIRA_SEQUENCIA:
        raise ValueError("UVS de banner ja possui sequencias customizadas.")
    caminhos_sequencia = [sequencias_base[3][-1]] * (BANNER_PRIMEIRA_SEQUENCIA - quantidade_base)
    caminhos_sequencia.extend(
        caminhos.get(numero) or caminhos[min((c for c in caminhos if c > numero), default=max(caminhos))]
        for numero in range(BANNER_PRIMEIRA_SEQUENCIA, ultima_sequencia + 1)
    )
    nome, entrada = _novo_arquivo(
        BANNER_UVS,
        uvs_ext.estender_uvs(uvs_base, caminhos_sequencia, celulas=1),
    )
    arquivos[nome] = entrada
    with open(os.path.join(saida, "banners.json"), "w", encoding="utf-8") as arquivo:
        arquivo.write('{"count": %d}\n' % (ultima_sequencia + 1))
    relatorio.append(f"uvs dos banners: sequencias {BANNER_PRIMEIRA_SEQUENCIA}..{ultima_sequencia} (numero = icone; sem arquivo repete o proximo); "
                     f"banners.json: count {ultima_sequencia + 1}")


def _gravar_pak_e_relatorio(cabecalho, arquivos, saida, relatorio, log):
    """Escreve DDCore_Icons.pak e report.txt na pasta de saida e devolve o caminho do PAK."""
    destino = os.path.join(saida, "DDCore_Icons.pak")
    pak = _gravar_pak(cabecalho, arquivos)
    with open(destino, "wb") as arquivo:
        arquivo.write(pak)
    relatorio.append(f"pak: {destino} ({len(pak)} bytes, {len(arquivos)} arquivos)")
    relatorio.append("Folhas sem PNG ficam vazias, como no PAK base (vanilla). Instale este PAK e reinicie o jogo.")
    with open(os.path.join(saida, "report.txt"), "w", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(relatorio) + "\n")
    for linha in relatorio:
        log(linha)
    return destino


def montar_pak(icones, saida, base_pak=None, uvs_modelo=None, manter_uvs=False, glifos=None, uvs_painel=None, banners=None,
               uvs_banner=None, log=print):
    """Grava saida\\DDCore_Icons.pak, preview_sheet_N.png e report.txt. Devolve o caminho do PAK.

    base_pak, uvs_modelo, uvs_painel e uvs_banner substituem os assets padrao; manter_uvs=True preserva o UVS da lista.
    glifos: numero -> imagem do desenho da arma para o painel direito (as folhas do painel so entram no PAK se houver glifos).
    banners: numero (16..85) -> imagem 512x1024 do banner da Guilda (estende o UVS_ui040102; numero = o do icone = UVSequenceNo).
    Tambem grava previews das folhas geradas; se houver banners validos, grava banners.json com a contagem de sequencias.
    """
    if not icones and not banners:
        raise ValueError("Nenhum icone nem banner para montar.")
    base_pak = base_pak or app_paths.BASE_PAK
    uvs_modelo = uvs_modelo or app_paths.UVS_MODELO
    uvs_painel = uvs_painel or app_paths.UVS_PAINEL
    uvs_banner = uvs_banner or app_paths.UVS_BANNER
    os.makedirs(saida, exist_ok=True)
    with open(base_pak, "rb") as arquivo:
        cabecalho, arquivos = _ler_pak(arquivo.read())

    relatorio = []
    folhas = _atualizar_folhas_da_lista(arquivos, icones, saida, relatorio, log)
    if not manter_uvs:
        _atualizar_uvs_da_lista(arquivos, folhas, uvs_modelo, relatorio)

    if glifos:
        _montar_painel(arquivos, glifos, uvs_painel, saida, relatorio, log)
    else:
        relatorio.append("painel: sem desenhos de arma, o painel direito nao recebe folhas novas")

    if banners:
        _montar_banners(arquivos, banners, uvs_banner, saida, relatorio, log)

    return _gravar_pak_e_relatorio(cabecalho, arquivos, saida, relatorio, log)
