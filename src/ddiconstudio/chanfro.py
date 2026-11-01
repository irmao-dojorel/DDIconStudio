"""Chanfro de pedra/osso das armas dos brasoes, calibrado nos icones de vocacao vanilla.

A silhueta (mascara L) vira uma imagem colorida: a altura de cada pixel cresce com a distancia a borda ate
LARGURA_CHANFRO (o chanfro percorre a espessura do traco), uma malha triangular cria planos batidos e a luz,
vinda de cima e da esquerda, ilumina as faces voltadas para ela. O tom bege/prata e a granulacao seguem os icones
vanilla.
"""
import hashlib
import threading
from collections import OrderedDict

import numpy as np
from dataclasses import dataclass
from PIL import Image, ImageFilter, ImageOps

_CACHE = OrderedDict()   # ultimas renderizacoes: a previa e o salvamento usam os mesmos parametros
_CACHE_TAMANHO = 4
_CACHE_TRAVA = threading.Lock()

LADO_REFERENCIA = 420      # maior lado da arma, em px, na escala em que o chanfro foi calibrado
LARGURA_CHANFRO = 7.0      # px da borda ate o topo plano
FATOR_CHANFRO_LOCAL = 1.1
SUAVIZACAO_DIRECAO = 2.6   # sigma da distancia usada so para a direcao da normal: degraus do contorno viram listras
ELEVACAO_LUZ = 45          # graus acima do plano da imagem; a luz e a mesma do difuso e do especular
EXPOENTE_ESPECULAR = 24    # quanto maior, mais fino o brilho metalico
GANHO_ESPECULAR = 60       # niveis de cinza somados no pico do brilho
SUAVIZACAO_INCLINACAO = 0.6  # sigma da inclinacao nitida; pouco, para o chanfro continuar marcado
DOMO = 0.6                 # px de altura por px de distancia a borda, no miolo (abaulado)
# relevo de forja (macro): o topo ondula e se quebra em facetas grandes nos tracos nodosos e nos planaltos
ONDULACAO = 0.06           # desvio padrao da inclinacao (px/px) do ruido de altura de baixa frequencia
SIGMAS_ONDULACAO = (18.0, 40.0)
PESOS_ONDULACAO = (0.7, 1.0)
TAMANHO_FACETA = 30.0      # px: lado medio de cada faceta (celula de Voronoi)
FACETA = 0.30              # desvio padrao da inclinacao (px/px) de cada faceta, com organicidade 1
SIGMA_ORGANICO = 10.0      # px: alcance da curvatura da borda para dentro
CURVATURA_LISA = 0.02      # curvatura media (1/px) de contorno liso: organicidade 0
CURVATURA_NODOSA = 0.05    # curvatura media de contorno nodoso: organicidade 1
ORGANICO_MINIMO = 0.15
ORGANICO_MAXIMO = 1.3
FACETA_PLANALTO = 0.3      # forca das facetas no topo plano (fora do chanfro), em fracao de FACETA
ONDULACAO_PLANALTO = 1.0   # multiplica ONDULACAO no topo plano
FACETA_ATRAVES = 0.25      # fracao da inclinacao da faceta que sobra atravessando o traco
TORCAO = 0.5               # inclinacao de torcao (oposta nas duas aguas), em fracao de FACETA
SIGMA_EIXO = 4.0           # px: suavizacao do tensor de estrutura que da o eixo do traco
SUAVIZACAO_FACETA = 1.0    # px: quebra de angulo entre facetas
ENTRADA_MACRO = 4.0        # px depois da borda em que o relevo macro chega ao valor pleno
INTENSIDADE_MINIMA = 0.35
INTENSIDADE_PADRAO = 0.65
INTENSIDADE_MAXIMA = 1.45
CONTRASTE_LUZ = 1.6        # multiplicador do ganho de luz/sombra no maximo do slider
SUAVIZACAO_ALTURA = 0.6    # suaviza o relevo sem apagar os veios
ANGULO_LUZ = 225           # direcao de onde vem a luz (0 = direita, 90 = baixo): cima e esquerda
ABERTURA_LUZ = 65          # graus: a luz lateral cobre grande parte das faces voltadas para a esquerda e o topo, como no vanilla
CONTRASTE_FACES = 1.8      # escala a inclinacao dos detalhes (amassados, veios) na normal
CONTRASTE_CHANFRO = 2.5    # escala a inclinacao do chanfro na normal: quanto maior, mais marcada a aresta
BRILHO_BASE = 125          # prata quente sem inclinacao
GANHO_LUZ = 170            # quanto as faces voltadas para a luz clareiam
GANHO_SOMBRA = 45          # quanto as faces voltadas para o lado oposto escurecem
VEIOS_POR_AREA = 0.00018
AMASSADOS_POR_AREA = 0.00035   # teto de amassados por px de area do traco; o encaixe costuma parar antes
RAIO_AMASSADO = (6.0, 16.0)   # px (raio), na escala de referencia; os grandes entram primeiro, os pequenos tapam as frestas
EXPOENTE_RAIO_AMASSADO = 0.4  # <1 puxa o sorteio para os raios grandes (o martelo vanilla tem mais amassados de 22-28 px)
PROFUNDIDADE_AMASSADO = (0.75, 1.05)  # profundidade / raio, multiplicada pela intensidade
SOBREPOSICAO_AMASSADO = 0.75 # distancia minima entre centros / soma dos raios: <1 faz vizinhos se cortarem em cristas
ALCANCE_AMASSADO = 0.9        # o amassado so nasce se distancia do centro a borda >= ALCANCE * raio + FOLGA_BORDA
FOLGA_BORDA_AMASSADO = 1.0    # px; o amassado pode morder o chanfro mas nao chega ao contorno
IRREGULARIDADE_AMASSADO = 0.12
FACETAMENTO_AMASSADO = (0.4, 0.8)   # mistura entre contorno eliptico e poligonal (5 a 7 lados)
EXPOENTE_POLIGONO_AMASSADO = 8.0    # norma p que arredonda os cantos do poligono
ACHATAMENTO_AMASSADO = (0.75, 1.0)  # razao entre os eixos da elipse do amassado
NUCLEO_AMASSADO = 8.0               # px de distancia a borda que definem as pecas largas (cabecas, pomo)
AREA_NUCLEO_PEQUENO = 2500          # px de nucleo abaixo dos quais a peca (pomo, ponta do cabo) fica sem amassado
CANDIDATOS_AMASSADO = 6000          # sorteios do encaixe (ordenados do maior raio ao menor)
SOMBRA_EXTRA_AMASSADO = 25          # escurecimento extra da parede do amassado virada para o lado oposto da luz
LUZ_EXTRA_AMASSADO = 12             # clareamento extra (depois do ombro) da parede voltada para a luz
PERFIL_AMASSADO = 2.5              # 1 - n^p: >2 da fundo mais chato e paredes ingremes junto a aresta
ASSIMETRIA_AMASSADO = (0.25, 0.5)    # quanto o fundo do amassado se desloca para o lado da luz
CONTRASTE_AMASSADO = 1.3            # escala a inclinacao do amassado na sua normal propria
GRANULACAO = 9.0           # grao fino (sigma SIGMA_GRAO), niveis de cinza
GRANULACAO_MEDIA = 5.0     # estrias medias ao longo do contorno (sigma SIGMA_ESTRIAS)
MANCHAS = 4.0              # manchas de baixa frequencia (sigma SIGMA_MANCHAS)
MANCHAS_GRANDES = 3.0     # nuvens escuras maiores do bege (sigma SIGMA_MANCHAS_GRANDES)
SIGMA_MANCHAS_GRANDES = 8.0
LIMITE_GRAO = 255          # brilho a partir do qual o grao so tem a amplitude minima
FAIXA_GRAO = 100           # niveis de cinza abaixo de LIMITE_GRAO em que o grao ainda esta pleno
GRAO_MINIMO_LUZ = 0.35     # fracao do grao que resta nas luzes
CROMA = 0.5                # variacao do matiz bege (R sobe, B desce) entre graos vizinhos
SIGMA_GRAO = 0.5           # px
SIGMA_MANCHAS = 4.5        # px
SIGMA_CROMA = 1.2          # px
CROMA_FINO = 1.4           # variacao de matiz grao a grao (o vanilla tem desvio ~2.5 niveis em R-B no grao fino)
SIGMA_CROMA_FINO = 0.6
CROMA_GROSSO = 1.3         # manchas de matiz (mais amarelo / mais cinza) de alguns px
SIGMA_CROMA_GROSSO = 5.0
SUAVIZACAO_ORIENTACAO = 4.0  # sigma (px) do campo de direcao do contorno, que tambem preenche o miolo
SIGMA_ESTRIAS = 0.7        # px, largura das estrias medias (atraves do contorno)
COMPRIMENTO_ESTRIAS = 2.0  # px, sigma ao longo do contorno
ASSIMETRIA_GRAO = 0.1     # >0: grao fino com pontos claros raros (vanilla: assimetria +0.4..+0.8)
ASSIMETRIA_MANCHAS = -0.3  # <0: manchas com cauda escura (vanilla: -0.5..-0.8 nas bandas de 2-8 px)
LASCAS = 0.15              # px de deslocamento do tom: bordas entre faces onduladas
SIGMA_LASCAS = 2.2
LASCAS_FINAS = 0.1         # px, lascas pequenas na mesma borda
SIGMA_LASCAS_FINAS = 0.8
SIGMA_CAVIDADE = 3.0       # px, vizinhanca usada para medir cavidades do relevo dos detalhes
ESCALA_CAVIDADE = 2.0      # relevo abaixo do vizinho que conta como cavidade plena
SUJEIRA = 6.0             # escurecimento nas cavidades e cantos concavos
SIGMA_PONTA = 5.0
ESCALA_CANTO = 0.12        # cobertura da mascara a mais/menos que a borda reta que conta como canto pleno
DESGASTE = 22.0            # clareamento das pontas convexas (vanilla: +11..+21 em relacao a vizinhanca)
FIOS = 14.0                # fios claros de escova ao longo do contorno
SIGMA_FIOS = 0.9
COMPRIMENTO_FIOS = 6.0
LIMIAR_FIOS = 0.8          # so a cauda do ruido orientado vira fio
SIGMA_TUFOS = 7.0
POCOS_POR_AREA = 0.0006
RAIO_POCO = (0.7, 1.5)
PROFUNDIDADE_POCO = (15.0, 35.0)
RISCOS_POR_AREA = 0.003
COMPRIMENTO_RISCO = (5.0, 16.0)
DESVIO_RISCO = 0.6         # rad em torno da direcao do contorno
BRILHO_RISCO = (10.0, 24.0)
FRACAO_RISCOS_ESCUROS = 0.4  # riscos escuros (sulcos), um pouco mais fortes que os claros
CRAQUELADO = 16.0          # veios claros em rede (bordas de celulas), so em trechos
TAMANHO_CRAQUELADO = 14.0  # px, lado medio das celulas
LARGURA_CRAQUELADO = 0.9   # px (diferenca F2-F1)
SIGMA_TRECHOS_CRAQUELADO = 7.0
LIMITE_MARCAS = 215        # brilho acima do qual pocos e riscos quase somem
LIMIAR_ARESTA = 0.2        # laplaciano da distancia (negativo) a partir do qual o eixo medial e crista
ARESTA_ESCURA = 22.0       # linha escura fina sobre a crista
ARESTA_LASCAS = 26.0       # lascas claras curtas atravessando a crista
ATENUACAO_MANCHAS_LUZ = 0.75 # fracao das manchas que some nas faces claras (vanilla: cremes limpos)
SATURACAO_LUZ = 0.7        # iluminacao a partir da qual a face ja recebe luz plena
EXPOENTE_LUZ = 1.8         # >1 so as faces bem voltadas para a luz clareiam ate o creme; menor = luz mais larga
EXPOENTE_SOMBRA = 0.8
JOELHO_LUZ = 180           # brilho (antes da curva tonal) a partir do qual as manchas da textura somem nas luzes
# curva tonal (brilho calculado -> brilho final), calibrada por casamento de histograma com as 4 armas vanilla
# (cajado, arco, martelo, lanca, peso igual), com inclinacao limitada a 0.45..1.5 para nao posterizar:
# meios-tons sobem, a faixa 140-220 e comprimida e as luzes vao a ~250 em degrade (o vanilla e quase bimodal)
CURVA_TOM = np.array([
    (20, 76.6), (40, 85.6), (60, 94.6), (80, 103.6), (90, 108.1), (100, 112.6), (110, 120.5), (120, 129.1),
    (130, 135.1), (140, 139.6), (150, 144.1), (165, 150.9), (180, 157.6), (200, 166.6), (220, 175.6), (240, 195.1),
    (260, 225.1), (280, 246.3), (300, 252.0), (330, 252.0), (380, 252.0),
], np.float32)
SUAVIZACAO_TOM = 0.5       # sigma (px) do tom antes do grao: o vanilla passa do bege ao branco em degrade
CONTRASTE_LOCAL = 0.5      # realce do brilho contra a media local (sigma SIGMA_CONTRASTE_LOCAL), antes da curva:
SIGMA_CONTRASTE_LOCAL = 5.0  # separa mais a face clara da escura vizinha (aspecto metalico) sem mudar o histograma
PERFIL_CURVA = 0.25        # 0 = face plana (vanilla: faces chapadas), 1 = arco de circulo antigo
VARIACAO_LARGURA = 0.35    # fracao da largura do chanfro que varia ao longo do contorno (ruido de baixa frequencia)
SIGMA_LARGURA = 9.0        # px: comprimento das variacoes de largura
ONDULACAO_ARESTA = 0.15    # fracao da largura: ondulacao fina da aresta interna (chanfro -> topo)
SIGMA_ONDULACAO = 2.5      # px
DESVIO_CRISTA = 3.0        # px (teto) que a crista (encontro das faces) se afasta do eixo medio do traco
DESVIO_RELATIVO = 0.12     # desvio da crista como fracao da meia espessura do traco
RAIO_CRISTA = (17.0, 23.0)  # meia espessura (px) abaixo da qual o traco vira crista de duas faces, e acima da qual tem topo
RAIO_JANELA = 22           # px: janela para medir a meia espessura local
DOMO_TOPO = 0.05           # px/px de abaulado do topo no sombreado do chanfro (o topo vanilla e quase plano)
SIGMA_DESLOCAMENTO = 1.5   # px: desfoque da mascara usado para desloca-la sem outra transformada de distancia
SIGMA_CRISTA = 10.0        # px: comprimento das ondulacoes da crista
PASSO_FACETA = 22.5        # graus: a direcao da face e quantizada em planos, como pedra lascada
FACETAMENTO = 0.7          # 0 = faces curvas que seguem o contorno, 1 = planos com quebras secas
SIGMA_FACETA = 40.0        # px: ruido lento que desloca as quebras entre facetas (constante na espessura do traco)
SIGMA_ORIENTACAO = 4.0     # px: suavizacao da orientacao do contorno usada para escolher o plano
NORMA_MINIMA_DIRECAO = 0.3  # abaixo disso a direcao nao e normalizada: crista nitida (~1 px) sem ruido no eixo
MARGEM = 8                 # folga em volta da silhueta para a erosao e o desfoque
DISTANCIA_MAXIMA = 24
DISTANCIA_MAXIMA_CHANFRO = 80   # teto da distancia a borda quando o chanfro e maximo (tracos largos, como a lanca)

