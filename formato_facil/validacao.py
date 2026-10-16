"""Verificação do PDF gerado, lendo o próprio arquivo (e não as configurações).

Usa o PyMuPDF para medir o tamanho real de cada página e a caixa que envolve
todo o conteúdo desenhado (texto, imagens e linhas), conferindo se tudo está
dentro da área de conteúdo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf as fitz

from .geometria import A4_ALTURA_MM, A4_LARGURA_MM, Retangulo, formatar_mm, pt_para_mm

TOLERANCIA_PAGINA_MM = 0.01
TOLERANCIA_CONTEUDO_MM = 0.2


@dataclass
class RelatorioPagina:
    numero: int
    largura_mm: float
    altura_mm: float
    caixa_conteudo: Retangulo | None  # mm, origem no canto inferior esquerdo
    caixa_texto: Retangulo | None
    caixa_imagens: Retangulo | None
    dentro_da_area: bool
    escala_aplicada: bool

    @property
    def a4(self) -> bool:
        return (abs(self.largura_mm - A4_LARGURA_MM) <= TOLERANCIA_PAGINA_MM
                and abs(self.altura_mm - A4_ALTURA_MM) <= TOLERANCIA_PAGINA_MM)


@dataclass
class RelatorioVerificacao:
    area: Retangulo
    paginas: list[RelatorioPagina]
    fontes_embutidas: bool
    texto_extraido: str
    problemas: list[str] = field(default_factory=list)

    @property
    def aprovado(self) -> bool:
        return not self.problemas

    @property
    def todas_a4(self) -> bool:
        return all(p.a4 for p in self.paginas)


def _uniao(caixas: list[fitz.Rect]) -> fitz.Rect | None:
    caixas = [c for c in caixas if c.is_valid and not c.is_empty]
    if not caixas:
        return None
    resultado = fitz.Rect(caixas[0])
    for caixa in caixas[1:]:
        resultado |= caixa
    return resultado


def _para_mm(caixa: fitz.Rect | None, altura_pagina_pt: float) -> Retangulo | None:
    if caixa is None:
        return None
    return Retangulo(
        pt_para_mm(caixa.x0),
        pt_para_mm(altura_pagina_pt - caixa.y1),
        pt_para_mm(caixa.width),
        pt_para_mm(caixa.height),
    )


def _contem(area: Retangulo, caixa: Retangulo, tolerancia: float) -> bool:
    return (caixa.x_mm >= area.x_mm - tolerancia
            and caixa.y_mm >= area.y_mm - tolerancia
            and caixa.direita_mm <= area.direita_mm + tolerancia
            and caixa.topo_mm <= area.topo_mm + tolerancia)


def verificar_pdf(dados: bytes, area: Retangulo, considerar_desenhos: bool = True,
                  tolerancia_mm: float = TOLERANCIA_CONTEUDO_MM) -> RelatorioVerificacao:
    """Mede o PDF e confere página A4 e conteúdo dentro da área.

    ``considerar_desenhos=False`` ignora linhas vetoriais (use quando as marcas
    de corte, que ficam propositalmente fora da área, estiverem ativadas).
    """
    paginas: list[RelatorioPagina] = []
    problemas: list[str] = []
    fontes_ok = True
    textos: list[str] = []
    with fitz.open(stream=dados, filetype="pdf") as documento:
        for indice, pagina in enumerate(documento):
            altura_pt = pagina.rect.height
            caixas_texto = []
            for bloco in pagina.get_text("rawdict")["blocks"]:
                for linha in bloco.get("lines", []):
                    for trecho in linha["spans"]:
                        for caractere in trecho["chars"]:
                            if caractere["c"].strip():
                                caixas_texto.append(fitz.Rect(caractere["bbox"]))
            caixas_imagens = [fitz.Rect(info["bbox"]) for info in pagina.get_image_info()]
            caixas_desenhos = ([fitz.Rect(d["rect"]) for d in pagina.get_drawings()]
                               if considerar_desenhos else [])
            textos.append(pagina.get_text())

            for fonte in pagina.get_fonts():
                extensao = fonte[1]
                if extensao in ("n/a", ""):
                    fontes_ok = False

            texto_mm = _para_mm(_uniao(caixas_texto), altura_pt)
            imagens_mm = _para_mm(_uniao(caixas_imagens), altura_pt)
            total_mm = _para_mm(_uniao(caixas_texto + caixas_imagens + caixas_desenhos), altura_pt)
            dentro = total_mm is None or _contem(area, total_mm, tolerancia_mm)
            # A página não pode ter UserUnit nem caixa de recorte diferente da mídia.
            escala = abs(pagina.cropbox.width - pagina.mediabox.width) > 0.01 or \
                abs(pagina.cropbox.height - pagina.mediabox.height) > 0.01
            relatorio = RelatorioPagina(
                indice + 1,
                pt_para_mm(pagina.mediabox.width),
                pt_para_mm(pagina.mediabox.height),
                total_mm, texto_mm, imagens_mm, dentro, escala,
            )
            paginas.append(relatorio)

            if not relatorio.a4:
                problemas.append(
                    f"Página {relatorio.numero}: tamanho {formatar_mm(relatorio.largura_mm)} × "
                    f"{formatar_mm(relatorio.altura_mm)} mm não é A4."
                )
            if not dentro:
                problemas.append(f"Página {relatorio.numero}: há conteúdo fora da área definida.")
            if escala:
                problemas.append(f"Página {relatorio.numero}: caixa de recorte diferente da página.")
    if not fontes_ok:
        problemas.append("Há fontes não incorporadas no PDF.")
    return RelatorioVerificacao(area, paginas, fontes_ok, "\n".join(textos), problemas)
