"""Cálculo das dimensões físicas da página e da área de conteúdo.

Convenções:
- Todas as medidas públicas estão em milímetros.
- A origem fica no canto inferior esquerdo da página (como no PDF/ReportLab).
- 1 polegada = 25,4 mm = 72 pontos PDF.
"""

from __future__ import annotations

from dataclasses import dataclass

from .erros import ErroGeometria

PONTOS_POR_MM = 72.0 / 25.4

A4_LARGURA_MM = 210.0
A4_ALTURA_MM = 297.0

AREA_LARGURA_PADRAO_MM = 75.0
AREA_ALTURA_PADRAO_MM = 140.0

# Limites razoáveis para evitar áreas inutilizáveis.
AREA_MINIMA_MM = 10.0


def mm_para_pt(mm: float) -> float:
    return mm * PONTOS_POR_MM


def pt_para_mm(pt: float) -> float:
    return pt / PONTOS_POR_MM


def formatar_mm(valor: float) -> str:
    """Formata milímetros no padrão brasileiro: 67.5 -> '67,5'."""
    texto = f"{valor:.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


@dataclass(frozen=True)
class Retangulo:
    """Retângulo em milímetros com origem no canto inferior esquerdo."""

    x_mm: float
    y_mm: float
    largura_mm: float
    altura_mm: float

    @property
    def direita_mm(self) -> float:
        return self.x_mm + self.largura_mm

    @property
    def topo_mm(self) -> float:
        return self.y_mm + self.altura_mm

    # Valores em pontos PDF, usados pelo ReportLab.
    @property
    def x_pt(self) -> float:
        return mm_para_pt(self.x_mm)

    @property
    def y_pt(self) -> float:
        return mm_para_pt(self.y_mm)

    @property
    def largura_pt(self) -> float:
        return mm_para_pt(self.largura_mm)

    @property
    def altura_pt(self) -> float:
        return mm_para_pt(self.altura_mm)

    @property
    def direita_pt(self) -> float:
        return mm_para_pt(self.direita_mm)

    @property
    def topo_pt(self) -> float:
        return mm_para_pt(self.topo_mm)

    def recuar(self, margem_mm: float) -> "Retangulo":
        """Retângulo interno, reduzido pela margem em todos os lados."""
        return Retangulo(
            self.x_mm + margem_mm,
            self.y_mm + margem_mm,
            self.largura_mm - 2 * margem_mm,
            self.altura_mm - 2 * margem_mm,
        )


@dataclass(frozen=True)
class ConfigArea:
    """Configuração da área de conteúdo dentro da folha A4.

    Quando ``centralizar_horizontal`` é falso, ``x_mm`` é a distância da borda
    esquerda da folha até a borda esquerda da área. Quando ``centralizar_vertical``
    é falso, ``y_mm`` é a distância da borda inferior da folha até a borda
    inferior da área.
    """

    largura_mm: float = AREA_LARGURA_PADRAO_MM
    altura_mm: float = AREA_ALTURA_PADRAO_MM
    centralizar_horizontal: bool = True
    centralizar_vertical: bool = True
    x_mm: float | None = None
    y_mm: float | None = None


@dataclass(frozen=True)
class Pagina:
    largura_mm: float = A4_LARGURA_MM
    altura_mm: float = A4_ALTURA_MM

    @property
    def tamanho_pt(self) -> tuple[float, float]:
        return (mm_para_pt(self.largura_mm), mm_para_pt(self.altura_mm))


PAGINA_A4 = Pagina()


def calcular_area(config: ConfigArea | None = None, pagina: Pagina = PAGINA_A4) -> Retangulo:
    """Calcula o retângulo de conteúdo e valida se ele cabe inteiro na folha."""
    config = config or ConfigArea()
    largura, altura = float(config.largura_mm), float(config.altura_mm)

    if largura < AREA_MINIMA_MM or altura < AREA_MINIMA_MM:
        raise ErroGeometria(
            f"A área de conteúdo precisa ter pelo menos {formatar_mm(AREA_MINIMA_MM)} mm "
            "de largura e de altura."
        )
    if largura > pagina.largura_mm or altura > pagina.altura_mm:
        raise ErroGeometria(
            f"A área de {formatar_mm(largura)} × {formatar_mm(altura)} mm é maior que a folha "
            f"A4 ({formatar_mm(pagina.largura_mm)} × {formatar_mm(pagina.altura_mm)} mm)."
        )

    if config.centralizar_horizontal or config.x_mm is None:
        x = (pagina.largura_mm - largura) / 2.0
    else:
        x = float(config.x_mm)
    if config.centralizar_vertical or config.y_mm is None:
        y = (pagina.altura_mm - altura) / 2.0
    else:
        y = float(config.y_mm)

    tolerancia = 1e-9
    if x < -tolerancia or x + largura > pagina.largura_mm + tolerancia:
        raise ErroGeometria(
            "Com essa posição horizontal a área sairia da folha. "
            f"A distância da borda esquerda deve ficar entre 0 e "
            f"{formatar_mm(pagina.largura_mm - largura)} mm."
        )
    if y < -tolerancia or y + altura > pagina.altura_mm + tolerancia:
        raise ErroGeometria(
            "Com essa posição vertical a área sairia da folha. "
            f"A distância da borda deve ficar entre 0 e "
            f"{formatar_mm(pagina.altura_mm - altura)} mm."
        )
    return Retangulo(x, y, largura, altura)


def area_interna(area: Retangulo, margem_mm: float) -> Retangulo:
    """Área útil para o texto, descontada a margem interna."""
    if margem_mm < 0:
        raise ErroGeometria("A margem interna não pode ser negativa.")
    interna = area.recuar(margem_mm)
    if interna.largura_mm < 5 or interna.altura_mm < 5:
        raise ErroGeometria(
            f"A margem interna de {formatar_mm(margem_mm)} mm é grande demais para uma área de "
            f"{formatar_mm(area.largura_mm)} × {formatar_mm(area.altura_mm)} mm."
        )
    return interna
