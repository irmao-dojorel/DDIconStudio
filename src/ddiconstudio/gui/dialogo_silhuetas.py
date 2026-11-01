"""Image helpers shared by the Flet silhouette import flow."""
from PIL import Image, ImageFilter

from ddiconstudio import chanfro

LADO_MINIATURA = 280
COR_FUNDO = (38, 48, 59, 255)


def miniatura_silhueta(mascara, intensidade, nivel_chanfro, acabamento=chanfro.Acabamento()):
    """Render a beveled silhouette preview."""
    arma = chanfro.arma_chanfrada(
        mascara,
        LADO_MINIATURA - 10,
        intensidade=intensidade,
        nivel_chanfro=nivel_chanfro,
        acabamento=acabamento,
    )
    fundo = Image.new("RGBA", (LADO_MINIATURA, LADO_MINIATURA), COR_FUNDO)
    posicao = ((LADO_MINIATURA - arma.width) // 2, (LADO_MINIATURA - arma.height) // 2)
    sombra = Image.new("L", fundo.size, 0)
    sombra.paste(arma.getchannel("A"), posicao)
    sombra = sombra.filter(ImageFilter.GaussianBlur(2.8)).point(lambda valor: int(valor * 0.5))
    fundo.paste((0, 0, 0, 255), mask=sombra)
    fundo.alpha_composite(arma, posicao)
    return fundo
