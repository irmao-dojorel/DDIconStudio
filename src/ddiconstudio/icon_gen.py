"""Gerador de icones de vocacao: moldura + fundo colorido (com divisao opcional) + arma.

render(...) devolve uma imagem RGBA 200x200 pronta para salvar em icons\\<n>.png.
Ordem do desenho: fundo texturizado -> armas (cada uma com sombra, limitada pela moldura) -> moldura por cima.
"""
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageFilter, ImageOps

from ddiconstudio import app_paths, chanfro
from ddiconstudio.glyph_gen import LADO_GLIFO, render as render_glifo_mascara

ASSETS = app_paths.ASSETS
LADO_CELULA = 200  # tamanho de uma célula da grade 4x4 usada pelas folhas de ícones do PAK
LADO_ARMA = 140    # maior lado da arma na célula, com escala 1.0 (nos brasões vanilla a arma ocupa ~80% da altura)

# multiplicadores de cor sobre o chanfro de pedra; 'prata' deixa o tom bege do vanilla como está
METAIS = {
    'prata': (1.00, 1.00, 1.00),
    'latao': (1.04, 1.00, 0.88),   # tom dos glifos do painel (atlas do jogo: R/G 1.14, B/G 0.76)
    'ouro': (1.00, 0.80, 0.42),
    'bronze': (0.92, 0.62, 0.38),
    'aco escuro': (0.62, 0.66, 0.74),
    'branco': (1.00, 1.00, 1.00),
}
METAIS_MOLDURA = {
    'bronze': (1.20, 0.93, 0.83),
    'prata': (1.00, 1.00, 1.04),
    'ouro': (1.10, 1.00, 0.72),
    'ferro': (0.80, 0.84, 0.92),
    'cobre': (1.35, 0.80, 0.62),
}
GANHO_CONTRASTE_MOLDURA = 0.18
GANHO_REALCE_MOLDURA_MESTRE = 480.0
GANHO_SOMBRA_ARMA = 1.0
PALETA = {
    'vermelho': (130, 48, 54), 'ambar': (164, 106, 8), 'azul': (25, 101, 130), 'verde': (72, 110, 59),
    'roxo': (83, 39, 78), 'turquesa': (30, 120, 125), 'rosa': (165, 55, 105), 'cinza': (85, 85, 95),
    'preto': (34, 34, 40), 'osso': (195, 188, 168),
}


def listar(subpasta):
    """Nomes (sem .png) dos arquivos de `assets/<subpasta>`, ignorando os que comecam com _ e as mascaras."""
    pasta = os.path.join(ASSETS, subpasta)
    if not os.path.isdir(pasta):
        return []
    return sorted(nome[:-4] for nome in os.listdir(pasta)
                  if nome.lower().endswith('.png') and not nome.startswith('_') and not nome.endswith('_mask.png'))


def molduras():
    ordem = {'simples': 0, 'avancada': 1, 'mestre': 2}
    return sorted(listar('molduras'), key=lambda nome: (ordem.get(nome, len(ordem)), nome))


def armas():
    return listar('silhuetas')


def _ruido(gerador, tamanho_grao):
    """Cria ruído em baixa resolução e o amplia para a célula; `tamanho_grao` controla o tamanho aparente dos grãos."""
    lado = LADO_CELULA // tamanho_grao + 3
    imagem = Image.frombytes('L', (lado, lado), bytes(gerador.getrandbits(8) for _ in range(lado * lado)))
    return imagem.resize((LADO_CELULA, LADO_CELULA), Image.BICUBIC)


def _textura(semente):
    """Devolve (luminosidade L 0..255, pontos escuros L) para reutilizar a mesma textura nas duas metades."""
    gerador = random.Random(semente)
    ruido_grosso = Image.blend(_ruido(gerador, 40), _ruido(gerador, 14), 0.6)
    ruido_fino = Image.blend(_ruido(gerador, 5), _ruido(gerador, 2), 0.5)
    luminosidade = ImageOps.autocontrast(Image.blend(ruido_grosso, ruido_fino, 0.65), cutoff=1)
    pontos_escuros = _ruido(gerador, 2).point(lambda valor: 80 if valor > 242 else 0)
    return luminosidade, pontos_escuros


