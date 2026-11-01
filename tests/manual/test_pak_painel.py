"""Gera um PAK de teste com glifos de painel e confere a estrutura (sem o jogo)."""
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
import xxhash  # noqa: E402
import zstandard  # noqa: E402
from ddiconstudio import app_paths  # noqa: E402
from ddiconstudio import icon_gen  # noqa: E402
from ddiconstudio import pak_builder  # noqa: E402
from ddiconstudio import uvs_ext  # noqa: E402
from PIL import Image  # noqa: E402

saida = os.path.join(tempfile.gettempdir(), "ddc_pak_test")
icones = {n: None for n in range(16, 20)}
armas = icon_gen.armas()
print("armas:", len(armas), armas[:3])
if len(armas) < 2:
    raise RuntimeError("O teste precisa de pelo menos duas silhuetas em assets/silhuetas.")
glifos = {16: icon_gen.render_glifo([dict(arma=armas[0], escala=1.0)]), 17: icon_gen.render_glifo([dict(arma=armas[1], escala=1.0)]),
          18: Image.new("RGBA", (200, 200), (255, 0, 0, 255)), 33: icon_gen.render_glifo([dict(arma=armas[0], escala=1.0)])}
banners = {
    numero: Image.new("RGBA", (pak_builder.BANNER_LARGURA, pak_builder.BANNER_ALTURA), (numero, 0, 0, 255))
    for numero in (16, 17)
}
destino = pak_builder.montar_pak(icones, saida, glifos=glifos, banners=banners)

pak = open(destino, "rb").read()
cab, arquivos = pak_builder._ler_pak(pak)
print("arquivos:", len(arquivos))
uvs_lista = arquivos[pak_builder.HASH_UVS_LISTA]
assert uvs_lista["attr"] == 2, "UVS deve continuar comprimido em Zstandard"
uvs_descomprimido = zstandard.ZstdDecompressor().decompress(uvs_lista["dados"])
modelo_uvs = bytearray(open(app_paths.UVS_MODELO, "rb").read())
folhas_uvs = sorted({numero // 16 for numero in icones})
pak_builder._ajustar_grade_do_uvs(modelo_uvs, folhas_uvs)
assert uvs_descomprimido == modelo_uvs, "UVS comprimido difere do modelo atualizado"
hash_uvs_64 = xxhash.xxh64(uvs_descomprimido, seed=0xFFFFFFFF).intdigest()
checksum_uvs = xxhash.xxh32(hash_uvs_64.to_bytes(8, "little"), seed=0xFFFFFFFF).intdigest()
assert uvs_lista["chk"] == checksum_uvs, "checksum do UVS atualizado incorreto"
nome_uvs = uvs_ext.nome_hex("natives/stm/Gui/ui04/ui0401/UVS_ui040101.uvs.8")
assert nome_uvs in arquivos, "UVS do painel ausente"
print("UVS painel ok", len(arquivos[nome_uvs]["dados"]))
for folha in (1, 2):
    nome = uvs_ext.nome_hex(f"natives/stm/Gui/ui04/ui0401/VBS_cus_pnl_ico_sheet_{folha}.tex.{uvs_ext.TEX_VERSION}")
    assert nome in arquivos, f"folha de painel {folha} ausente"
    print(f"painel sheet {folha} ok", len(arquivos[nome]["dados"]))
nome_folha_3 = uvs_ext.nome_hex(f"natives/stm/Gui/ui04/ui0401/VBS_cus_pnl_ico_sheet_3.tex.{uvs_ext.TEX_VERSION}")
assert nome_folha_3 not in arquivos, "folha 3 nao deveria ser gerada: nao ha glifos nela"
print("painel sheet 3 ausente como esperado (sem glifos na folha)")
nome_uvs_banner = uvs_ext.nome_hex(pak_builder.BANNER_UVS)
sequencias_banner = uvs_ext.ler_uvs(arquivos[nome_uvs_banner]["dados"])
caminhos_banner = sequencias_banner[3]
caminho_banner_vanilla = uvs_ext.ler_uvs(open(app_paths.UVS_BANNER, "rb").read())[3][-1]
assert len(caminhos_banner) == 86
assert caminhos_banner[10:16] == [caminho_banner_vanilla] * 6
assert caminhos_banner[16] == "Gui/ui04/ui0401/VBS_cus_banner_16.tex"
assert caminhos_banner[17] == "Gui/ui04/ui0401/VBS_cus_banner_17.tex"
print("sequencias dos banners: slots 10..15 preservados, 16/17 alinhados aos icones")
u = arquivos[nome_uvs]["dados"]
print(uvs_ext.ler_uvs(u))
# o PAK reescrito tem que ter as mesmas entradas do base + novas, com offsets validos
total = struct.unpack_from("<I", pak, 8)[0]
fim = max(struct.unpack_from("<Q", pak, 16 + i * 48 + 8)[0] + struct.unpack_from("<Q", pak, 16 + i * 48 + 16)[0] for i in range(total))
assert fim == len(pak), "o ultimo arquivo nao termina no fim do PAK"
print("entradas:", total, "fim dos dados == tamanho: True")
