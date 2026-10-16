"""Registro de fontes TrueType para o ReportLab.

Usamos apenas fontes TrueType, que o ReportLab incorpora (em subconjunto) no
PDF. Isso garante acentuação correta e aparência idêntica em qualquer
computador. As fontes do Windows são usadas quando disponíveis; no Linux (por
exemplo, no Streamlit Cloud) usam-se as fontes livres Liberation e DejaVu. A
Bitstream Vera, distribuída junto com o ReportLab, é a alternativa garantida.
"""

from __future__ import annotations

import os
import struct
from functools import lru_cache
from pathlib import Path

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .erros import ErroValidacao

_PASTA_WINDOWS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
_PASTA_REPORTLAB = Path(reportlab.__file__).parent / "fonts"
_PASTA_PROJETO = Path(__file__).resolve().parent.parent / "fontes"
_PASTAS_LINUX = [Path(p) for p in (
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/liberation2",
    "/usr/share/fonts/truetype/dejavu",
)]

FONTE_RESERVA = "Bitstream Vera Sans"

# Nome exibido -> nome do arquivo .ttf
_CANDIDATAS: dict[str, str] = {
    "Arial": "arial.ttf",
    "Calibri": "calibri.ttf",
    "Segoe UI": "segoeui.ttf",
    "Verdana": "verdana.ttf",
    "Georgia": "georgia.ttf",
    "Times New Roman": "times.ttf",
    # Linux: Liberation Sans/Serif têm as mesmas medidas de Arial/Times New Roman.
    "Liberation Sans": "LiberationSans-Regular.ttf",
    "Liberation Serif": "LiberationSerif-Regular.ttf",
    "DejaVu Sans": "DejaVuSans.ttf",
    FONTE_RESERVA: "Vera.ttf",
}

PREFERENCIA_PADRAO = ("Arial", "Liberation Sans", "DejaVu Sans")


def _localizar_arquivo(arquivo: str) -> Path | None:
    for pasta in (_PASTA_PROJETO, _PASTA_WINDOWS, *_PASTAS_LINUX, _PASTA_REPORTLAB):
        caminho = pasta / arquivo
        if caminho.is_file():
            return caminho
    return None


@lru_cache(maxsize=1)
def fontes_disponiveis() -> dict[str, Path]:
    """Fontes que existem neste computador (nome exibido -> caminho)."""
    encontradas: dict[str, Path] = {}
    for nome, arquivo in _CANDIDATAS.items():
        caminho = _localizar_arquivo(arquivo)
        if caminho is not None:
            encontradas[nome] = caminho
    return encontradas


def fonte_padrao() -> str:
    disponiveis = fontes_disponiveis()
    return next((nome for nome in PREFERENCIA_PADRAO if nome in disponiveis), FONTE_RESERVA)


def nome_interno(nome: str) -> str:
    return "FF-" + nome.replace(" ", "")


def registrar_fonte(nome: str) -> str:
    """Registra a fonte no ReportLab (uma única vez) e devolve o nome interno."""
    disponiveis = fontes_disponiveis()
    if nome not in disponiveis:
        raise ErroValidacao(f"A fonte “{nome}” não está disponível neste computador.")
    interno = nome_interno(nome)
    if interno not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(interno, str(disponiveis[nome])))
    return interno


@lru_cache(maxsize=None)
def _metricas_arquivo(caminho: str) -> tuple[float, float] | None:
    """Lê do arquivo TTF os valores verticais que abrangem todos os glifos.

    O ReportLab usa o ``sTypoAscender``, que não cobre letras maiúsculas
    acentuadas (Á, Ã, Ê). Para garantir que nada saia da área, usamos o maior
    valor entre ``usWinAscent``/``usWinDescent`` (tabela OS/2) e o
    ascendente/descendente da tabela ``hhea``. Devolve frações do em.
    """
    try:
        dados = Path(caminho).read_bytes()
        num_tabelas = struct.unpack(">H", dados[4:6])[0]
        tabelas = {}
        for i in range(num_tabelas):
            registro = dados[12 + 16 * i: 28 + 16 * i]
            tag = registro[:4].decode("latin-1")
            _, deslocamento, _ = struct.unpack(">III", registro[4:])
            tabelas[tag] = deslocamento
        unidades = struct.unpack(">H", dados[tabelas["head"] + 18: tabelas["head"] + 20])[0]
        hhea_asc, hhea_desc = struct.unpack(">hh", dados[tabelas["hhea"] + 4: tabelas["hhea"] + 8])
        ascendente, descendente = hhea_asc, -hhea_desc
        if "OS/2" in tabelas:
            win_asc, win_desc = struct.unpack(">HH", dados[tabelas["OS/2"] + 74: tabelas["OS/2"] + 78])
            ascendente, descendente = max(ascendente, win_asc), max(descendente, win_desc)
        return ascendente / unidades, descendente / unidades
    except (OSError, KeyError, struct.error, ZeroDivisionError):
        return None


def metricas_verticais(nome_interno_fonte: str, tamanho_pt: float) -> tuple[float, float]:
    """(ascendente, descendente) em pontos; o descendente é devolvido positivo."""
    fonte = pdfmetrics.getFont(nome_interno_fonte)
    caminho = getattr(fonte.face, "filename", None)
    metricas = _metricas_arquivo(str(caminho)) if caminho else None
    if metricas is not None:
        return metricas[0] * tamanho_pt, metricas[1] * tamanho_pt
    ascendente, descendente = pdfmetrics.getAscentDescent(nome_interno_fonte, tamanho_pt)
    return float(ascendente), float(abs(descendente))


def caracteres_ausentes(nome: str, texto: str) -> list[str]:
    """Caracteres do texto que não existem na fonte (seriam impressos como caixas)."""
    interno = registrar_fonte(nome)
    fonte = pdfmetrics.getFont(interno)
    mapa = fonte.face.charToGlyph
    ausentes: list[str] = []
    for caractere in sorted(set(texto)):
        if caractere in "\n\r\t" or caractere.isspace() and caractere != "\u00a0":
            continue
        if ord(caractere) not in mapa and caractere not in ausentes:
            ausentes.append(caractere)
    return ausentes