def _cor(canais):
    """Converte canais calculados em RGB válido, limitando cada um ao intervalo 0..255."""
    return tuple(max(0, min(255, int(valor))) for valor in canais)


def _fundo(cor, luminosidade, pontos_escuros):
    """Aplica luminosidade e pontos escuros à cor de fundo, produzindo uma imagem RGB de uma célula."""
    # A máscara 40..231 interpola entre uma base escura (40%) e uma clara (112% + 6 por canal).
    escuro = Image.new('RGB', (LADO_CELULA, LADO_CELULA), _cor([valor * 0.40 for valor in cor]))
    claro = Image.new('RGB', (LADO_CELULA, LADO_CELULA), _cor([valor * 1.12 + 6 for valor in cor]))
    imagem = Image.composite(claro, escuro, luminosidade.point(lambda valor: int(40 + valor * 0.75)))
    imagem.paste((0, 0, 0), mask=pontos_escuros)
    return imagem


def _tingir(imagem, multiplicadores, ganho=1.0):
    """Cinza -> cor: multiplica os canais R, G e B pelos `multiplicadores` (imagem RGBA em tons de cinza)."""
    vermelho, verde, azul, alfa = imagem.split()
    canais_tingidos = tuple(canal.point(lambda valor, mult=mult: min(255, int(valor * mult * ganho)))
                            for canal, mult in zip((vermelho, verde, azul), multiplicadores))
    return Image.merge('RGBA', canais_tingidos + (alfa,))


def _realcar_luz_moldura(imagem, mestre=False):
    luminancia = np.asarray(imagem.convert('L'), dtype=np.float32)
    canal = Image.fromarray(luminancia.astype(np.uint8), 'L')
    media_local = np.asarray(
        canal.filter(ImageFilter.GaussianBlur(chanfro.SIGMA_CONTRASTE_LOCAL)),
        dtype=np.float32,
    )
    brilho = (
        luminancia
        + GANHO_CONTRASTE_MOLDURA * (luminancia - 128)
        + chanfro.CONTRASTE_LOCAL * (luminancia - media_local)
    )
    if mestre:
        realce = np.clip((luminancia - 128) / 127, 0, 1) ** 1.5
        brilho += GANHO_REALCE_MOLDURA_MESTRE * realce
    brilho = Image.fromarray(np.clip(brilho, 0, 255).astype(np.uint8), 'L')
    return Image.merge('RGBA', (brilho, brilho, brilho, imagem.getchannel('A')))


def _carregar_moldura(moldura, metal_moldura):
    """Devolve moldura tingida, máscara do interior e centro do interior."""
    pasta = os.path.join(ASSETS, 'molduras')
    imagem = Image.open(os.path.join(pasta, moldura + '.png')).convert('RGBA')
    imagem = _realcar_luz_moldura(imagem, mestre=moldura == 'mestre')
    imagem = _tingir(imagem, METAIS_MOLDURA.get(metal_moldura, METAIS_MOLDURA['bronze']))
    mascara = Image.open(os.path.join(pasta, moldura + '_mask.png')).convert('L')
    caixa = mascara.point(lambda valor: 255 if valor > 128 else 0).getbbox()
    centro = ((caixa[0] + caixa[2]) / 2, (caixa[1] + caixa[3]) / 2)
    return imagem, mascara, centro


