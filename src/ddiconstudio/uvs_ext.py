"""Formato .uvs (UVSequence) do RE Engine e hash de nomes do PAK.

Decodificado a partir do UVS_job_01.uvs / UVS_ui040101.uvs do jogo e do UVS estendido do VSB:
  cabecalho (0x38 bytes): ".SVU", u32 sequencias, u32 texturas, u32 patterns, u64 0, u64 off_seq, u64 off_tex, u64 off_pat, u64 off_str
  sequencia (40 B): u64 0, u64 deslocamento (em caracteres) do caminho da textura na tabela de textos, 24 bytes 0xFF
  textura (u64): baixo = quantidade de patterns, alto = indice do primeiro pattern dela
  pattern (32 B): f32 0, f32 0, f32 u, f32 v, f32 u2, f32 v2, u32 indice da textura, u32 0xFFFFFFFF
  textos: caminhos das texturas em UTF-16, terminados em nulo
"""
import struct

UVS_ASSINATURA = b".SVU"
TEX_VERSION = 251211553
TAMANHO_CABECALHO_UVS = 0x38
BYTES_POR_SEQUENCIA, BYTES_POR_TEXTURA, BYTES_POR_PATTERN = 40, 8, 32


def murmur3_32(dados, semente=0xFFFFFFFF):
    """Calcula o MurmurHash3 de 32 bits usado pelos índices de caminho do PAK."""
    constante_1, constante_2, mascara_32_bits = 0xCC9E2D51, 0x1B873593, 0xFFFFFFFF
    hash_atual = semente
    palavras_completas = len(dados) // 4
    for indice in range(palavras_completas):
        palavra = struct.unpack_from("<I", dados, indice * 4)[0]
        palavra = (palavra * constante_1) & mascara_32_bits
        palavra = ((palavra << 15) | (palavra >> 17)) & mascara_32_bits
        palavra = (palavra * constante_2) & mascara_32_bits
        hash_atual ^= palavra
        hash_atual = ((hash_atual << 13) | (hash_atual >> 19)) & mascara_32_bits
        hash_atual = (hash_atual * 5 + 0xE6546B64) & mascara_32_bits
    palavra = 0
    resto = dados[palavras_completas * 4:]   # 0 a 3 bytes que sobram no fim
    if len(resto) >= 3:
        palavra ^= resto[2] << 16
    if len(resto) >= 2:
        palavra ^= resto[1] << 8
    if len(resto) >= 1:
        palavra ^= resto[0]
        palavra = (palavra * constante_1) & mascara_32_bits
        palavra = ((palavra << 15) | (palavra >> 17)) & mascara_32_bits
        palavra = (palavra * constante_2) & mascara_32_bits
        hash_atual ^= palavra
    hash_atual ^= len(dados)
    hash_atual ^= hash_atual >> 16
    hash_atual = (hash_atual * 0x85EBCA6B) & mascara_32_bits
    hash_atual ^= hash_atual >> 13
    hash_atual = (hash_atual * 0xC2B2AE35) & mascara_32_bits
    hash_atual ^= hash_atual >> 16
    return hash_atual


def hash_nome(caminho):
    """(baixo, alto) do caminho dentro do PAK (ex.: natives/stm/Gui/ui04/ui0401/UVS_ui040101.uvs.8)."""
    return (murmur3_32(caminho.lower().encode("utf-16-le")), murmur3_32(caminho.upper().encode("utf-16-le")))


def nome_hex(caminho):
    baixo, alto = hash_nome(caminho)
    return f"{alto:08X}{baixo:08X}"


