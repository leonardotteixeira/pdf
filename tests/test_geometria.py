"""Requisito crítico: dimensões físicas da página e da área."""

import pymupdf
import pytest

from formato_facil.erros import ErroGeometria
from formato_facil.formatacao import ConfigTexto, calcular_layout
from formato_facil.geometria import (
    ConfigArea,
    Retangulo,
    calcular_area,
    mm_para_pt,
    pt_para_mm,
)
from formato_facil.imagens import carregar_imagem
from formato_facil.pdf_gerador import OpcoesGuias, gerar_pdf_imagens, gerar_pdf_texto
from formato_facil.validacao import verificar_pdf

from .conftest import PRECISAO_MM, TEXTO_ACENTOS, imagem_bytes

A4_PT = (595.2755905511812, 841.8897637795277)


def _pdf_texto(area, texto=TEXTO_ACENTOS, **kwargs):
    layout = calcular_layout(texto, ConfigTexto(**kwargs), area)
    return gerar_pdf_texto(layout, permitir_varias_paginas=True)


def _pdf_preenchido(area):
    """PDF cuja imagem preenche toda a área: a caixa da imagem no arquivo é a área."""
    imagem, _ = carregar_imagem(imagem_bytes(750, 1400))
    pdf, _ = gerar_pdf_imagens([imagem], area, modo="preencher")
    return pdf


def test_conversao_de_unidades():
    assert mm_para_pt(25.4) == pytest.approx(72.0)
    assert pt_para_mm(72.0) == pytest.approx(25.4)
    assert mm_para_pt(210) == pytest.approx(A4_PT[0])
    assert mm_para_pt(297) == pytest.approx(A4_PT[1])


def test_area_padrao_coordenadas_exatas():
    area = calcular_area()
    assert area == Retangulo(67.5, 78.5, 75.0, 140.0)


# 1. O PDF possui dimensões A4 exatas (lido do arquivo gerado)
@pytest.mark.parametrize("modo", ["texto", "imagem"])
def test_pdf_tem_dimensoes_a4_exatas(area_padrao, modo):
    pdf = _pdf_texto(area_padrao) if modo == "texto" else _pdf_preenchido(area_padrao)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        for pagina in documento:
            assert pagina.mediabox.width == pytest.approx(A4_PT[0], abs=0.01)
            assert pagina.mediabox.height == pytest.approx(A4_PT[1], abs=0.01)
            assert pt_para_mm(pagina.mediabox.width) == pytest.approx(210.0, abs=0.005)
            assert pt_para_mm(pagina.mediabox.height) == pytest.approx(297.0, abs=0.005)
            assert pagina.rotation == 0  # retrato, sem rotação
            assert pagina.cropbox == pagina.mediabox
            # Nenhuma transformação de escala na página
            assert "UserUnit" not in documento.xref_object(pagina.xref)
    # A página NÃO pode ter o tamanho da área
    assert verificar_pdf(pdf, area_padrao).todas_a4


# 2. A área de conteúdo mede 75 × 140 mm (medida no PDF)
def test_area_mede_75_por_140_no_pdf(area_padrao):
    pdf = _pdf_preenchido(area_padrao)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        caixa = pymupdf.Rect(documento[0].get_image_info()[0]["bbox"])
    assert pt_para_mm(caixa.width) == pytest.approx(75.0, abs=0.01)
    assert pt_para_mm(caixa.height) == pytest.approx(140.0, abs=0.01)


def test_texto_justificado_ocupa_toda_a_largura(area_padrao):
    """Sem margem interna, linhas justificadas vão da borda esquerda à direita da área."""
    texto = ("palavra " * 400).strip()
    pdf = _pdf_texto(area_padrao, texto, alinhamento="justificado", margem_interna_mm=0)
    relatorio = verificar_pdf(pdf, area_padrao, tolerancia_mm=PRECISAO_MM)
    caixa = relatorio.paginas[0].caixa_texto
    assert caixa.x_mm == pytest.approx(67.5, abs=0.05)
    assert caixa.largura_mm == pytest.approx(75.0, abs=0.2)
    assert caixa.largura_mm <= 75.0
    assert relatorio.aprovado