def _montar_fundo(cor_a, cor_b, semente, mascara, centro_x):
    """Fundo texturizado, dividido opcionalmente e escurecido junto da moldura."""
    luminosidade, pontos_escuros = _textura(semente)
    fundo = _fundo(cor_a, luminosidade, pontos_escuros)
    if cor_b is not None:
        fundo_direito = _fundo(cor_b, luminosidade, pontos_escuros)
        metade_direita = Image.new('L', (LADO_CELULA, LADO_CELULA), 0)
        metade_direita.paste(255, (int(round(centro_x)), 0, LADO_CELULA, LADO_CELULA))
        fundo = Image.composite(fundo_direito, fundo, metade_direita)

    vinheta = mascara.filter(ImageFilter.GaussianBlur(9)).point(lambda valor: int(70 + 185 * valor / 255))
    return Image.composite(fundo, Image.new('RGB', (LADO_CELULA, LADO_CELULA), (0, 0, 0)), vinheta)


def _zona_proibida(mascara, margem):
    """Máscara da faixa junto da moldura em que a arma não pode tocar."""
    interior_seguro = mascara.point(lambda valor: 255 if valor > 128 else 0)
    for _ in range(margem):
        interior_seguro = interior_seguro.filter(ImageFilter.MinFilter(3))
    return interior_seguro.point(lambda valor: 255 - valor)


def _caminho_da_silhueta(nome):
    return os.path.join(ASSETS, 'silhuetas', nome + '.png')


def _ler_arma(nome, espelhar):
    """Carrega a máscara alfa da silhueta e a espelha quando solicitado."""
    mascara = Image.open(_caminho_da_silhueta(nome)).convert('RGBA').getchannel('A')
    return ImageOps.mirror(mascara) if espelhar else mascara


_cache_chanfro = {}


def _arma_chanfrada(nome, espelhar, rotacao):
    """Carrega o chanfro gravado, aplicando o efeito padrão a máscaras antigas."""
    caminho = _caminho_da_silhueta(nome)
    chave = (nome, espelhar, rotacao, os.path.getmtime(caminho))
    if chave not in _cache_chanfro:
        armazenada = Image.open(caminho).convert('RGBA')
        pronta = any(armazenada.getchannel(canal).getextrema()[0] < 255 for canal in ('R', 'G', 'B'))
        if pronta:
            imagem = armazenada
            if espelhar:
                imagem = ImageOps.mirror(imagem)
            if rotacao % 360:
                imagem = imagem.rotate(-rotacao, resample=Image.BICUBIC, expand=True)
        else:
            mascara = armazenada.getchannel('A')
            if espelhar:
                mascara = ImageOps.mirror(mascara)
            if rotacao % 360:
                mascara = mascara.rotate(-rotacao, resample=Image.BICUBIC, expand=True)
            imagem = chanfro.aplicar(mascara)
        _cache_chanfro[chave] = imagem
    return _cache_chanfro[chave]


def _arma_plana(nome, espelhar, rotacao):
    """Silhueta branca sem chanfro; o metal é aplicado depois."""
    mascara = _ler_arma(nome, espelhar)
    if rotacao % 360:
        mascara = mascara.rotate(-rotacao, resample=Image.BICUBIC, expand=True)
    imagem = Image.new('RGBA', mascara.size, (255, 255, 255, 0))
    imagem.putalpha(mascara)
    return imagem


def _posicionar_arma(imagem, escala, ajuste_x, ajuste_y, centro):
    """Redimensiona e centraliza a arma na célula, aplicando o deslocamento."""
    fator = escala * LADO_ARMA / chanfro.LADO_REFERENCIA
    imagem = imagem.resize((max(1, round(imagem.width * fator)), max(1, round(imagem.height * fator))), Image.LANCZOS)
    x = int(round(centro[0] + ajuste_x - imagem.width / 2))
    y = int(round(centro[1] + ajuste_y - imagem.height / 2))
    return imagem, x, y


def _cabe_fora_da_zona(imagem, x, y, zona_proibida):
    """True se a parte visível da arma (alfa > 40) não encosta na zona proibida."""
    silhueta = Image.new('L', (LADO_CELULA, LADO_CELULA), 0)
    silhueta.paste(imagem.getchannel('A').point(lambda valor: 255 if valor > 40 else 0), (x, y))
    return ImageChops.multiply(silhueta, zona_proibida).getbbox() is None