# (brilho, R/G, B/G) medidas na arma do glifo vanila: escuros mais saturados, claros quase brancos
TINTA = np.array([
    (75, 1.173, 0.840), (103, 1.149, 0.866), (126, 1.138, 0.872), (152, 1.128, 0.878),
    (185, 1.107, 0.890), (217, 1.079, 0.902), (247, 1.018, 0.949), (255, 1.009, 0.962),
])

def _distancia_a_borda(dentro, limite=DISTANCIA_MAXIMA):
    """Distancia euclidiana continua da borda para dentro; 0.5 px no contorno.

    Exata ate `limite`: a passada horizontal e exata e a vertical so olha |dy| <= alcance, pois alem disso o
    resultado ja seria cortado no limite."""
    dentro = np.asarray(dentro, bool)
    fora = np.pad(~dentro, 1, mode="constant", constant_values=True)
    altura, largura = fora.shape
    colunas = np.broadcast_to(np.arange(largura, dtype=np.int64), fora.shape)
    anterior = np.maximum.accumulate(np.where(fora, colunas, -largura), axis=1)
    seguinte = np.minimum.accumulate(np.where(fora, colunas, 2 * largura)[:, ::-1], axis=1)[:, ::-1]
    horizontal = np.minimum(colunas - anterior, seguinte - colunas)
    alcance = int(np.ceil(limite)) + 1
    longe = alcance * alcance + 1
    quadrado = np.minimum(horizontal, alcance + 1) ** 2
    melhor = quadrado.copy()
    for dy in range(1, min(alcance, altura - 1) + 1):
        custo = dy * dy
        np.minimum(melhor[dy:], quadrado[:-dy] + custo, out=melhor[dy:])
        np.minimum(melhor[:-dy], quadrado[dy:] + custo, out=melhor[:-dy])
    distancia_quadrada = np.minimum(melhor, longe).astype(np.float32)
    distancia = np.maximum(np.sqrt(distancia_quadrada) - 0.5, 0.5)[1:-1, 1:-1]
    distancia[~dentro] = 0
    return np.minimum(distancia, limite).astype(np.float32)