def estender_uvs(base, caminhos, celulas=4):
    """Acrescenta uma sequência por caminho de textura, cada uma com uma grade exata de `celulas` x `celulas` patterns.

    Mantém as tabelas existentes e apenas desloca seus offsets ao reconstruir o arquivo UVS.
    """
    if base[:4] != UVS_ASSINATURA:
        raise ValueError("Nao e um .uvs.")
    qtd_sequencias, qtd_texturas, qtd_patterns = struct.unpack_from("<3I", base, 4)
    inicio_sequencias, inicio_texturas, inicio_patterns, inicio_textos = struct.unpack_from("<4Q", base, 0x18)
    tamanhos = (inicio_texturas - inicio_sequencias, inicio_patterns - inicio_texturas, inicio_textos - inicio_patterns)
    if tamanhos != (BYTES_POR_SEQUENCIA * qtd_sequencias, BYTES_POR_TEXTURA * qtd_texturas, BYTES_POR_PATTERN * qtd_patterns):
        raise ValueError("Tabelas do .uvs em layout inesperado.")
    textos = base[inicio_textos:]
    fim_dos_caminhos = 0
    for _ in range(qtd_texturas):   # os caminhos existentes, cada um terminado em nulo
        while textos[fim_dos_caminhos:fim_dos_caminhos + 2] != b"\0\0":
            fim_dos_caminhos += 2
        fim_dos_caminhos += 2
    caminhos_existentes = textos[:fim_dos_caminhos]
    caracteres_usados = len(caminhos_existentes) // 2

    tabela_sequencias = bytearray(base[inicio_sequencias:inicio_texturas])
    tabela_texturas = bytearray(base[inicio_texturas:inicio_patterns])
    tabela_patterns = bytearray(base[inicio_patterns:inicio_textos])
    tabela_textos = bytearray(caminhos_existentes)
    for indice_textura, caminho in enumerate(caminhos, start=qtd_sequencias):
        tabela_sequencias += struct.pack("<QQ", 0, caracteres_usados) + b"\xff" * 24
        tabela_texturas += struct.pack("<II", celulas * celulas, len(tabela_patterns) // BYTES_POR_PATTERN)
        passo = 1.0 / celulas
        for quadro in range(celulas * celulas):
            u0, v0 = (quadro % celulas) * passo, (quadro // celulas) * passo
            tabela_patterns += struct.pack("<6f", 0.0, 0.0, u0, v0, u0 + passo, v0 + passo) + struct.pack("<II", indice_textura, 0xFFFFFFFF)
        texto = caminho.encode("utf-16-le") + b"\0\0"
        tabela_textos += texto
        caracteres_usados += len(texto) // 2
    while len(tabela_textos) % 16:
        tabela_textos += b"\0"

    total_sequencias = qtd_sequencias + len(caminhos)
    total_texturas = qtd_texturas + len(caminhos)
    total_patterns = qtd_patterns + len(caminhos) * celulas * celulas
    novo = bytearray(base[:TAMANHO_CABECALHO_UVS])
    struct.pack_into("<3I", novo, 4, total_sequencias, total_texturas, total_patterns)
    novo_inicio_texturas = TAMANHO_CABECALHO_UVS + BYTES_POR_SEQUENCIA * total_sequencias
    novo_inicio_patterns = novo_inicio_texturas + BYTES_POR_TEXTURA * total_texturas
    novo_inicio_textos = novo_inicio_patterns + BYTES_POR_PATTERN * total_patterns
    struct.pack_into("<4Q", novo, 0x18, TAMANHO_CABECALHO_UVS, novo_inicio_texturas, novo_inicio_patterns, novo_inicio_textos)
    return bytes(novo + tabela_sequencias + tabela_texturas + tabela_patterns + tabela_textos)


def ler_uvs(dados):
    """Resumo para conferencia: (sequencias, texturas, patterns, caminhos)."""
    qtd_sequencias, qtd_texturas, qtd_patterns = struct.unpack_from("<3I", dados, 4)
    inicio_textos = struct.unpack_from("<Q", dados, 0x30)[0]
    textos = dados[inicio_textos:].decode("utf-16-le", "ignore").split("\0")
    return qtd_sequencias, qtd_texturas, qtd_patterns, [texto for texto in textos if texto][:qtd_texturas]


def cabecalho_tex(largura, altura):
    """Cabecalho de 56 bytes de uma textura BC7_SRGB de um mip (igual ao das folhas do VSB e das texturas do jogo)."""
    pitch = ((largura // 4) * 16 + 255) & ~255
    tamanho_dos_dados = pitch * (altura // 4)
    return struct.pack("<14I", 0x00584554, TEX_VERSION, largura | (altura << 16), 0x10010001, 0x63, 0xFFFFFFFF, 0, 0x880,
                       0, 0, 0x38, 0, pitch, tamanho_dos_dados)