def _encolher_ate_caber(imagem, escala, tentativas, centro, zona_proibida):
    """Reduz a arma de 3% em 3% (até 17 passos) até caber longe da moldura.

    `tentativas` = lista de (ajuste_x, ajuste_y), testadas em ordem.
    Se nada couber, devolve a última posição tentada. Resultado: (imagem, x, y).
    """
    resultado = None
    for ajuste_x, ajuste_y in tentativas:
        for passo in range(18):
            escala_tentada = escala * (1 - 0.03 * passo)
            resultado = _posicionar_arma(imagem, escala_tentada, ajuste_x, ajuste_y, centro)
            if _cabe_fora_da_zona(*resultado, zona_proibida):
                return resultado
    return resultado


def _camada_da_arma(imagem, x, y, com_sombra, mascara_recorte):
    """Devolve sombra e arma em camadas separadas, ambas recortadas pela moldura."""
    sombra = Image.new('RGBA', (LADO_CELULA, LADO_CELULA), (0, 0, 0, 0))
    if com_sombra:
        alfa_sombra = Image.new('L', (LADO_CELULA, LADO_CELULA), 0)
        alfa_sombra.paste(imagem.getchannel('A'), (x, y))
        alfa_sombra = alfa_sombra.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(7.0))
        alfa_sombra = alfa_sombra.point(lambda valor: min(255, int(valor * GANHO_SOMBRA_ARMA)))
        sombra.paste((0, 0, 0, 255), mask=alfa_sombra)
    arma = Image.new('RGBA', (LADO_CELULA, LADO_CELULA), (0, 0, 0, 0))
    arma.paste(imagem, (x, y))
    if mascara_recorte is not None:
        sombra.putalpha(ImageChops.multiply(sombra.getchannel('A'), mascara_recorte))
        arma.putalpha(ImageChops.multiply(arma.getchannel('A'), mascara_recorte))
    return sombra, arma


def _camada_do_item(item, centro, zona_proibida, metal, com_sombra, mascara_recorte, uma_so_arma, usar_chanfro):
    """Desenha uma silhueta de render(): aplica o chanfro opcional, posiciona, tinge e põe sombra."""
    escala = item.get('escala', 1.0)
    ajuste_x, ajuste_y = item.get('dx', 0), item.get('dy', 0)
    espelhar = item.get('espelhar', False)
    rotacao = item.get('rotacao', 0)
    imagem = (_arma_chanfrada(item['arma'], espelhar, rotacao) if usar_chanfro
              else _arma_plana(item['arma'], espelhar, rotacao))

    if zona_proibida is None:
        imagem, x, y = _posicionar_arma(imagem, escala, ajuste_x, ajuste_y, centro)
    else:
        tentativas = [(ajuste_x, ajuste_y)]
        if uma_so_arma:
            tentativas.append((0, 0))   # com uma arma, se nao coube na posicao pedida, tenta centralizada
        imagem, x, y = _encolher_ate_caber(imagem, escala, tentativas, centro, zona_proibida)

    imagem = _tingir(imagem, METAIS.get(metal, METAIS['prata']))
    return _camada_da_arma(imagem, x, y, com_sombra, mascara_recorte)


def _compor_camadas_de_armas(tela, sombras, armas):
    for sombra in sombras:
        tela = Image.alpha_composite(tela, sombra)
    for arma in armas:
        tela = Image.alpha_composite(tela, arma)
    return tela


