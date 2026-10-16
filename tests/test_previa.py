"""Pré-visualização: proporções da folha e linhas de referência só na imagem."""

import pytest

from formato_facil import previa
from formato_facil.formatacao import ConfigTexto, calcular_layout
from formato_facil.pdf_gerador import gerar_pdf_texto

from .conftest import TEXTO_ACENTOS, TEXTO_LONGO


@pytest.fixture
def pdf(area_padrao):
    return gerar_pdf_texto(calcular_layout(TEXTO_LONGO, ConfigTexto(), area_padrao),
                           permitir_varias_paginas=True)


@pytest.mark.parametrize("referencias", [True, False])
def test_folha_mantem_proporcao_a4(pdf, area_padrao, referencias):
    imagem = previa.folha_anotada(pdf, 0, area_padrao, 3.0, referencias, largura_px=600)
    assert imagem.width == pytest.approx(600, abs=2)
    assert imagem.height / imagem.width == pytest.approx(297 / 210, rel=0.005)


def test_referencias_aparecem_apenas_quando_pedidas(pdf, area_padrao):
    com = previa.folha_anotada(pdf, 0, area_padrao, 3.0, True)
    sem = previa.folha_anotada(pdf, 0, area_padrao, 3.0, False)
    azul = (37, 99, 235)
    assert azul in {cor for _, cor in com.getcolors(1 << 20)}
    assert azul not in {cor for _, cor in sem.getcolors(1 << 20)}


def test_area_ampliada_tem_proporcao_da_area(area_padrao):
    pdf = gerar_pdf_texto(calcular_layout(TEXTO_ACENTOS, ConfigTexto(), area_padrao))
    imagem = previa.area_ampliada(pdf, 0, area_padrao, True, dpi=200)
    # área de 75 × 140 mm + 3 mm de folga em cada lado
    assert imagem.width / imagem.height == pytest.approx(81 / 146, rel=0.01)


def test_paginas_da_previa(pdf):
    assert previa.contar_paginas(pdf) > 1
    assert previa.renderizar(pdf, 99, 30).width > 0  # índice além do fim mostra a última folha
