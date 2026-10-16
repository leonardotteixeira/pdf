"""Geração do PDF final com ReportLab, usando apenas unidades físicas.

A página é sempre A4 retrato (210 × 297 mm). Todo o conteúdo é desenhado
dentro do retângulo da área calculado em ``geometria``. Não há nenhuma
transformação de escala aplicada à página.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image
from reportlab.lib.colors import Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from . import fontes, montagem
from . import imagens as proc_imagens
from .erros import ErroConteudoExcedente, ErroValidacao
from .formatacao import ResultadoLayout, espaco_extra_justificado, posicoes_das_palavras
from .geometria import PAGINA_A4, Retangulo, area_interna, formatar_mm, mm_para_pt

CRIADOR = "Formato Fácil PDF"

_COR_GUIA = Color(0.55, 0.55, 0.55)
_ESPESSURA_GUIA_PT = 0.3
_MARCA_AFASTAMENTO_MM = 2.0
_MARCA_COMPRIMENTO_MM = 5.0


@dataclass(frozen=True)
class OpcoesGuias:
    """Linhas de referência opcionais no PDF (desligadas por padrão)."""

    contorno: bool = False  # contorno tracejado, desenhado por dentro da área
    marcas_corte: bool = False  # marcas nos cantos, do lado de fora da área

    @property
    def alguma(self) -> bool:
        return self.contorno or self.marcas_corte


def _novo_canvas(saida: io.BytesIO, titulo: str, fonte_interna: str) -> canvas.Canvas:
    # A fonte inicial é informada para que o ReportLab não declare a Helvetica
    # padrão (que não é incorporada) no início de cada página.
    c = canvas.Canvas(saida, pagesize=PAGINA_A4.tamanho_pt, pageCompression=1,
                      initialFontName=fonte_interna)
    c.setTitle(titulo)
    c.setAuthor(CRIADOR)
    c.setCreator(CRIADOR)
    c.setSubject("Conteúdo formatado em área de tamanho fixo sobre folha A4")
    # Sugere ao leitor de PDF imprimir em tamanho real (sem "ajustar à página").
    c.setViewerPreference("PrintScaling", "None")
    return c


def _desenhar_guias(c: canvas.Canvas, area: Retangulo, guias: OpcoesGuias) -> None:
    if not guias.alguma:
        return
    c.saveState()
    c.setStrokeColor(_COR_GUIA)
    c.setLineWidth(_ESPESSURA_GUIA_PT)
    if guias.contorno:
        meio = _ESPESSURA_GUIA_PT / 2
        c.setDash(2, 2)
        c.rect(area.x_pt + meio, area.y_pt + meio, area.largura_pt - 2 * meio,
               area.altura_pt - 2 * meio, stroke=1, fill=0)
        c.setDash()
    if guias.marcas_corte:
        a = mm_para_pt(_MARCA_AFASTAMENTO_MM)
        m = mm_para_pt(_MARCA_COMPRIMENTO_MM)
        for x in (area.x_pt, area.direita_pt):
            for y in (area.y_pt, area.topo_pt):
                sx = -1 if x == area.x_pt else 1
                sy = -1 if y == area.y_pt else 1
                c.line(x + sx * a, y, x + sx * (a + m), y)  # horizontal, para fora
                c.line(x, y + sy * a, x, y + sy * (a + m))  # vertical, para fora
    c.restoreState()


def verificar_excesso(layout: ResultadoLayout, permitir_varias_paginas: bool) -> None:
    """Interrompe antes da geração se o texto não couber e o usuário não escolheu
    distribuir em várias folhas. Nenhuma linha é descartada silenciosamente."""
    if layout.cabe_em_uma_area or permitir_varias_paginas:
        return
    raise ErroConteudoExcedente(
        f"O texto não cabe em uma única área: ele ocupa {layout.total_linhas} linhas e cabem "
        f"{layout.linhas_por_area} por área (seriam necessárias {layout.numero_paginas} folhas). "
        "Escolha distribuir em várias folhas, reduzir a fonte ou editar o texto.",
        paginas_necessarias=layout.numero_paginas,
        linhas_totais=layout.total_linhas,
        linhas_por_area=layout.linhas_por_area,
    )


def gerar_pdf_texto(layout: ResultadoLayout, guias: OpcoesGuias = OpcoesGuias(),
                    permitir_varias_paginas: bool = False,
                    titulo: str = "Documento formatado") -> bytes:
    """Gera o PDF no modo texto (texto selecionável e pesquisável)."""
    if not layout.paginas or all(linha.vazia for p in layout.paginas for linha in p):
        raise ErroValidacao("Não há texto para gerar o PDF. Digite ou importe algum conteúdo.")
    verificar_excesso(layout, permitir_varias_paginas)

    saida = io.BytesIO()
    c = _novo_canvas(saida, titulo, layout.fonte_interna)
    interna = layout.interna
    tamanho = layout.config.tamanho_pt
    for linhas in layout.paginas:
        _desenhar_guias(c, layout.area, guias)
        c.setFont(layout.fonte_interna, tamanho)
        texto = c.beginText()
        texto.setFont(layout.fonte_interna, tamanho)
        texto.setFillColorRGB(0, 0, 0)
        for indice, linha in enumerate(linhas):
            if linha.vazia:
                continue
            base = interna.topo_pt - layout.ascendente_pt - indice * layout.entrelinha_pt
            posicoes = posicoes_das_palavras(linha, layout)
            extra = espaco_extra_justificado(linha, layout)
            texto.setTextOrigin(interna.x_pt + posicoes[0], base)
            if extra:
                # O ReportLab sempre codifica o espaço como 32 nas fontes TrueType,
                # então o operador Tw (espaçamento entre palavras) funciona e a
                # linha continua sendo uma única frase pesquisável.
                texto.setWordSpace(extra)
                texto.textOut(linha.texto)
                texto.setWordSpace(0)
            else:
                texto.textOut(linha.texto)
        c.drawText(texto)
        c.showPage()
    c.save()
    return saida.getvalue()


def gerar_pdf_imagens(lista_imagens: list[Image.Image], area: Retangulo, modo: str = "ajustar",
                      margem_mm: float = 0.0, guias: OpcoesGuias = OpcoesGuias(),
                      titulo: str = "Imagem formatada") -> tuple[bytes, list[str]]:
    """Gera o PDF no modo "preservar aparência": uma imagem por folha A4,
    sempre na mesma posição, sem distorção."""
    if not lista_imagens:
        raise ErroValidacao("Não há imagem para gerar o PDF.")
    caixa = area_interna(area, margem_mm) if margem_mm > 0 else area

    saida = io.BytesIO()
    c = _novo_canvas(saida, titulo, fontes.registrar_fonte(fontes.fonte_padrao()))
    avisos: list[str] = []
    for numero, imagem in enumerate(lista_imagens, start=1):
        encaixe = proc_imagens.calcular_encaixe(imagem.width, imagem.height, caixa, modo)
        preparada, avisos_imagem = proc_imagens.preparar_para_pdf(imagem, encaixe)
        prefixo = f"Página {numero}: " if len(lista_imagens) > 1 else ""
        avisos.extend(prefixo + a for a in avisos_imagem)
        destino = encaixe.destino
        c.drawImage(ImageReader(preparada), destino.x_pt, destino.y_pt,
                    width=destino.largura_pt, height=destino.altura_pt)
        _desenhar_guias(c, area, guias)
        c.showPage()
    c.save()
    return saida.getvalue(), avisos


MENOR_LADO_LEGIVEL_MM = 15.0


def gerar_pdf_montagem(lista_imagens: list[Image.Image], area: Retangulo, margem_mm: float = 0.0,
                       espaco_mm: float = 2.0, imagens_por_area: int = 0,
                       permitir_girar: bool = False, guias: OpcoesGuias = OpcoesGuias(),
                       nomes: list[str] | None = None, titulo: str = "Imagens formatadas",
                       ) -> tuple[bytes, list[str], list[montagem.Montagem]]:
    """Gera o PDF com várias imagens juntas na mesma área (sem distorção nem cortes).

    ``imagens_por_area = 0`` coloca todas na mesma área; um valor N distribui as
    imagens em grupos de N, um grupo por folha A4 (sempre na mesma posição).
    """
    if not lista_imagens:
        raise ErroValidacao("Não há imagem para gerar o PDF.")
    nomes = nomes or [f"Imagem {i}" for i in range(1, len(lista_imagens) + 1)]
    caixa = area_interna(area, margem_mm) if margem_mm > 0 else area
    por_area = imagens_por_area if imagens_por_area and imagens_por_area > 0 else len(lista_imagens)
    grupos = [list(range(i, min(i + por_area, len(lista_imagens))))
              for i in range(0, len(lista_imagens), por_area)]

    saida = io.BytesIO()
    c = _novo_canvas(saida, titulo, fontes.registrar_fonte(fontes.fonte_padrao()))
    avisos: list[str] = []
    montagens: list[montagem.Montagem] = []
    for grupo in grupos:
        tamanhos = [lista_imagens[i].size for i in grupo]
        try:
            resultado = montagem.montar(tamanhos, caixa, espaco_mm, permitir_girar)
        except ValueError as exc:
            raise ErroValidacao("O espaço entre as imagens é grande demais para a área. "
                                "Diminua o espaço ou o número de imagens por área.") from exc
        montagens.append(resultado)
        for posicao in resultado.posicoes:
            indice = grupo[posicao.indice]
            imagem = lista_imagens[indice]
            if posicao.girada:
                imagem = imagem.transpose(Image.Transpose.ROTATE_90)
            destino = posicao.destino
            imagem, dpi = proc_imagens.limitar_resolucao(imagem, destino.largura_mm)
            if dpi < proc_imagens.DPI_BAIXO:
                avisos.append(f"{nomes[indice]}: resolução baixa para o tamanho impresso "
                              f"(cerca de {dpi:.0f} DPI); pode sair borrada.")
            if min(destino.largura_mm, destino.altura_mm) < MENOR_LADO_LEGIVEL_MM:
                avisos.append(
                    f"{nomes[indice]}: ficou pequena ({formatar_mm(destino.largura_mm)} × "
                    f"{formatar_mm(destino.altura_mm)} mm). Considere menos imagens por área."
                )
            c.drawImage(ImageReader(imagem), destino.x_pt, destino.y_pt,
                        width=destino.largura_pt, height=destino.altura_pt)
        _desenhar_guias(c, area, guias)
        c.showPage()
    c.save()
    return saida.getvalue(), avisos, montagens