def _desfocar(imagem, sigma):
    """Desfoque gaussiano separavel de uma matriz float."""
    raio = int(np.ceil(3 * sigma))
    nucleo = np.exp(-0.5 * (np.arange(-raio, raio + 1) / sigma) ** 2)
    nucleo /= nucleo.sum()
    for _ in range(2):
        # cada passada desfoca as linhas e transpoe: as fatias ficam contiguas, a aritmetica nao muda
        preenchida = np.pad(imagem, [(raio, raio), (0, 0)], mode="edge")
        n = imagem.shape[0]
        saida = np.zeros(imagem.shape, np.result_type(nucleo, preenchida))
        termo = np.empty_like(saida)
        for i, peso in enumerate(nucleo):
            np.multiply(peso, preenchida[i:i + n], out=termo)
            saida += termo
        imagem = np.ascontiguousarray(saida.T)
    return imagem


def _maximo_local(matriz, raio):
    """Maximo da matriz numa janela quadrada de lado 2*raio+1."""
    for eixo in (0, 1):
        origem = matriz
        matriz = origem.copy()
        for passo in range(1, raio + 1):
            frente = [slice(None)] * 2
            tras = [slice(None)] * 2
            frente[eixo], tras[eixo] = slice(passo, None), slice(None, -passo)
            matriz[tuple(frente)] = np.maximum(matriz[tuple(frente)], origem[tuple(tras)])
            matriz[tuple(tras)] = np.maximum(matriz[tuple(tras)], origem[tuple(frente)])
    return matriz


def _largura_local(distancia, maximo=False):
    """Estima a espessura local do traco e limita a face chanfrada a ela (`maximo`: usa a espessura inteira)."""
    if maximo:
        return np.maximum(2.0, _desfocar(_maximo_local(distancia, int(np.ceil(distancia.max()))), 3.0))
    distancia_codificada = Image.fromarray(np.clip(distancia * 8, 0, 255).astype(np.uint8), "L")
    raio_local = np.asarray(distancia_codificada.filter(ImageFilter.MaxFilter(31)), np.float32) / 8
    return np.minimum(LARGURA_CHANFRO, np.maximum(2.0, raio_local * FATOR_CHANFRO_LOCAL))


def _direcao_da_borda(distancia, dentro):
    """Gradiente (y, x) da distancia desfocada so dentro da silhueta: direcao da normal sem os degraus de pixel."""
    interior = dentro.astype(np.float32)
    desfocada = _desfocar(distancia * interior, SUAVIZACAO_DIRECAO) / np.maximum(_desfocar(interior, SUAVIZACAO_DIRECAO), 1e-3)
    return np.gradient(desfocada)


def _altura_do_chanfro(distancia, largura_local, intensidade, domo=DOMO):
    return (largura_local * _perfil(np.clip(distancia / largura_local, 0, 1)) + domo * distancia) * intensidade


def _inclinacao(distancia, largura_local, intensidade, domo=DOMO):
    """Subida da altura por px de distancia a borda, medida na distancia nitida (o chanfro continua marcado)."""
    return (_altura_do_chanfro(distancia + 0.5, largura_local, intensidade, domo)
            - _altura_do_chanfro(np.maximum(distancia - 0.5, 0), largura_local, intensidade, domo))


def _largura_forma(distancia, fator, largura_chanfro):
    """Largura irregular do chanfro: tracos finos (meia espessura < RAIO_CRISTA) viram duas faces ate o eixo, como
    o cabo do martelo vanilla; nas partes largas o chanfro tem `largura_chanfro` vezes o fator irregular."""
    raio = np.maximum(2.0, _desfocar(_maximo_local(distancia, RAIO_JANELA), 2.0))
    transicao = np.clip((raio - RAIO_CRISTA[0]) / (RAIO_CRISTA[1] - RAIO_CRISTA[0]), 0, 1)
    largura = (1 - transicao) * raio * FATOR_CHANFRO_LOCAL + transicao * largura_chanfro * fator
    return np.minimum(largura, raio * FATOR_CHANFRO_LOCAL), raio


def _ruido_oitavas(forma, dentro, gerador, sigmas, pesos):
    """Soma de ruidos suaves (uma oitava por sigma), desvio padrao 1 dentro da silhueta."""
    soma = sum(peso * _ruido(forma, dentro, gerador, sigma) for sigma, peso in zip(sigmas, pesos))
    return soma / max(float(soma[dentro].std()), 1e-6)


def _facetas_forja(dentro, direcao_y, direcao_x, gerador):
    """Gradiente (y, x) constante por celula de Voronoi: planos batidos grandes com quebra de angulo entre eles.

    Cada faceta inclina sobretudo ao longo do traco (lombada: as duas aguas sobem juntas) e gira as aguas em
    sentidos opostos (torcao: `direcao` troca de sinal na aresta), quase sem inclinar atravessando o traco."""
    pontos = np.argwhere(dentro)
    quantidade = max(4, round(len(pontos) / (TAMANHO_FACETA * TAMANHO_FACETA)))
    sementes = pontos[gerador.integers(len(pontos), size=quantidade)].astype(np.float32)
    sorteio = gerador.normal(0, 1, (quantidade, 4)).astype(np.float32)
    yy, xx = np.mgrid[0:dentro.shape[0], 0:dentro.shape[1]].astype(np.float32)
    melhor = np.full(dentro.shape, np.inf, np.float32)
    rotulo = np.zeros(dentro.shape, np.int32)
    for indice, (sy, sx) in enumerate(sementes):
        d2 = (yy - sy) ** 2 + (xx - sx) ** 2
        menor = d2 < melhor
        melhor[menor] = d2[menor]
        rotulo[menor] = indice
    # eixo do traco pelo tensor de estrutura (a direcao da borda troca de sinal na aresta; o eixo nao)
    interior = dentro.astype(np.float32)
    sxx = _desfocar(direcao_x * direcao_x * interior, SIGMA_EIXO)
    syy = _desfocar(direcao_y * direcao_y * interior, SIGMA_EIXO)
    sxy = _desfocar(direcao_x * direcao_y * interior, SIGMA_EIXO)
    angulo = 0.5 * np.arctan2(2 * sxy, sxx - syy)
    atraves_x, atraves_y = np.cos(angulo), np.sin(angulo)
    tilt_y, tilt_x = sorteio[rotulo, 0], sorteio[rotulo, 1]
    componente = tilt_x * atraves_x + tilt_y * atraves_y
    tilt_x = tilt_x - (1 - FACETA_ATRAVES) * componente * atraves_x
    tilt_y = tilt_y - (1 - FACETA_ATRAVES) * componente * atraves_y
    norma = np.maximum(np.hypot(direcao_x, direcao_y), 0.5)
    torcao = sorteio[rotulo, 2] * TORCAO
    tilt_x = tilt_x - torcao * direcao_y / norma
    tilt_y = tilt_y + torcao * direcao_x / norma
    return _desfocar(tilt_y, SUAVIZACAO_FACETA), _desfocar(tilt_x, SUAVIZACAO_FACETA)


