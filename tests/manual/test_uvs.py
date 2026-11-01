"""Confere uvs_ext.py contra os arquivos reais (UVS do jogo, UVS estendido do VSB, cabecalhos de textura)."""
import os
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from ddiconstudio import app_paths, pak_builder, uvs_ext  # noqa: E402

TMP = os.environ["TEMP"]
JOB_ORIG = os.path.join(TMP, "ddc_extract", "natives", "stm", "Gui", "ui01", "Common", "job", "UVS_job_01.uvs.8")
VSB_UVS = app_paths.UVS_MODELO
PANEL_ATLAS = os.path.join(TMP, "ddc_extract", "natives", "stm", "Gui", "ui04", "ui0401", "TEX_ui040101_01_IAM.tex.251211553")
VSB_PAK = open(app_paths.BASE_PAK, "rb").read()
VSB_SHEET = pak_builder._ler_pak(VSB_PAK)[1]["21EF8C0EC312CBFB"]["dados"]

ok = True


def check(nome, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FALHA"), nome, extra)


check("hash UVS_job_01", uvs_ext.hash_nome("natives/stm/Gui/ui01/Common/job/UVS_job_01.uvs.8") == (0xCD99FE97, 0xD76F4EEC))
check("hash UVS_ui040101", uvs_ext.hash_nome("natives/stm/Gui/ui04/ui0401/UVS_ui040101.uvs.8") == (0xE8648FD6, 0x78280E5A))

orig = open(JOB_ORIG, "rb").read()
vsb = open(VSB_UVS, "rb").read()
caminhos = [f"Gui/ui01/Common/job/VBS_cus_voc_ico_sheet_{k}.tex" for k in range(1, 10)]
novo = uvs_ext.estender_uvs(orig, caminhos)
a, b = uvs_ext.ler_uvs(novo), uvs_ext.ler_uvs(vsb)
check("contagens e caminhos iguais ao VSB", a == b, str(a[:3]))
o = struct.unpack_from("<4Q", vsb, 0x18)
n = struct.unpack_from("<4Q", novo, 0x18)
check("offsets das tabelas iguais", o == n, f"{o} {n}")
check("sequencias+texturas iguais", novo[0x38:o[2]] == vsb[0x38:o[2]])
# patterns: so a altura das folhas do VSB difere (0.2475 em vez de 0.25)
iguais = sum(novo[o[2] + i * 32:o[2] + i * 32 + 32] == vsb[o[2] + i * 32:o[2] + i * 32 + 32] for i in range(160))
check("patterns identicos (esperado: 16 do jogo + os sem arredondamento do VSB)", iguais >= 16, f"{iguais}/160")
check("textos iguais", novo[n[3]:n[3] + 0x3AE] == vsb[o[3]:o[3] + 0x3AE])

atlas = open(PANEL_ATLAS, "rb").read()[:56]
check("cabecalho tex 512x256 = atlas do jogo", uvs_ext.cabecalho_tex(512, 256) == atlas)
check("cabecalho tex 800x800 = folha do VSB", uvs_ext.cabecalho_tex(800, 800) == VSB_SHEET[:56])
print("TUDO OK" if ok else "HA FALHAS")
