"""Formatação do texto: limpeza, quebra de linhas e paginação.

O mecanismo de layout é próprio (em vez de depender de estimativas) para que
cada linha seja medida com as métricas reais da fonte TrueType. Assim é
possível garantir, antes de gerar o PDF, que nenhuma linha ultrapassa a área e
saber exatamente quantas áreas o texto ocupa.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace

from reportlab.pdfbase.pdfmetrics import stringWidth

from . import fontes
from .erros import ErroValidacao
from .geometria import Retangulo, area_interna, formatar_mm

ALINHAMENTOS = {
    "esquerda": "À esquerda",
    "justificado": "Justificado",
    "centralizado": "Centralizado",
}

TAMANHO_MINIMO_ABSOLUTO_PT = 4.0
TAMANHO_MAXIMO_ABSOLUTO_PT = 72.0

_EPSILON = 1e-6
# Pequena folga (≈0,1 mm) entre a linha mais longa e a borda: compensa o
# arredondamento das larguras de glifos que o PDF armazena em números inteiros.
FOLGA_HORIZONTAL_PT = 0.3
_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​﻿]")
_ESPACOS = re.compile(r"[ \t]+")


# ---------------------------------------------------------------------------
# Limpeza de texto
# ---------------------------------------------------------------------------

def normalizar_texto(texto: str) -> str:
    """Normaliza quebras de linha e acentos sem alterar o conteúdo.

    - Converte CRLF/CR em LF.
    - Usa a forma Unicode NFC (letras acentuadas como um único caractere).
    - Troca tabulações por espaços e remove caracteres de controle invisíveis.
    - Remove espaços no fim das linhas.
    """
    if not texto:
        return ""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = texto.replace(" ", "\n").replace(" ", "\n\n")
    texto = texto.replace("­", "")  # hífen invisível (soft hyphen)
    texto = unicodedata.normalize("NFC", texto)
    texto = texto.replace("\t", "    ")
    texto = _CONTROLE.sub("", texto)
    return "\n".join(linha.rstrip() for linha in texto.split("\n"))


def texto_esta_vazio(texto: str | None) -> bool:
    return not texto or not texto.strip()


def corrigir_quebras_de_linha(texto: str) -> str:
    """Junta linhas quebradas no meio de parágrafos (comum em OCR e PDFs).

    Linhas em branco continuam separando parágrafos. Uma linha terminada em
    hífen é unida à seguinte sem espaço, mantendo o hífen (o usuário revisa).
    """
    texto = normalizar_texto(texto)
    paragrafos = re.split(r"\n\s*\n", texto)
    resultado = []
    for paragrafo in paragrafos:
        linhas = [linha.strip() for linha in paragrafo.split("\n") if linha.strip()]
        if not linhas:
            continue
        unido = linhas[0]
        for linha in linhas[1:]:
            if unido.endswith("-"):
                unido += linha
            else:
                unido += " " + linha
        resultado.append(unido)
    return "\n\n".join(resultado)


def remover_espacos_extras(texto: str) -> str:
    """Reduz espaços repetidos e linhas em branco consecutivas."""
    texto = normalizar_texto(texto)
    linhas = [_ESPACOS.sub(" ", linha).strip() for linha in texto.split("\n")]
    texto = "\n".join(linhas)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def contar_palavras(texto: str) -> int:
    return len(texto.split())


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigTexto:
    fonte: str = field(default_factory=fontes.fonte_padrao)
    tamanho_pt: float = 10.0
    espacamento: float = 1.25  # múltiplo do tamanho da fonte
    margem_interna_mm: float = 3.0
    alinhamento: str = "esquerda"


@dataclass
class Linha:
    palavras: list[str]
    larguras: list[float]  # largura de cada palavra, em pontos
    largura_pt: float  # largura natural (com espaços normais)
    ultima_do_paragrafo: bool

    @property
    def vazia(self) -> bool:
        return not self.palavras

    @property
    def texto(self) -> str:
        return " ".join(self.palavras)


@dataclass
class ResultadoLayout:
    config: ConfigTexto
    area: Retangulo
    interna: Retangulo
    fonte_interna: str
    paginas: list[list[Linha]]
    linhas_por_area: int
    entrelinha_pt: float
    ascendente_pt: float
    descendente_pt: float
    largura_espaco_pt: float
    largura_linha_pt: float  # largura máxima de uma linha de texto
    caracteres_sem_glifo: list[str]

    @property
    def total_linhas(self) -> int:
        return sum(len(p) for p in self.paginas)

    @property
    def numero_paginas(self) -> int:
        return len(self.paginas)

    @property
    def cabe_em_uma_area(self) -> bool:
        return len(self.paginas) <= 1

    @property
    def ocupacao_ultima_area(self) -> float:
        """Fração das linhas disponíveis usada na última área (0 a 1)."""
        if not self.paginas or self.linhas_por_area == 0:
            return 0.0
        return len(self.paginas[-1]) / self.linhas_por_area


def _quebrar_palavra_longa(palavra: str, fonte: str, tamanho: float, largura_max: float) -> list[str]:
    """Divide uma palavra que, sozinha, não cabe na largura (ex.: URLs)."""
    pedacos: list[str] = []
    atual = ""
    for caractere in palavra:
        if atual and stringWidth(atual + caractere, fonte, tamanho) > largura_max + _EPSILON:
            pedacos.append(atual)
            atual = caractere
        else:
            atual += caractere
    if atual:
        pedacos.append(atual)
    return pedacos


def quebrar_em_linhas(texto: str, fonte_interna: str, tamanho_pt: float,
                      largura_max_pt: float) -> list[Linha]:
    """Quebra o texto em linhas que cabem em ``largura_max_pt``.

    Cada quebra de linha do texto original é respeitada; linhas em branco
    viram linhas vazias (separação de parágrafos).
    """
    espaco = stringWidth(" ", fonte_interna, tamanho_pt)
    linhas: list[Linha] = []
    for linha_original in normalizar_texto(texto).split("\n"):
        palavras_brutas = [p for p in _ESPACOS.split(linha_original.strip()) if p]
        if not palavras_brutas:
            linhas.append(Linha([], [], 0.0, True))
            continue

        palavras: list[tuple[str, float]] = []
        for palavra in palavras_brutas:
            largura = stringWidth(palavra, fonte_interna, tamanho_pt)
            if largura > largura_max_pt + _EPSILON:
                for pedaco in _quebrar_palavra_longa(palavra, fonte_interna, tamanho_pt, largura_max_pt):
                    palavras.append((pedaco, stringWidth(pedaco, fonte_interna, tamanho_pt)))
            else:
                palavras.append((palavra, largura))

        atual: list[tuple[str, float]] = []
        largura_atual = 0.0
        for palavra, largura in palavras:
            nova = largura if not atual else largura_atual + espaco + largura
            if atual and nova > largura_max_pt + _EPSILON:
                linhas.append(Linha([p for p, _ in atual], [w for _, w in atual], largura_atual, False))
                atual, largura_atual = [(palavra, largura)], largura
            else:
                atual.append((palavra, largura))
                largura_atual = nova
        linhas.append(Linha([p for p, _ in atual], [w for _, w in atual], largura_atual, True))
    return linhas


def linhas_que_cabem(altura_pt: float, ascendente: float, descendente: float, entrelinha: float) -> int:
    """Quantas linhas cabem na altura sem que nenhum glifo ultrapasse a área.

    A primeira linha de base fica a ``ascendente`` do topo; cada linha seguinte,
    ``entrelinha`` abaixo. A última linha precisa ter seu descendente dentro da área.
    """
    disponivel = altura_pt - ascendente - descendente
    if disponivel < -_EPSILON:
        return 0
    return int((disponivel + _EPSILON) // entrelinha) + 1


def paginar(linhas: list[Linha], linhas_por_area: int) -> list[list[Linha]]:
    """Distribui as linhas em áreas, descartando apenas linhas em branco no
    início das áreas de continuação (nunca texto)."""
    if linhas_por_area <= 0:
        return [linhas] if linhas else []
    # Remove linhas em branco no final do texto (não têm conteúdo).
    while linhas and linhas[-1].vazia:
        linhas = linhas[:-1]
    paginas: list[list[Linha]] = []
    atual: list[Linha] = []
    for linha in linhas:
        if not atual and paginas and linha.vazia:
            continue
        atual.append(linha)
        if len(atual) == linhas_por_area:
            paginas.append(atual)
            atual = []
    if atual:
        paginas.append(atual)
    return paginas


def calcular_layout(texto: str, config: ConfigTexto, area: Retangulo) -> ResultadoLayout:
    """Calcula o layout completo do texto dentro da área."""
    if not (TAMANHO_MINIMO_ABSOLUTO_PT <= config.tamanho_pt <= TAMANHO_MAXIMO_ABSOLUTO_PT):
        raise ErroValidacao(
            f"O tamanho da fonte deve ficar entre {TAMANHO_MINIMO_ABSOLUTO_PT:g} e "
            f"{TAMANHO_MAXIMO_ABSOLUTO_PT:g} pt."
        )
    if not (0.8 <= config.espacamento <= 4.0):
        raise ErroValidacao("O espaçamento entre linhas deve ficar entre 0,8 e 4,0.")
    if config.alinhamento not in ALINHAMENTOS:
        raise ErroValidacao("Alinhamento de texto desconhecido.")

    interna = area_interna(area, config.margem_interna_mm)
    fonte_interna = fontes.registrar_fonte(config.fonte)
    ascendente, descendente = fontes.metricas_verticais(fonte_interna, config.tamanho_pt)
    entrelinha = config.tamanho_pt * config.espacamento

    por_area = linhas_que_cabem(interna.altura_pt, ascendente, descendente, entrelinha)
    if por_area < 1:
        raise ErroValidacao(
            "Com esse tamanho de fonte e essa margem não cabe nem uma linha na área. "
            "Reduza a fonte ou a margem interna."
        )
    largura_linha = interna.largura_pt - FOLGA_HORIZONTAL_PT
    linhas = quebrar_em_linhas(texto, fonte_interna, config.tamanho_pt, largura_linha)
    paginas = paginar(linhas, por_area)

    return ResultadoLayout(
        config=config,
        area=area,
        interna=interna,
        fonte_interna=fonte_interna,
        paginas=paginas,
        linhas_por_area=por_area,
        entrelinha_pt=entrelinha,
        ascendente_pt=ascendente,
        descendente_pt=descendente,
        largura_espaco_pt=stringWidth(" ", fonte_interna, config.tamanho_pt),
        largura_linha_pt=largura_linha,
        caracteres_sem_glifo=fontes.caracteres_ausentes(config.fonte, texto),
    )


def maior_tamanho_que_cabe(texto: str, config: ConfigTexto, area: Retangulo,
                           minimo_pt: float, maximo_pt: float | None = None,
                           passo_pt: float = 0.25) -> float | None:
    """Maior tamanho de fonte (entre mínimo e máximo) com o qual o texto cabe
    em uma única área. Devolve ``None`` se nem o mínimo for suficiente."""
    maximo_pt = config.tamanho_pt if maximo_pt is None else maximo_pt
    minimo_pt = max(minimo_pt, TAMANHO_MINIMO_ABSOLUTO_PT)
    passos = int(round((maximo_pt - minimo_pt) / passo_pt))
    for i in range(passos + 1):
        tamanho = round(maximo_pt - i * passo_pt, 2)
        if tamanho < minimo_pt - _EPSILON:
            break
        candidato = replace(config, tamanho_pt=tamanho)
        try:
            if calcular_layout(texto, candidato, area).cabe_em_uma_area:
                return tamanho
        except ErroValidacao:
            continue
    return None


def espaco_extra_justificado(linha: Linha, layout: ResultadoLayout) -> float:
    """Espaço adicional (pt) a somar em cada espaço entre palavras para que a
    linha justificada termine exatamente na borda direita. Zero se não se aplica."""
    n = len(linha.palavras)
    if layout.config.alinhamento != "justificado" or linha.ultima_do_paragrafo or n < 2:
        return 0.0
    return max(0.0, (layout.largura_linha_pt - linha.largura_pt) / (n - 1))


def posicoes_das_palavras(linha: Linha, layout: ResultadoLayout) -> list[float]:
    """Deslocamento horizontal (pt, a partir da borda interna) de cada palavra."""
    largura_max = layout.largura_linha_pt
    alinhamento = layout.config.alinhamento
    if not linha.palavras:
        return []

    intervalo = layout.largura_espaco_pt + espaco_extra_justificado(linha, layout)

    if alinhamento == "centralizado":
        inicio = max(0.0, (largura_max - linha.largura_pt) / 2.0)
    else:
        inicio = 0.0

    posicoes = []
    x = inicio
    for largura in linha.larguras:
        posicoes.append(x)
        x += largura + intervalo
    return posicoes


def descrever_espaco(layout: ResultadoLayout) -> str:
    interna = layout.interna
    return (
        f"Área útil para o texto: {formatar_mm(interna.largura_mm)} × "
        f"{formatar_mm(interna.altura_mm)} mm — cabem {layout.linhas_por_area} linhas "
        f"por área com fonte de {formatar_mm(layout.config.tamanho_pt)} pt."
    )