def _organicidade(dentro):
    """0..ORGANICO_MAXIMO: quao torto e o contorno em volta (curvatura media da borda espalhada para dentro).

    Tracos de contorno liso (lanca, arco) ficam perto de ORGANICO_MINIMO e mantem a nervura reta; os de
    contorno nodoso (cajado, cabo do martelo) ganham aresta serpenteando e facetas fortes."""
    suave = _desfocar(dentro.astype(np.float32), 2.0)
    gy, gx = np.gradient(suave)
    norma = np.hypot(gx, gy) + 1e-6
    curvatura = np.abs(np.gradient(gx / norma, axis=1) + np.gradient(gy / norma, axis=0))
    borda = (norma > 0.05).astype(np.float32)
    media = _desfocar(curvatura * borda, SIGMA_ORGANICO) / np.maximum(_desfocar(borda, SIGMA_ORGANICO), 1e-3)
    return np.clip((media - CURVATURA_LISA) / (CURVATURA_NODOSA - CURVATURA_LISA), ORGANICO_MINIMO, ORGANICO_MAXIMO)


def _relevo_forja(distancia, dentro, planalto, organico, intensidade, gerador):
    """Inclinacao (y, x) do relevo de forja: ondulacao lenta e facetas grandes (Voronoi).

    As facetas sao fortes nos tracos de contorno nodoso (cajado, cabo do martelo) e no topo plano (`planalto`),
    e quase somem nos tracos lisos (lanca, arco), que mantem as faces chapadas do chanfro."""
    forma = distancia.shape
    direcao_y, direcao_x = _direcao_da_borda(distancia, dentro)
    ondulacao = _ruido_oitavas(forma, dentro, gerador, SIGMAS_ONDULACAO, PESOS_ONDULACAO)
    oy, ox = np.gradient(ondulacao)
    escala = ONDULACAO / max(float(np.hypot(oy, ox)[dentro].std()), 1e-6)
    fy, fx = _facetas_forja(dentro, direcao_y, direcao_x, gerador)
    modulacao = intensidade * np.clip((distancia - 1.0) / ENTRADA_MACRO, 0, 1)
    forca_faceta = FACETA * np.maximum(organico, FACETA_PLANALTO * planalto)
    escala = escala * (1 + (ONDULACAO_PLANALTO - 1) * planalto)
    return (oy * escala + fy * forca_faceta) * modulacao, (ox * escala + fx * forca_faceta) * modulacao


def _perfil(fracao):
    """Altura 0..1 em funcao da fracao 0..1 do caminho borda -> topo: face quase plana (pouco arco) e topo chato."""
    return (1 - PERFIL_CURVA) * fracao + PERFIL_CURVA * np.sqrt(1 - (1 - fracao) ** 2)


def _geometria_irregular(dentro, distancia, limite, gerador, organico):
    """Distancia com a crista deslocada e fator de largura do chanfro, ambos irregulares ao longo do contorno.

    A crista e o eixo medio de uma silhueta inflada/encolhida por um ruido suave (DESVIO_CRISTA): no contorno real
    a distancia continua ~0, mas o encontro das faces passa a serpentear como no vanilla."""
    raio = _desfocar(_maximo_local(distancia, RAIO_JANELA), 2.0)
    # so os tracos de contorno nodoso serpenteiam; nos lisos (arco, lanca) a crista deslocada vira manchas
    desvio = (_ruido(dentro.shape, dentro, gerador, SIGMA_CRISTA) * np.clip(DESVIO_RELATIVO * raio, 0.5, DESVIO_CRISTA)
              * np.clip((organico - ORGANICO_MINIMO) / (1 - ORGANICO_MINIMO), 0, 1))
    # silhueta deslocada desvio px para fora (ou para dentro): limiar da mascara desfocada (aprox. logistica da gaussiana)
    desfocada = _desfocar(dentro.astype(np.float32), SIGMA_DESLOCAMENTO)
    deslocada = desfocada > 1 / (1 + np.exp(1.702 * desvio / SIGMA_DESLOCAMENTO))
    distancia_crista = _distancia_a_borda(deslocada, limite + DESVIO_CRISTA * 4)
    efetiva = np.where(deslocada & dentro, distancia_crista - desvio, distancia)
    efetiva = np.where(dentro, np.clip(efetiva, 0.5, limite), 0).astype(np.float32)
    largura = (1 + VARIACAO_LARGURA * _ruido(dentro.shape, dentro, gerador, SIGMA_LARGURA)
               + ONDULACAO_ARESTA * _ruido(dentro.shape, dentro, gerador, SIGMA_ONDULACAO))
    fase = _ruido(dentro.shape, dentro, gerador, SIGMA_FACETA)
    return efetiva, np.clip(largura, 0.5, 1.7).astype(np.float32), fase


def _facetar(direcao_y, direcao_x, fase, peso=1.0):
    """Normaliza a direcao (crista nitida) e gira cada trecho do contorno para o plano mais proximo (PASSO_FACETA).

    O giro vem da orientacao (eixo, modulo 180 graus) suavizada do contorno: as duas faces de um traco giram juntas
    e a quebra entre planos atravessa o traco inteiro, em vez de manchas soltas."""
    norma = np.hypot(direcao_y, direcao_x)
    escala = 1 / np.maximum(norma, NORMA_MINIMA_DIRECAO)
    angulo = np.arctan2(direcao_y, direcao_x)
    cosseno = _desfocar(norma * np.cos(2 * angulo), SIGMA_ORIENTACAO)
    seno = _desfocar(norma * np.sin(2 * angulo), SIGMA_ORIENTACAO)
    passo = np.radians(PASSO_FACETA)
    eixo = np.arctan2(seno, cosseno) / 2 + fase * passo * 0.5
    giro = _desfocar((np.round(eixo / passo) * passo - eixo).astype(np.float32), 0.7)
    angulo = angulo + FACETAMENTO * giro * peso
    modulo = norma * escala
    return modulo * np.sin(angulo), modulo * np.cos(angulo)


def _curva_tonal(brilho):
    """Aplica CURVA_TOM (monotona: preserva a ordem dos tons e as formas), estendida linearmente abaixo do 1o ponto."""
    x, y = CURVA_TOM[:, 0], CURVA_TOM[:, 1]
    resultado = np.interp(brilho, x, y)
    resultado = np.where(brilho < x[0], y[0] + (brilho - x[0]) * (y[1] - y[0]) / (x[1] - x[0]), resultado)
    return np.clip(resultado, 0, 255)


def _colorir(brilho):
    """Cinza (H, W) -> RGB com a tinta bege do vanilla, que depende do brilho."""
    vermelho_sobre_verde = np.interp(brilho, TINTA[:, 0], TINTA[:, 1])
    azul_sobre_verde = np.interp(brilho, TINTA[:, 0], TINTA[:, 2])
    verde = brilho / ((vermelho_sobre_verde + 1 + azul_sobre_verde) / 3)
    return np.dstack([verde * vermelho_sobre_verde, verde, verde * azul_sobre_verde])


@dataclass(frozen=True)
class Acabamento:
    """Ajustes do usuario; os padroes reproduzem o visual original. semente != 0 muda a distribuicao aleatoria."""
    forjado: float = 1.0   # densidade dos amassados (0 = sem forjado)
    tamanho: float = 1.0   # escala do raio dos amassados
    riscos: float = 1.0    # densidade dos riscos
    brilho: float = 1.0    # escala do brilho especular
    semente: int = 0


def _semente(mascara):
    import hashlib
    dados = np.ascontiguousarray(mascara, dtype=np.uint8).tobytes()
    return int.from_bytes(hashlib.blake2b(dados, digest_size=8).digest(), "little")


def _componente(regiao, ponto):
    """Parte da mascara ligada (4 vizinhos) ao pixel `ponto` (y, x)."""
    visitados = np.zeros(regiao.shape, bool)
    pilha = [(int(ponto[0]), int(ponto[1]))]
    visitados[pilha[0]] = True
    while pilha:
        y, x = pilha.pop()
        for vy, vx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= vy < regiao.shape[0] and 0 <= vx < regiao.shape[1] and regiao[vy, vx] and not visitados[vy, vx]:
                visitados[vy, vx] = True
                pilha.append((vy, vx))
    return visitados