# 3. A área está centralizada corretamente
def test_area_centralizada_no_pdf(area_padrao):
    pdf = _pdf_preenchido(area_padrao)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        pagina = documento[0]
        caixa = pymupdf.Rect(pagina.get_image_info()[0]["bbox"])
        altura = pagina.rect.height
    esquerda = pt_para_mm(caixa.x0)
    direita = 210 - pt_para_mm(caixa.x1)
    inferior = pt_para_mm(altura - caixa.y1)  # origem no canto inferior esquerdo
    superior = pt_para_mm(caixa.y0)
    assert esquerda == pytest.approx(67.5, abs=0.01)
    assert inferior == pytest.approx(78.5, abs=0.01)
    assert esquerda == pytest.approx(direita, abs=0.01)
    assert superior == pytest.approx(inferior, abs=0.01)


def test_posicao_personalizada():
    area = calcular_area(ConfigArea(centralizar_horizontal=False, x_mm=10,
                                    centralizar_vertical=False, y_mm=20))
    assert (area.x_mm, area.y_mm, area.largura_mm, area.altura_mm) == (10, 20, 75, 140)
    pdf = _pdf_preenchido(area)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        caixa = pymupdf.Rect(documento[0].get_image_info()[0]["bbox"])
        altura = documento[0].rect.height
    assert pt_para_mm(caixa.x0) == pytest.approx(10, abs=0.01)
    assert pt_para_mm(altura - caixa.y1) == pytest.approx(20, abs=0.01)


def test_dimensoes_alteradas_sao_respeitadas_sem_ajuste_automatico():
    area = calcular_area(ConfigArea(largura_mm=60, altura_mm=90))
    pdf = _pdf_preenchido(area)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        caixa = pymupdf.Rect(documento[0].get_image_info()[0]["bbox"])
        assert pt_para_mm(documento[0].rect.width) == pytest.approx(210, abs=0.005)
    assert pt_para_mm(caixa.width) == pytest.approx(60, abs=0.01)
    assert pt_para_mm(caixa.height) == pytest.approx(90, abs=0.01)


@pytest.mark.parametrize("config", [
    ConfigArea(largura_mm=250),
    ConfigArea(altura_mm=300),
    ConfigArea(largura_mm=5),
    ConfigArea(centralizar_horizontal=False, x_mm=150),
    ConfigArea(centralizar_vertical=False, y_mm=-1),
])
def test_area_fora_da_folha_gera_erro(config):
    with pytest.raises(ErroGeometria) as erro:
        calcular_area(config)
    assert erro.value.mensagem


def test_guias_desligadas_por_padrao(area_padrao):
    pdf = _pdf_texto(area_padrao)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        assert documento[0].get_drawings() == []


def test_contorno_opcional_fica_dentro_da_area(area_padrao):
    layout = calcular_layout(TEXTO_ACENTOS, ConfigTexto(), area_padrao)
    pdf = gerar_pdf_texto(layout, OpcoesGuias(contorno=True))
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        assert len(documento[0].get_drawings()) == 1
    assert verificar_pdf(pdf, area_padrao, tolerancia_mm=PRECISAO_MM).aprovado


def test_pdf_sugere_impressao_em_tamanho_real(area_padrao):
    pdf = _pdf_texto(area_padrao)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        catalogo = documento.xref_object(documento.pdf_catalog())
        chave = documento.xref_get_key(documento.pdf_catalog(), "ViewerPreferences")
        assert "ViewerPreferences" in catalogo
        preferencias = documento.xref_object(int(chave[1].split()[0]))
        assert "/PrintScaling /None" in preferencias