def render(moldura='simples', cor_a=(150, 28, 28), cor_b=None, arma=None, semente=1,
           escala=1.0, dx=0, dy=0, metal='prata', sombra=True, espelhar=False, metal_moldura='bronze',
           transparente=False, margem=0, armas=None, rotacao=0, sem_moldura=False, usar_chanfro=True):
    """Cores são RGB 0..255; `cor_b` divide o fundo ao meio, sem linha (esquerda `cor_a`, direita `cor_b`).
    `margem` é em pixels e `rotacao` em graus; `semente` fixa a textura aleatória. `transparente` remove o fundo.

    armas = lista de dicts (arma, escala, dx, dy, rotacao, espelhar), desenhadas em ordem (a ultima fica por cima);
    rotacao em graus, positivo = sentido horario, em torno do centro da arma.
    quando dada, substitui arma/escala/dx/dy/rotacao/espelhar.
    margem > 0 encolhe a arma ate caber a essa distancia da moldura (so com uma arma ela tambem e centralizada).
    sem_moldura = so as silhuetas (sem fundo, moldura nem recorte), na mesma posicao do brasao.
    usar_chanfro=False preserva a silhueta plana para os glifos pequenos do painel da Guilda."""
    if armas is None:
        armas = [dict(arma=arma, escala=escala, dx=dx, dy=dy, rotacao=rotacao, espelhar=espelhar)]
    armas = [item for item in armas if item.get('arma')]
    imagem_moldura, mascara, centro = _carregar_moldura(moldura, metal_moldura)

    if transparente or sem_moldura:
        tela = Image.new('RGBA', (LADO_CELULA, LADO_CELULA), (0, 0, 0, 0))
    else:
        tela = _montar_fundo(cor_a, cor_b, semente, mascara, centro[0]).convert('RGBA')

    zona_proibida = _zona_proibida(mascara, margem) if margem > 0 and not sem_moldura else None
    mascara_recorte = None if sem_moldura else mascara
    sombras, camadas_armas = [], []
    for item in armas:
        camada_sombra, camada_arma = _camada_do_item(
            item, centro, zona_proibida, metal, sombra, mascara_recorte,
            uma_so_arma=len(armas) == 1, usar_chanfro=usar_chanfro,
        )
        sombras.append(camada_sombra)
        camadas_armas.append(camada_arma)
    tela = _compor_camadas_de_armas(tela, sombras, camadas_armas)

    if sem_moldura:
        return tela
    # fundo e arma limitados ao interior; moldura por cima
    tela.putalpha(ImageChops.multiply(tela.getchannel('A'), mascara.filter(ImageFilter.MaxFilter(3))))
    return Image.alpha_composite(tela, imagem_moldura)


def render_glifo(armas, tamanho=LADO_GLIFO):
    """Silhuetas planas em lat?o para o painel da Guilda, no estilo do atlas do jogo (sem chanfro)."""
    if not [item for item in armas if item.get('arma')]:
        return None
    imagem = render(armas=armas, sem_moldura=True, usar_chanfro=False, sombra=False)
    return render_glifo_mascara(imagem.getchannel('A'), tamanho)


PCT_BRASAO = 80   # lado maximo visivel do brasao, em relacao a celula de 200 px


def reduzir(imagem, porcentagem):
    """Normaliza o maior lado visivel para `porcentagem`% da celula, preservando proporcao."""
    lado = max(1, min(LADO_CELULA, round(LADO_CELULA * porcentagem / 100)))
    imagem = imagem.convert('RGBA')
    caixa = imagem.getchannel('A').getbbox()
    saida = Image.new('RGBA', (LADO_CELULA, LADO_CELULA), (0, 0, 0, 0))
    if caixa is None:
        return saida
    imagem = imagem.crop(caixa)
    escala = min(lado / imagem.width, lado / imagem.height)
    tamanho = (max(1, round(imagem.width * escala)), max(1, round(imagem.height * escala)))
    imagem = imagem.resize(tamanho, Image.LANCZOS)
    saida.alpha_composite(imagem, ((LADO_CELULA - tamanho[0]) // 2, (LADO_CELULA - tamanho[1]) // 2))
    return saida