def _adicionar_amassados(altura, marcas, luzes, dentro, distancia, largura_local, intensidade, gerador,
                         densidade=1.0, escala_raio=1.0):
    """Martelado: calotas encaixadas (das maiores as menores) que se cortam em cristas e podem morder o chanfro.

    Cada calota tem contorno entre elipse e poligono; onde duas se sobrepoem vale a mais funda, o que deixa uma aresta
    viva entre elas. Devolve a profundidade (>= 0); a altura e rebaixada por ela."""
    relevo = np.zeros(altura.shape, np.float32)
    raio_minimo, raio_maximo = (raio * escala_raio for raio in RAIO_AMASSADO)
    elegivel = dentro & (distancia >= largura_local + ALCANCE_AMASSADO * raio_minimo + FOLGA_BORDA_AMASSADO)
    pontos = np.argwhere(elegivel)
    if not len(pontos):
        return relevo
    quantidade = max(1, round(int(dentro.sum()) * AMASSADOS_POR_AREA * densidade))
    sorteio = pontos[gerador.integers(len(pontos), size=CANDIDATOS_AMASSADO)]
    raios = raio_minimo + (raio_maximo - raio_minimo) * gerador.random(CANDIDATOS_AMASSADO) ** EXPOENTE_RAIO_AMASSADO
    cabe = (distancia[sorteio[:, 0], sorteio[:, 1]] - largura_local[sorteio[:, 0], sorteio[:, 1]]
            - FOLGA_BORDA_AMASSADO) / ALCANCE_AMASSADO
    raios = np.minimum(raios, cabe)
    ordem = np.argsort(-raios)
    # pecas largas pequenas (pomo, ponta do cabo) levam no maximo um amassado; o martelado fica nas cabecas
    nucleo = distancia >= NUCLEO_AMASSADO
    rotulo = np.full(altura.shape, -1, np.int32)
    vagas = []
    for y, x in np.argwhere(nucleo):
        if rotulo[y, x] < 0:
            componente = _componente(nucleo, (y, x))
            rotulo[componente] = len(vagas)
            vagas.append(quantidade if componente.sum() >= AREA_NUCLEO_PEQUENO else 0)
    rotulo = np.where(rotulo >= 0, rotulo, np.argmax(vagas) if vagas else -1)
    centros = np.empty((0, 2), np.float32)
    raios_colocados = np.empty(0, np.float32)
    for indice in ordem:
        if len(centros) >= quantidade:
            break
        raio = raios[indice]
        if raio < raio_minimo:
            break
        centro = sorteio[indice].astype(np.float32)
        peca = rotulo[sorteio[indice][0], sorteio[indice][1]]
        if peca >= 0 and vagas[peca] <= 0:
            continue
        if len(centros):
            afastamento = np.hypot(*(centros - centro).T)
            if np.any(afastamento < SOBREPOSICAO_AMASSADO * (raios_colocados + raio)):
                continue
        centros = np.vstack([centros, centro])
        if peca >= 0:
            vagas[peca] -= 1
        raios_colocados = np.append(raios_colocados, raio)
    altura_total, largura_total = altura.shape
    for (centro_y, centro_x), raio_x in zip(centros.astype(int), raios_colocados):
        raio_y = raio_x * gerador.uniform(*ACHATAMENTO_AMASSADO)
        angulo = gerador.uniform(0, np.pi)
        margem = int(np.ceil(raio_x * (1 + IRREGULARIDADE_AMASSADO) + 2))
        x0, x1 = max(0, centro_x - margem), min(largura_total, centro_x + margem + 1)
        y0, y1 = max(0, centro_y - margem), min(altura_total, centro_y + margem + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dx, dy = (xx - centro_x).astype(np.float32), (yy - centro_y).astype(np.float32)
        eixo_x = (dx * np.cos(angulo) + dy * np.sin(angulo)) / raio_x
        eixo_y = (-dx * np.sin(angulo) + dy * np.cos(angulo)) / raio_y
        eliptico = np.sqrt(eixo_x * eixo_x + eixo_y * eixo_y)
        lados = int(gerador.integers(5, 8))
        giro = gerador.uniform(0, 2 * np.pi)
        faces = giro + 2 * np.pi * (np.arange(lados) + gerador.uniform(-0.2, 0.2, lados)) / lados
        recuos = gerador.uniform(0.9, 1.1, lados) * np.cos(np.pi / lados)
        # norma p dos recuos: contorno de poligono com cantos e miolo liso (o max puro deixa vincos de piramide)
        poligonal = sum(np.maximum((eixo_x * np.cos(f) + eixo_y * np.sin(f)) / r, 0) ** EXPOENTE_POLIGONO_AMASSADO
                        for f, r in zip(faces, recuos)) ** (1 / EXPOENTE_POLIGONO_AMASSADO)
        mistura = gerador.uniform(*FACETAMENTO_AMASSADO)
        normalizado = (1 - mistura) * eliptico + mistura * poligonal
        direcao = np.arctan2(eixo_y, eixo_x)
        normalizado /= 1 + IRREGULARIDADE_AMASSADO * np.cos(2 * direcao + gerador.uniform(0, 6.3))
        profundidade = raio_x * gerador.uniform(*PROFUNDIDADE_AMASSADO) * intensidade
        # fundo deslocado para o lado da luz: parede escura curta e ingreme, parede clara longa (golpe inclinado)
        rumo = np.radians(ANGULO_LUZ) + gerador.uniform(-0.35, 0.35)
        para_luz = np.clip((dx * np.cos(rumo) + dy * np.sin(rumo)) / raio_x, -1, 1)
        assimetria = gerador.uniform(*ASSIMETRIA_AMASSADO)
        calota = profundidade * np.maximum(1 - normalizado ** PERFIL_AMASSADO, 0) * (1 + assimetria * para_luz) / (1 + assimetria / 2)
        recorte = np.s_[y0:y1, x0:x1]
        relevo[recorte] = np.maximum(relevo[recorte], calota)
    # sulcos nunca invadem o chanfro: so valem no topo plano
    relevo *= np.clip(distancia - largura_local, 0, 1) * dentro
    altura -= relevo
    return relevo


def _adicionar_veios_martelo(altura, marcas, luzes, dentro, distancia, largura_local, intensidade, gerador):
    residual = dentro & (distancia > largura_local + 1)
    pontos = np.argwhere(residual)
    quantidade = min(36, round(len(pontos) * VEIOS_POR_AREA))
    if not len(pontos):
        return

    altura_risco, largura_risco = altura.shape
    for _ in range(quantidade):
        centro_y, centro_x = pontos[gerador.integers(len(pontos))]
        comprimento = gerador.uniform(8.0, 20.0)
        largura = gerador.uniform(1.0, 2.2)
        angulo = gerador.uniform(0, np.pi)
        raio = int(np.ceil(comprimento / 2 + largura * 3 + 1))
        x0, x1 = max(0, centro_x - raio), min(largura_risco, centro_x + raio + 1)
        y0, y1 = max(0, centro_y - raio), min(altura_risco, centro_y + raio + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dx, dy = xx - centro_x, yy - centro_y
        ao_longo = dx * np.cos(angulo) + dy * np.sin(angulo)
        atraves = -dx * np.sin(angulo) + dy * np.cos(angulo)
        fim = np.clip((comprimento / 2 - np.abs(ao_longo)) / max(largura * 1.3, 1), 0, 1)
        nucleo = np.exp(-((atraves / largura) ** 2)) * fim
        recorte = np.s_[y0:y1, x0:x1]
        regiao_residual = residual[recorte]
        altura[recorte] -= nucleo * intensidade * gerador.uniform(0.8, 1.6) * regiao_residual
        marcas[recorte] = np.maximum(marcas[recorte], nucleo * gerador.uniform(7, 13) * regiao_residual)
        aro = np.exp(-(((np.abs(atraves) - largura * 1.6) / max(largura * 0.65, 0.5)) ** 2)) * fim
        luzes[recorte] = np.maximum(luzes[recorte], aro * gerador.uniform(3, 6) * regiao_residual)


def _suavizar_dentro(brilho, dentro, sigma):
    """Desfoque que so mistura pixels da silhueta, sem puxar o tom do fundo para a borda."""
    if sigma <= 0:
        return brilho
    interior = dentro.astype(np.float32)
    return _desfocar(brilho * interior, sigma) / np.maximum(_desfocar(interior, sigma), 1e-3) * interior + brilho * (1 - interior)


def _amostrar(imagem, y, x):
    """Interpolacao bilinear de `imagem` nas posicoes (y, x), presas a borda."""
    altura, largura = imagem.shape
    y = np.clip(y, 0, altura - 1.001)
    x = np.clip(x, 0, largura - 1.001)
    y0, x0 = y.astype(np.int32), x.astype(np.int32)
    fy, fx = y - y0, x - x0
    plana = imagem.ravel()
    indice = y0 * largura + x0
    return ((plana.take(indice) * (1 - fx) + plana.take(indice + 1) * fx) * (1 - fy)
            + (plana.take(indice + largura) * (1 - fx) + plana.take(indice + largura + 1) * fx) * fy)


def _campo_tangente(distancia, dentro):
    """Direcao (y, x) unitaria ao longo do contorno, definida tambem no miolo (media do angulo dobrado)."""
    gradiente_y, gradiente_x = _direcao_da_borda(distancia, dentro)
    angulo = 2 * np.arctan2(gradiente_y, gradiente_x)
    peso = np.hypot(gradiente_y, gradiente_x)
    cosseno = _desfocar(np.cos(angulo) * peso, SUAVIZACAO_ORIENTACAO)
    seno = _desfocar(np.sin(angulo) * peso, SUAVIZACAO_ORIENTACAO)
    normal = 0.5 * np.arctan2(seno, cosseno)
    return np.cos(normal), -np.sin(normal)   # tangente = normal girada 90 graus


def _ruido_orientado(forma, dentro, gerador, tangente, sigma_atraves, sigma_ao_longo):
    """Ruido gaussiano esticado ao longo do contorno: estrias de lixa/escova que acompanham o chanfro."""
    ruido = _desfocar(gerador.normal(0, 1, forma).astype(np.float32), sigma_atraves)
    tangente_y, tangente_x = tangente
    yy, xx = np.mgrid[0:forma[0], 0:forma[1]].astype(np.float32)
    passos = np.arange(-np.ceil(2.5 * sigma_ao_longo), np.ceil(2.5 * sigma_ao_longo) + 1)
    pesos = np.exp(-0.5 * (passos / sigma_ao_longo) ** 2)
    soma = None
    for passo, peso in zip(passos, pesos):
        termo = _amostrar(ruido, yy + passo * tangente_y, xx + passo * tangente_x)
        termo *= peso
        if soma is None:
            soma = termo
        else:
            soma += termo
    return soma / max(float(soma[dentro].std()), 1e-6)


def _assimetrico(ruido, inclinacao):
    """Desvia a cauda do ruido: inclinacao > 0 gera pontos claros raros, < 0 manchas escuras raras."""
    torto = ruido + inclinacao * np.maximum(ruido * np.sign(inclinacao), 0) ** 2 * np.sign(inclinacao)
    return (torto - torto.mean()) / max(float(torto.std()), 1e-6)


def _textura(brilho, dentro, gerador, distancia, altura, tangente):
    """Textura que segue a forma, somada ao tom antes do ombro das luzes.

    Manchas esticadas ao longo do contorno e escuras na cauda, sujeira nas cavidades (altura abaixo da vizinha),
    desgaste claro e liso nas pontas convexas e bordas das faces lascadas (o tom e deslocado por ruido)."""
    interior = dentro.astype(np.float32)
    # bordas entre faces levemente onduladas/lascadas: desloca o tom por ruido, so muda onde o tom muda depressa
    yy, xx = np.mgrid[0:brilho.shape[0], 0:brilho.shape[1]].astype(np.float32)
    deslocamento_y, deslocamento_x = (
        _ruido(brilho.shape, dentro, gerador, SIGMA_LASCAS) * LASCAS
        + _ruido(brilho.shape, dentro, gerador, SIGMA_LASCAS_FINAS) * LASCAS_FINAS for _ in range(2))
    deslocado = _amostrar(brilho, yy + deslocamento_y, xx + deslocamento_x)
    seguro = np.clip(distancia - 1.5, 0, 1)
    brilho = brilho * (1 - seguro) + deslocado * seguro
    manchas = (_assimetrico(_ruido_orientado(brilho.shape, dentro, gerador, tangente, SIGMA_MANCHAS * 0.6,
                                             SIGMA_MANCHAS * 1.6), ASSIMETRIA_MANCHAS) * MANCHAS
               + _assimetrico(_ruido(brilho.shape, dentro, gerador, SIGMA_MANCHAS_GRANDES), ASSIMETRIA_MANCHAS)
               * MANCHAS_GRANDES)
    # cavidade: quanto o relevo dos detalhes fica abaixo da vizinhanca (amassados, veios)
    vizinha = _desfocar(altura * interior, SIGMA_CAVIDADE) / np.maximum(_desfocar(interior, SIGMA_CAVIDADE), 1e-3)
    cavidade = np.clip((vizinha - altura) / ESCALA_CAVIDADE, 0, 1)
    # cantos: mais (concavo) ou menos (ponta convexa) silhueta em volta do que numa borda reta a mesma distancia
    z = distancia / SIGMA_PONTA
    borda_reta = 0.5 * (1 + np.tanh(0.7978 * (z + 0.044715 * z ** 3)))
    excesso = _desfocar(interior, SIGMA_PONTA) - borda_reta
    perto_da_borda = np.clip(1 - distancia / 6, 0, 1)
    ponta = _desfocar(np.clip(-excesso / ESCALA_CANTO, 0, 1) * perto_da_borda, 1.0)
    canto = _desfocar(np.clip(excesso / ESCALA_CANTO, 0, 1) * perto_da_borda, 1.5)
    sujeira = np.maximum(cavidade, canto) * np.clip(1 + 0.8 * _ruido(brilho.shape, dentro, gerador, 1.8), 0, 2.5)
    luz = np.clip((brilho - JOELHO_LUZ + 30) / 50, 0, 1)
    variacao = manchas * (1 - 0.85 * ponta) * (1 - ATENUACAO_MANCHAS_LUZ * luz) - SUJEIRA * sujeira + DESGASTE * ponta
    variacao -= float(variacao[dentro].mean())
    return brilho + variacao * dentro, ponta


def _craquelado(forma, dentro, gerador):
    """Fragmentos de uma rede de veios claros (bordas de celulas de Voronoi), so em parte da superficie."""
    lado = TAMANHO_CRAQUELADO
    linhas, colunas = int(np.ceil(forma[0] / lado)) + 2, int(np.ceil(forma[1] / lado)) + 2
    pontos = (np.stack(np.mgrid[0:linhas, 0:colunas], -1) - 1 + gerador.uniform(0.1, 0.9, (linhas, colunas, 2))) * lado
    yy, xx = np.mgrid[0:forma[0], 0:forma[1]].astype(np.float32)
    celula_y, celula_x = (yy // lado).astype(np.int32) + 1, (xx // lado).astype(np.int32) + 1
    primeira = np.full(forma, np.inf, np.float32)
    segunda = np.full(forma, np.inf, np.float32)
    for vy in (-1, 0, 1):
        for vx in (-1, 0, 1):
            ponto = pontos[np.clip(celula_y + vy, 0, linhas - 1), np.clip(celula_x + vx, 0, colunas - 1)]
            distancia = np.hypot(yy - ponto[..., 0], xx - ponto[..., 1])
            segunda = np.minimum(segunda, np.maximum(primeira, distancia))
            primeira = np.minimum(primeira, distancia)
    veios = np.exp(-0.5 * ((segunda - primeira) / LARGURA_CRAQUELADO) ** 2)
    trechos = np.clip((_ruido(forma, dentro, gerador, SIGMA_TRECHOS_CRAQUELADO) - 0.3) * 1.5, 0, 1)
    return veios * trechos * gerador.uniform(0.7, 1.0, forma).astype(np.float32)


def _aresta(distancia, largura_local):
    """0..1 sobre as cristas do chanfro (eixo medial onde as duas faces se encontram, laplaciano bem negativo)."""
    suave = _desfocar(distancia, 0.8)
    laplaciano = (np.gradient(np.gradient(suave, axis=0), axis=0)
                  + np.gradient(np.gradient(suave, axis=1), axis=1))
    crista = np.clip((-laplaciano - LIMIAR_ARESTA) / 0.3, 0, 1) * np.clip((distancia - 2) / 2, 0, 1)
    return crista * (distancia <= largura_local + 1.5)


def _marcas(forma, dentro, distancia, tangente, gerador, densidade_riscos=1.0):
    """Pocos escuros e riscos claros esparsos, os riscos quase paralelos ao contorno."""
    marcas = np.zeros(forma, np.float32)
    pontos = np.argwhere(dentro & (distancia >= 2))
    if not len(pontos):
        return marcas
    area = int(dentro.sum())
    tangente_y, tangente_x = tangente
    for _ in range(round(area * POCOS_POR_AREA)):
        centro_y, centro_x = pontos[gerador.integers(len(pontos))]
        sigma = gerador.uniform(*RAIO_POCO)
        y0, y1 = max(0, centro_y - 4), min(forma[0], centro_y + 5)
        x0, x1 = max(0, centro_x - 4), min(forma[1], centro_x + 5)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        ponto = np.exp(-0.5 * ((yy - centro_y) ** 2 + (xx - centro_x) ** 2) / sigma ** 2)
        marcas[y0:y1, x0:x1] -= ponto * gerador.uniform(*PROFUNDIDADE_POCO)
    for _ in range(round(area * RISCOS_POR_AREA * densidade_riscos)):
        centro_y, centro_x = pontos[gerador.integers(len(pontos))]
        base = np.arctan2(tangente_y[centro_y, centro_x], tangente_x[centro_y, centro_x])
        angulo = base + gerador.normal(0, DESVIO_RISCO)
        comprimento = gerador.uniform(*COMPRIMENTO_RISCO)
        largura = gerador.uniform(0.45, 0.75)
        raio = int(np.ceil(comprimento / 2 + 3))
        y0, y1 = max(0, centro_y - raio), min(forma[0], centro_y + raio + 1)
        x0, x1 = max(0, centro_x - raio), min(forma[1], centro_x + raio + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        dy, dx = yy - centro_y, xx - centro_x
        ao_longo = dx * np.cos(angulo) + dy * np.sin(angulo)
        atraves = -dx * np.sin(angulo) + dy * np.cos(angulo)
        fim = np.clip((comprimento / 2 - np.abs(ao_longo)) / 1.5, 0, 1)
        traco = np.exp(-0.5 * (atraves / largura) ** 2) * fim
        sinal = -1.4 if gerador.random() < FRACAO_RISCOS_ESCUROS else 1.0
        marcas[y0:y1, x0:x1] += sinal * traco * gerador.uniform(*BRILHO_RISCO)
    marcas += CRAQUELADO * _craquelado(forma, dentro, gerador)
    return marcas * dentro * np.clip(distancia - 1, 0, 1)


def _grao(brilho, dentro, gerador, tangente, marcas, ponta, aresta):
    """Grao fino (pontos claros raros) e estrias medias ao longo do contorno, somados depois do ombro.

    Somem nas luzes, que no vanilla sao cremes lisos, e no desgaste das pontas. Nas cristas, uma linha escura
    fina com lascas claras curtas atravessando-a (o "ziper" da lanca vanilla)."""
    variacao = (_assimetrico(_ruido(brilho.shape, dentro, gerador, SIGMA_GRAO), ASSIMETRIA_GRAO) * GRANULACAO
                + _ruido_orientado(brilho.shape, dentro, gerador, tangente, SIGMA_ESTRIAS, COMPRIMENTO_ESTRIAS)
                * GRANULACAO_MEDIA)
    # fios claros de escova/lixa ao longo do contorno, em tufos
    fios = np.maximum(_ruido_orientado(brilho.shape, dentro, gerador, tangente, SIGMA_FIOS, COMPRIMENTO_FIOS)
                      - LIMIAR_FIOS, 0)
    tufos = np.clip(_ruido(brilho.shape, dentro, gerador, SIGMA_TUFOS) + 0.2, 0, 1.5)
    variacao = variacao + FIOS * fios * tufos
    suave = _desfocar(brilho, 1.5)
    atenuacao = np.clip((LIMITE_GRAO - suave) / FAIXA_GRAO, GRAO_MINIMO_LUZ, 1) * (1 - 0.8 * ponta)
    visibilidade_marcas = np.clip((LIMITE_MARCAS - suave) / 50, 0.1, 1)
    normal = (-tangente[1], tangente[0])
    lascas = np.maximum(_ruido_orientado(brilho.shape, dentro, gerador, normal, 0.5, 1.2) - 0.3, 0)
    faixa = np.clip(_desfocar(aresta, 1.0) * 2.5, 0, 1)
    ziper = (ARESTA_LASCAS * lascas * faixa - ARESTA_ESCURA * _desfocar(aresta, 0.5)) * visibilidade_marcas
    return brilho + (variacao * atenuacao + marcas * visibilidade_marcas + ziper) * dentro


def _ruido(forma, dentro, gerador, sigma):
    """Ruido gaussiano desfocado, de desvio padrao 1 dentro da silhueta."""
    ruido = _desfocar(gerador.normal(0, 1, forma).astype(np.float32), sigma)
    return ruido / max(float(ruido[dentro].std()), 1e-6)


def normalizar(mascara):
    """Recorta a silhueta e a leva ao tamanho de referencia, em que o chanfro foi calibrado."""
    caixa = mascara.getbbox()
    if not caixa:
        raise ValueError("A silhueta esta vazia.")
    mascara = mascara.crop(caixa)
    escala = LADO_REFERENCIA / max(mascara.size)
    tamanho = (max(1, round(mascara.width * escala)), max(1, round(mascara.height * escala)))
    return mascara.resize(tamanho, Image.Resampling.LANCZOS)


def aplicar(mascara, largura_chanfro=LARGURA_CHANFRO, ganho_luz=GANHO_LUZ, intensidade=INTENSIDADE_PADRAO,
            nivel_chanfro=0.0, progresso=None, acabamento=Acabamento()):
    """RGBA com o chanfro; a mascara (ja no tamanho de referencia) vira o alfa.

    nivel_chanfro (0..1) e o efeito bevel: 0 limita o chanfro a `largura_chanfro` e deixa o topo plano; 1 leva o
    chanfro da borda ate o centro do traco (silhueta sem topo, com uma quina no meio).
    `progresso(fracao)` e chamado (0..1) ao fim de cada etapa."""
    avisar = progresso or (lambda fracao: None)
    chave = (mascara.mode, mascara.size, hashlib.blake2b(mascara.tobytes(), digest_size=16).digest(),
             float(largura_chanfro), float(ganho_luz), float(intensidade), float(nivel_chanfro), acabamento)
    with _CACHE_TRAVA:
        pronta = _CACHE.get(chave)
        if pronta is not None:
            _CACHE.move_to_end(chave)
    if pronta is not None:
        avisar(1.0)
        return pronta.copy()
    imagem = _aplicar(mascara, largura_chanfro, ganho_luz, intensidade, nivel_chanfro, avisar, acabamento)
    with _CACHE_TRAVA:
        _CACHE[chave] = imagem
        while len(_CACHE) > _CACHE_TAMANHO:
            _CACHE.popitem(last=False)
    return imagem.copy()


def _aplicar(mascara, largura_chanfro, ganho_luz, intensidade, nivel_chanfro, avisar, acabamento):
    intensidade = float(np.clip(intensidade, INTENSIDADE_MINIMA, INTENSIDADE_MAXIMA))
    densidade_amassados = float(np.clip(acabamento.forjado, 0, 3))
    escala_raio = float(np.clip(acabamento.tamanho, 0.3, 3))
    densidade_riscos = float(np.clip(acabamento.riscos, 0, 5))
    ganho_especular = GANHO_ESPECULAR * float(np.clip(acabamento.brilho, 0, 3))
    mascara = ImageOps.expand(mascara, MARGEM)
    dentro = np.asarray(mascara) >= 128
    nivel = float(np.clip(nivel_chanfro, 0, 1))
    limite = DISTANCIA_MAXIMA_CHANFRO if nivel > 0 else DISTANCIA_MAXIMA
    distancia = _distancia_a_borda(dentro, limite)
    avisar(0.15)
    largura_local = np.minimum(largura_chanfro, _largura_local(distancia))
    if nivel > 0:
        largura_local = (1 - nivel) * largura_local + nivel * _largura_local(distancia, True)
    altura_base = _altura_do_chanfro(distancia, largura_local, intensidade)
    altura = altura_base.copy()
    marcas = np.zeros(altura.shape, np.float32)
    luzes = np.zeros(altura.shape, np.float32)
    semente = _semente(mascara) ^ int(acabamento.semente)
    gerador = np.random.default_rng(semente)
    relevo_amassados = np.zeros(altura.shape, np.float32)
    # sulcos (amassados e veios) so nascem no topo plano; quanto maior o chanfro, menor o topo
    if densidade_amassados > 0:
        relevo_amassados = _adicionar_amassados(altura, marcas, luzes, dentro, distancia, largura_local,
                                                intensidade, gerador, densidade_amassados, escala_raio)
        _adicionar_veios_martelo(altura, marcas, luzes, dentro, distancia, largura_local, intensidade, gerador)
    altura = _desfocar(altura - altura_base, SUAVIZACAO_ALTURA)
    avisar(0.35)
    luz_x, luz_y = np.cos(np.radians(ANGULO_LUZ)), np.sin(np.radians(ANGULO_LUZ))
    # geometria irregular so no chanfro; amassados e veios continuam com a distancia/largura originais
    gerador_forma = np.random.default_rng(semente ^ 0x5F0A3C)
    organico = _organicidade(dentro)
    distancia_forma, fator_largura, fase = _geometria_irregular(dentro, distancia, limite, gerador_forma, organico)
    largura_forma, _ = _largura_forma(distancia_forma, fator_largura, largura_chanfro)
    if nivel > 0:
        largura_forma = (1 - nivel) * largura_forma + nivel * _largura_local(distancia_forma, True)
    # so o chanfro e facetado; o topo (quase plano) nao ganha quebras de plano
    no_chanfro = np.clip(largura_forma + 1.0 - distancia_forma, 0, 1)
    direcao_y, direcao_x = _facetar(*_direcao_da_borda(distancia_forma, dentro), fase, no_chanfro)
    inclinacao = _desfocar(_inclinacao(distancia_forma, largura_forma, intensidade, DOMO_TOPO), SUAVIZACAO_INCLINACAO)
    planalto = _desfocar(1 - no_chanfro, 2.5)
    macro_y, macro_x = _relevo_forja(distancia, dentro, planalto, organico, intensidade,
                                     np.random.default_rng(semente ^ 0x5EED0FF0A6E))
    gradiente_y, gradiente_x = np.gradient(altura)
    avisar(0.55)
    # normal da superficie a partir da inclinacao do chanfro, do relevo de forja e dos detalhes
    normal_x = -(inclinacao * direcao_x * CONTRASTE_CHANFRO + macro_x + gradiente_x * CONTRASTE_FACES)
    normal_y = -(inclinacao * direcao_y * CONTRASTE_CHANFRO + macro_y + gradiente_y * CONTRASTE_FACES)
    comprimento = np.sqrt(normal_x ** 2 + normal_y ** 2 + 1)
    elevacao = np.radians(ELEVACAO_LUZ)
    luz = np.array([luz_x * np.cos(elevacao), luz_y * np.cos(elevacao), np.sin(elevacao)])
    iluminacao = None
    for angulo in (ANGULO_LUZ - ABERTURA_LUZ, ANGULO_LUZ, ANGULO_LUZ + ABERTURA_LUZ):
        luz_lado = np.array([np.cos(np.radians(angulo)) * np.cos(elevacao),
                             np.sin(np.radians(angulo)) * np.cos(elevacao), np.sin(elevacao)])
        desvio = (normal_x * luz_lado[0] + normal_y * luz_lado[1] + luz_lado[2]) / comprimento - luz_lado[2]
        lado = np.clip(np.where(desvio > 0, desvio / (1 - luz_lado[2]), desvio / luz_lado[2]), -1, 1)
        iluminacao = lado if iluminacao is None else np.maximum(iluminacao, lado)
    meio = (luz + np.array([0, 0, 1.0]))
    meio /= np.linalg.norm(meio)
    especular = np.maximum((normal_x * meio[0] + normal_y * meio[1] + meio[2]) / comprimento, 0) ** EXPOENTE_ESPECULAR
    dentro_amassado = np.zeros(altura.shape, np.float32)
    no_amassado = np.zeros(altura.shape, np.float32)
    if relevo_amassados.any():
        # normal real da calota (sem o domo/chanfro por baixo): todo amassado fica escuro do lado da luz e claro do outro
        amassado_y, amassado_x = np.gradient(_desfocar(relevo_amassados, 0.5))
        normal_ax, normal_ay = amassado_x * CONTRASTE_AMASSADO, amassado_y * CONTRASTE_AMASSADO
        difuso_amassado = (normal_ax * luz[0] + normal_ay * luz[1] + luz[2]) / np.sqrt(normal_ax ** 2 + normal_ay ** 2 + 1)
        desvio_amassado = difuso_amassado - luz[2]
        no_amassado = np.clip(np.where(desvio_amassado > 0, desvio_amassado / (1 - luz[2]), desvio_amassado / luz[2]), -1, 1)
        dentro_amassado = np.clip(_desfocar((relevo_amassados > 0.05).astype(np.float32), 0.5) * 1.5, 0, 1)
        iluminacao = iluminacao * (1 - dentro_amassado) + no_amassado * dentro_amassado
    # a intensidade controla todo o efeito de luz: o contraste cresce linearmente ate o maximo do slider
    contraste = CONTRASTE_LUZ * (intensidade - INTENSIDADE_MINIMA) / (INTENSIDADE_MAXIMA - INTENSIDADE_MINIMA) + 0.15
    brilho = (BRILHO_BASE + contraste * ganho_luz * np.minimum(np.maximum(iluminacao, 0) / SATURACAO_LUZ, 1) ** EXPOENTE_LUZ
              - contraste * GANHO_SOMBRA * np.maximum(-iluminacao, 0) ** EXPOENTE_SOMBRA - marcas + luzes)
    if relevo_amassados.any():
        # a sombra extra so vale para a parede virada contra a luz (as laterais nao viram aro escuro)
        contra_luz = np.clip(-(normal_ax * luz_x + normal_ay * luz_y), 0, 1)
        brilho -= SOMBRA_EXTRA_AMASSADO * contra_luz * dentro_amassado
    brilho += ganho_especular * especular * (1 - dentro_amassado)
    brilho = _suavizar_dentro(brilho, dentro, SUAVIZACAO_TOM)
    avisar(0.7)
    brilho = brilho + CONTRASTE_LOCAL * (brilho - _suavizar_dentro(brilho, dentro, SIGMA_CONTRASTE_LOCAL)) * dentro
    tangente = _campo_tangente(distancia, dentro)
    brilho, ponta = _textura(brilho, dentro, gerador, distancia, altura, tangente)
    marcas_finas = _marcas(brilho.shape, dentro, distancia, tangente, gerador, densidade_riscos)
    aresta = _aresta(distancia_forma, largura_forma)
    avisar(0.85)
    brilho = _curva_tonal(brilho) + LUZ_EXTRA_AMASSADO * np.maximum(no_amassado, 0) * dentro_amassado
    rgb = _colorir(_grao(brilho, dentro, gerador, tangente, marcas_finas, ponta, aresta))
    croma = _ruido(brilho.shape, dentro, gerador, SIGMA_CROMA) * CROMA
    croma = croma + (_ruido(brilho.shape, dentro, gerador, SIGMA_CROMA_FINO) * CROMA_FINO
                     + _ruido(brilho.shape, dentro, gerador, SIGMA_CROMA_GROSSO) * CROMA_GROSSO)
    rgb[..., 0] += croma
    rgb[..., 2] -= croma
    rgb = np.clip(rgb, 0, 255)
    rgba = np.dstack([rgb, np.asarray(mascara, np.float32)]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA").crop((MARGEM, MARGEM, mascara.width - MARGEM, mascara.height - MARGEM))


def arma_chanfrada(mascara, lado_final, largura_chanfro=LARGURA_CHANFRO, ganho_luz=GANHO_LUZ,
                   intensidade=INTENSIDADE_PADRAO, nivel_chanfro=0.0, progresso=None,
                   acabamento=Acabamento()):
    """Silhueta -> arma chanfrada com o maior lado igual a `lado_final` (px)."""
    arma = aplicar(
        normalizar(mascara), largura_chanfro, ganho_luz, intensidade, nivel_chanfro, progresso, acabamento,
    )
    escala = lado_final / max(arma.size)
    tamanho = (max(1, round(arma.width * escala)), max(1, round(arma.height * escala)))
    return arma.resize(tamanho, Image.Resampling.LANCZOS)
