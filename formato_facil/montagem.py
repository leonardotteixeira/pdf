"""Montagem de várias imagens dentro de uma mesma área, sem distorção e sem cortes.

As imagens são organizadas em linhas (ou em colunas), na ordem escolhida pelo
usuário. Em cada linha todas as imagens têm a mesma altura e, juntas, ocupam a
largura da área; em colunas, vale o mesmo com largura e altura trocadas.
Entre todas as formas possíveis de dividir as imagens em linhas, escolhe-se a
que deixa as imagens maiores de forma equilibrada: a menor imagem fica o
maior possível e, entre arranjos equivalentes, vence o que ocupa mais espaço. Se o conjunto ficar
alto demais, ele é reduzido por igual — a proporção de cada imagem é sempre
mantida (mesma escala na largura e na altura).
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .geometria import Retangulo

LIMITE_BUSCA_COMPLETA = 12  # até 12 imagens testa todas as divisões em linhas (2^11)


@dataclass(frozen=True)
class Posicao:
    indice: int  # índice da imagem na lista original
    destino: Retangulo  # onde a imagem é desenhada (mm)
    girada: bool  # girada 90° para aproveitar melhor o espaço


@dataclass(frozen=True)
class Montagem:
    caixa: Retangulo
    posicoes: tuple[Posicao, ...]
    linhas: tuple[tuple[int, ...], ...]  # índices das imagens em cada linha (ou coluna)
    direcao: str = "linhas"  # "linhas" (lado a lado) ou "colunas" (empilhadas)

    @property
    def descricao(self) -> str:
        n = len(self.linhas)
        if self.direcao == "linhas":
            return f"{n} linha" + ("s" if n > 1 else "")
        return f"{n} coluna" + ("s" if n > 1 else "")

    @property
    def ocupacao(self) -> float:
        """Fração da área ocupada pelas imagens (0 a 1)."""
        total = sum(p.destino.largura_mm * p.destino.altura_mm for p in self.posicoes)
        return total / (self.caixa.largura_mm * self.caixa.altura_mm)

    @property
    def menor_lado_mm(self) -> float:
        return min(min(p.destino.largura_mm, p.destino.altura_mm) for p in self.posicoes)


def _divisoes_completas(n: int):
    """Todas as formas de dividir n itens consecutivos em linhas."""
    for cortes_qtd in range(n):
        for cortes in combinations(range(1, n), cortes_qtd):
            limites = (0, *cortes, n)
            yield [list(range(limites[i], limites[i + 1])) for i in range(len(limites) - 1)]


def _divisoes_equilibradas(proporcoes: list[float]):
    """Para muitas imagens: para cada número de linhas, divide equilibrando a
    soma das proporções (largura/altura) de cada linha."""
    n = len(proporcoes)
    total = sum(proporcoes)
    for linhas in range(1, n + 1):
        alvo = total / linhas
        divisao, atual, soma = [], [], 0.0
        for i, proporcao in enumerate(proporcoes):
            restantes_itens = n - i
            restantes_linhas = linhas - len(divisao)
            if atual and (soma + proporcao / 2 > alvo or restantes_itens < restantes_linhas) \
                    and len(divisao) < linhas - 1:
                divisao.append(atual)
                atual, soma = [], 0.0
            atual.append(i)
            soma += proporcao
        divisao.append(atual)
        yield divisao


def _avaliar(divisao: list[list[int]], proporcoes: list[float], largura: float, altura: float,
             espaco: float):
    """Altura de cada linha e fator de redução; ``None`` se a divisão não cabe."""
    alturas = []
    for linha in divisao:
        livre = largura - espaco * (len(linha) - 1)
        if livre <= 0:
            return None
        alturas.append(livre / sum(proporcoes[i] for i in linha))
    disponivel = altura - espaco * (len(divisao) - 1)
    if disponivel <= 0:
        return None
    fator = min(1.0, disponivel / sum(alturas))
    areas = [(h * fator) ** 2 * proporcoes[i] for h, linha in zip(alturas, divisao) for i in linha]
    pontuacao = (min(areas), sum(areas))
    return pontuacao, alturas, fator


def _melhor(proporcoes: list[float], largura: float, altura: float, espaco: float):
    n = len(proporcoes)
    candidatas = (_divisoes_completas(n) if n <= LIMITE_BUSCA_COMPLETA
                  else _divisoes_equilibradas(proporcoes))
    melhor = None
    for divisao in candidatas:
        avaliacao = _avaliar(divisao, proporcoes, largura, altura, espaco)
        if avaliacao is None:
            continue
        if melhor is None or _supera(avaliacao[0], melhor[0][0]):
            melhor = (avaliacao, divisao)
    return melhor


def _supera(nova: tuple[float, float], atual: tuple[float, float], tolerancia: float = 0.005) -> bool:
    """Critério equilibrado: primeiro, a MENOR imagem deve ficar o maior possível
    (evita uma imagem enorme ao lado de outras minúsculas); entre arranjos
    praticamente empatados nisso (0,5%), vence o que ocupa mais espaço no total."""
    menor_nova, total_nova = nova
    menor_atual, total_atual = atual
    if menor_nova > menor_atual * (1 + tolerancia):
        return True
    if menor_nova < menor_atual * (1 - tolerancia):
        return False
    return total_nova > total_atual + 1e-9


def montar(tamanhos_px: list[tuple[int, int]], caixa: Retangulo, espaco_mm: float = 2.0,
           permitir_girar: bool = False) -> Montagem:
    """Calcula a posição de cada imagem dentro da caixa (em mm)."""
    if not tamanhos_px:
        raise ValueError("Nenhuma imagem para montar.")
    espaco = max(0.0, float(espaco_mm))
    originais = [w / h for w, h in tamanhos_px]

    variantes = [[False] * len(originais)]
    if permitir_girar:
        caixa_em_pe = caixa.altura_mm >= caixa.largura_mm
        # Gira as imagens cuja orientação é contrária à da área (deitada numa área em pé).
        girar = [(p > 1) if caixa_em_pe else (p < 1) for p in originais]
        if any(girar):
            variantes.append(girar)

    # Testa arranjos em linhas (imagens lado a lado, linhas empilhadas) e em
    # colunas (imagens empilhadas, colunas lado a lado). Para colunas, o mesmo
    # cálculo é feito com largura e altura trocadas.
    resultado = None
    for giros in variantes:
        proporcoes = [1 / p if g else p for p, g in zip(originais, giros)]
        for direcao in ("linhas", "colunas"):
            if direcao == "linhas":
                melhor = _melhor(proporcoes, caixa.largura_mm, caixa.altura_mm, espaco)
            else:
                melhor = _melhor([1 / p for p in proporcoes], caixa.altura_mm, caixa.largura_mm, espaco)
            if melhor and (resultado is None or _supera(melhor[0][0], resultado[0][0][0])):
                resultado = (melhor, proporcoes, giros, direcao)
    if resultado is None:
        raise ValueError("O espaço entre as imagens é grande demais para a área.")

    ((_, medidas, fator), divisao), proporcoes, giros, direcao = resultado
    medidas = [m * fator for m in medidas]  # altura de cada linha ou largura de cada coluna
    posicoes: list[Posicao] = []
    if direcao == "linhas":
        altura_bloco = sum(medidas) + espaco * (len(divisao) - 1)
        topo = caixa.topo_mm - (caixa.altura_mm - altura_bloco) / 2
        for altura_linha, linha in zip(medidas, divisao):
            largura_linha = altura_linha * sum(proporcoes[i] for i in linha) + espaco * (len(linha) - 1)
            x = caixa.x_mm + (caixa.largura_mm - largura_linha) / 2
            for i in linha:
                largura = altura_linha * proporcoes[i]
                posicoes.append(Posicao(i, Retangulo(x, topo - altura_linha, largura, altura_linha), giros[i]))
                x += largura + espaco
            topo -= altura_linha + espaco
    else:
        largura_bloco = sum(medidas) + espaco * (len(divisao) - 1)
        x = caixa.x_mm + (caixa.largura_mm - largura_bloco) / 2
        for largura_coluna, coluna in zip(medidas, divisao):
            altura_coluna = largura_coluna * sum(1 / proporcoes[i] for i in coluna) + espaco * (len(coluna) - 1)
            topo = caixa.topo_mm - (caixa.altura_mm - altura_coluna) / 2
            for i in coluna:
                altura = largura_coluna / proporcoes[i]
                posicoes.append(Posicao(i, Retangulo(x, topo - altura, largura_coluna, altura), giros[i]))
                topo -= altura + espaco
            x += largura_coluna + espaco
    return Montagem(caixa, tuple(posicoes), tuple(tuple(g) for g in divisao), direcao)
