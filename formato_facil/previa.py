"""Pré-visualização: rasteriza o PDF real e desenha as cotas por cima.

A imagem mostrada é gerada a partir do mesmo PDF que será baixado, então o
que se vê é exatamente o que será impresso. As linhas de referência e cotas
existem apenas na imagem de pré-visualização.
"""

from __future__ import annotations

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

from . import fontes
from .geometria import A4_ALTURA_MM, A4_LARGURA_MM, Retangulo, formatar_mm

_AZUL = (37, 99, 235)
_LARANJA = (234, 88, 12)
_CINZA = (120, 120, 120)


def _fonte(tamanho_px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    disponiveis = fontes.fontes_disponiveis()
    for nome in ("Segoe UI", "Arial", fontes.FONTE_RESERVA):
        if nome in disponiveis:
            try:
                return ImageFont.truetype(str(disponiveis[nome]), tamanho_px)
            except OSError:
                continue
    return ImageFont.load_default()


def renderizar(dados_pdf: bytes, indice_pagina: int, dpi: float) -> Image.Image:
    with fitz.open(stream=dados_pdf, filetype="pdf") as documento:
        pagina = documento[min(indice_pagina, documento.page_count - 1)]
        zoom = dpi / 72.0
        pixmap = pagina.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def contar_paginas(dados_pdf: bytes) -> int:
    with fitz.open(stream=dados_pdf, filetype="pdf") as documento:
        return documento.page_count


def _tracejado(desenho: ImageDraw.ImageDraw, p1, p2, cor, largura=1, traco=8, vazio=5):
    (x1, y1), (x2, y2) = p1, p2
    comprimento = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    if comprimento == 0:
        return
    dx, dy = (x2 - x1) / comprimento, (y2 - y1) / comprimento
    pos = 0.0
    while pos < comprimento:
        fim = min(pos + traco, comprimento)
        desenho.line([(x1 + dx * pos, y1 + dy * pos), (x1 + dx * fim, y1 + dy * fim)], fill=cor, width=largura)
        pos += traco + vazio


def _retangulo_tracejado(desenho, caixa, cor, largura=1, traco=8, vazio=5):
    x0, y0, x1, y1 = caixa
    for p1, p2 in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        _tracejado(desenho, p1, p2, cor, largura, traco, vazio)


def _seta(desenho, p1, p2, cor, largura=1, ponta=6):
    desenho.line([p1, p2], fill=cor, width=largura)
    (x1, y1), (x2, y2) = p1, p2
    for (ax, ay), (bx, by) in (((x1, y1), (x2, y2)), ((x2, y2), (x1, y1))):
        comprimento = max(1e-6, ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5)
        ux, uy = (ax - bx) / comprimento, (ay - by) / comprimento
        px, py = -uy, ux
        desenho.polygon([(bx, by), (bx + ux * ponta + px * ponta / 2, by + uy * ponta + py * ponta / 2),
                         (bx + ux * ponta - px * ponta / 2, by + uy * ponta - py * ponta / 2)], fill=cor)


def _rotulo(desenho, centro, texto, fonte, cor, fundo=(255, 255, 255)):
    caixa = desenho.textbbox((0, 0), texto, font=fonte)
    w, h = caixa[2] - caixa[0], caixa[3] - caixa[1]
    x, y = centro[0] - w / 2, centro[1] - h / 2
    desenho.rectangle([x - 4, y - 3, x + w + 4, y + h + 5], fill=fundo)
    desenho.text((x - caixa[0], y - caixa[1]), texto, font=fonte, fill=cor)


def folha_anotada(dados_pdf: bytes, indice_pagina: int, area: Retangulo,
                  margem_interna_mm: float = 0.0, mostrar_referencias: bool = True,
                  largura_px: int = 620) -> Image.Image:
    """Folha A4 inteira com a área, a margem interna e as cotas."""
    dpi = largura_px / (A4_LARGURA_MM / 25.4)
    imagem = renderizar(dados_pdf, indice_pagina, dpi)
    if not mostrar_referencias:
        return _com_borda(imagem)

    px = imagem.width / A4_LARGURA_MM  # pixels por mm

    def ponto(x_mm: float, y_mm: float) -> tuple[float, float]:
        return x_mm * px, (A4_ALTURA_MM - y_mm) * px

    desenho = ImageDraw.Draw(imagem)
    fonte = _fonte(max(11, int(imagem.width / 48)))
    esquerda, topo = ponto(area.x_mm, area.topo_mm)
    direita, base = ponto(area.direita_mm, area.y_mm)

    if margem_interna_mm > 0:
        interna = area.recuar(margem_interna_mm)
        ix0, iy0 = ponto(interna.x_mm, interna.topo_mm)
        ix1, iy1 = ponto(interna.direita_mm, interna.y_mm)
        _retangulo_tracejado(desenho, (ix0, iy0, ix1, iy1), _LARANJA, 1, traco=4, vazio=4)
    _retangulo_tracejado(desenho, (esquerda, topo, direita, base), _AZUL, 2)

    # Cotas da área
    deslocamento = 14
    _seta(desenho, (esquerda, topo - deslocamento), (direita, topo - deslocamento), _AZUL)
    _rotulo(desenho, ((esquerda + direita) / 2, topo - deslocamento),
            f"{formatar_mm(area.largura_mm)} mm", fonte, _AZUL)
    _seta(desenho, (direita + deslocamento, topo), (direita + deslocamento, base), _AZUL)
    _rotulo(desenho, (direita + deslocamento, (topo + base) / 2),
            f"{formatar_mm(area.altura_mm)} mm", fonte, _AZUL)

    # Distâncias até as bordas da folha
    meio_y = (topo + base) / 2
    meio_x = (esquerda + direita) / 2
    margem_esq = area.x_mm
    margem_dir = A4_LARGURA_MM - area.direita_mm
    margem_sup = A4_ALTURA_MM - area.topo_mm
    margem_inf = area.y_mm
    if margem_esq > 3:
        _seta(desenho, (0, meio_y + 30), (esquerda, meio_y + 30), _CINZA)
        _rotulo(desenho, (esquerda / 2, meio_y + 30), f"{formatar_mm(margem_esq)} mm", fonte, _CINZA)
    if margem_dir > 3:
        _seta(desenho, (direita, meio_y + 30), (imagem.width, meio_y + 30), _CINZA)
        _rotulo(desenho, ((direita + imagem.width) / 2, meio_y + 30), f"{formatar_mm(margem_dir)} mm",
                fonte, _CINZA)
    # As cotas verticais ficam na margem esquerda para não cruzar a cota de largura.
    x_vertical = esquerda / 2 if margem_esq > 15 else meio_x
    if margem_sup > 3:
        _seta(desenho, (x_vertical, 0), (x_vertical, topo), _CINZA)
        _rotulo(desenho, (x_vertical, topo / 2), f"{formatar_mm(margem_sup)} mm", fonte, _CINZA)
    if margem_inf > 3:
        _seta(desenho, (x_vertical, base), (x_vertical, imagem.height), _CINZA)
        _rotulo(desenho, (x_vertical, (base + imagem.height) / 2), f"{formatar_mm(margem_inf)} mm",
                fonte, _CINZA)

    _rotulo(desenho, (imagem.width / 2, imagem.height - 14),
            f"Folha A4 — {formatar_mm(A4_LARGURA_MM)} × {formatar_mm(A4_ALTURA_MM)} mm",
            _fonte(max(10, int(imagem.width / 56))), _CINZA)
    return _com_borda(imagem)


def area_ampliada(dados_pdf: bytes, indice_pagina: int, area: Retangulo,
                  mostrar_referencias: bool = True, dpi: float = 220) -> Image.Image:
    """Recorte em alta resolução só da área de conteúdo, para leitura do texto."""
    imagem = renderizar(dados_pdf, indice_pagina, dpi)
    px = imagem.width / A4_LARGURA_MM
    folga = 3  # mm de papel ao redor
    caixa = (
        max(0, int((area.x_mm - folga) * px)),
        max(0, int((A4_ALTURA_MM - area.topo_mm - folga) * px)),
        min(imagem.width, int((area.direita_mm + folga) * px)),
        min(imagem.height, int((A4_ALTURA_MM - area.y_mm + folga) * px)),
    )
    recorte = imagem.crop(caixa)
    if mostrar_referencias:
        desenho = ImageDraw.Draw(recorte)
        x0 = area.x_mm * px - caixa[0]
        y0 = (A4_ALTURA_MM - area.topo_mm) * px - caixa[1]
        _retangulo_tracejado(desenho, (x0, y0, x0 + area.largura_mm * px, y0 + area.altura_mm * px),
                             _AZUL, 2)
    return _com_borda(recorte)


def _com_borda(imagem: Image.Image) -> Image.Image:
    desenho = ImageDraw.Draw(imagem)
    desenho.rectangle([0, 0, imagem.width - 1, imagem.height - 1], outline=(200, 200, 200))
    return imagem
