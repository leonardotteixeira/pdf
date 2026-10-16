"""Formatação de texto: limites, acentos, texto vazio e texto longo."""

import pymupdf
import pytest

from formato_facil import fontes
from formato_facil.erros import ErroConteudoExcedente, ErroValidacao
from formato_facil.formatacao import (
    ConfigTexto,
    calcular_layout,
    contar_palavras,
    corrigir_quebras_de_linha,
    maior_tamanho_que_cabe,
    normalizar_texto,
    remover_espacos_extras,
)
from formato_facil.geometria import A4_ALTURA_MM, ConfigArea, calcular_area
from formato_facil.pdf_gerador import gerar_pdf_texto, verificar_excesso
from formato_facil.validacao import verificar_pdf

from .conftest import PRECISAO_MM, TEXTO_ACENTOS, TEXTO_LONGO

FONTES = list(fontes.fontes_disponiveis())


def _gerar(texto, area, varias=True, **kwargs):
    layout = calcular_layout(texto, ConfigTexto(**kwargs), area)
    return layout, gerar_pdf_texto(layout, permitir_varias_paginas=varias)


def _tinta_fora_da_area(pdf, area, dpi=300):
    """Conta pixels não brancos fora da área, rasterizando o PDF (verificação física)."""
    fora = 0
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        for pagina in documento:
            pix = pagina.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
            px_mm = pix.width / 210.0
            x0 = int(area.x_mm * px_mm) - 1
            x1 = int(area.direita_mm * px_mm) + 2
            y0 = int((A4_ALTURA_MM - area.topo_mm) * px_mm) - 1
            y1 = int((A4_ALTURA_MM - area.y_mm) * px_mm) + 2
            amostras = pix.samples
            largura = pix.width
            for y in range(pix.height):
                linha = amostras[y * largura:(y + 1) * largura]
                if y < y0 or y >= y1:
                    fora += sum(1 for v in linha if v < 250)
                else:
                    fora += sum(1 for v in linha[:max(0, x0)] if v < 250)
                    fora += sum(1 for v in linha[x1:] if v < 250)
    return fora


# 4. O conteúdo não ultrapassa os limites da área
@pytest.mark.parametrize("fonte", FONTES)
@pytest.mark.parametrize("alinhamento", ["esquerda", "justificado", "centralizado"])
def test_conteudo_dentro_da_area(area_padrao, fonte, alinhamento):
    texto = (TEXTO_ACENTOS + " ") * 6 + "https://exemplo.com.br/" + "a" * 120
    layout, pdf = _gerar(texto, area_padrao, fonte=fonte, alinhamento=alinhamento,
                         margem_interna_mm=0, tamanho_pt=11)
    relatorio = verificar_pdf(pdf, area_padrao, tolerancia_mm=PRECISAO_MM)
    assert relatorio.aprovado, relatorio.problemas
    for pagina in relatorio.paginas:
        caixa = pagina.caixa_texto
        assert caixa.x_mm >= area_padrao.x_mm - PRECISAO_MM
        assert caixa.direita_mm <= area_padrao.direita_mm + PRECISAO_MM
        assert caixa.y_mm >= area_padrao.y_mm - PRECISAO_MM
        assert caixa.topo_mm <= area_padrao.topo_mm + PRECISAO_MM


def test_nenhuma_tinta_fora_da_area_rasterizado(area_padrao):
    texto = ("ÁÃÊÇ ÔÚ gjpqy " + TEXTO_ACENTOS + " ") * 8
    _, pdf = _gerar(texto, area_padrao, margem_interna_mm=0, tamanho_pt=12, alinhamento="justificado")
    assert _tinta_fora_da_area(pdf, area_padrao) == 0


def test_margem_interna_respeitada(area_padrao):
    layout, pdf = _gerar(TEXTO_LONGO, area_padrao, margem_interna_mm=5)
    interna = area_padrao.recuar(5)
    relatorio = verificar_pdf(pdf, interna, tolerancia_mm=PRECISAO_MM)
    assert relatorio.aprovado, relatorio.problemas


def test_linhas_nao_excedem_a_largura(area_padrao):
    layout = calcular_layout(TEXTO_LONGO, ConfigTexto(tamanho_pt=9), area_padrao)
    for pagina in layout.paginas:
        assert len(pagina) <= layout.linhas_por_area
        for linha in pagina:
            assert linha.largura_pt <= layout.interna.largura_pt


# 5. O texto em português mantém seus acentos
@pytest.mark.parametrize("fonte", FONTES)
def test_acentos_preservados_e_fonte_incorporada(area_padrao, fonte):
    _, pdf = _gerar(TEXTO_ACENTOS, area_padrao, fonte=fonte)
    relatorio = verificar_pdf(pdf, area_padrao)
    extraido = " ".join(relatorio.texto_extraido.split())
    for palavra in TEXTO_ACENTOS.split():
        assert palavra in extraido, palavra
    assert relatorio.fontes_embutidas
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        for _, extensao, tipo, *_ in documento[0].get_fonts():
            assert extensao == "ttf" and tipo == "TrueType"


def test_texto_e_pesquisavel(area_padrao):
    _, pdf = _gerar(TEXTO_LONGO, area_padrao, alinhamento="justificado")
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        assert documento[0].search_for("formatação automática")


def test_acentos_decompostos_sao_normalizados():
    decomposto = "Ação"  # "Ação" em forma NFD
    assert normalizar_texto(decomposto) == "Ação"


def test_caracteres_sem_glifo_sao_detectados(area_padrao):
    layout = calcular_layout("Olá 😀 mundo", ConfigTexto(), area_padrao)
    assert "😀" in layout.caracteres_sem_glifo
    assert "á" not in layout.caracteres_sem_glifo


# 6. Arquivos/textos vazios
@pytest.mark.parametrize("texto", ["", "   ", "\n\n\t\n"])
def test_texto_vazio_nao_gera_pdf(area_padrao, texto):
    layout = calcular_layout(texto, ConfigTexto(), area_padrao)
    with pytest.raises(ErroValidacao) as erro:
        gerar_pdf_texto(layout)
    assert "Não há texto" in erro.value.mensagem


# 7. Textos longos são identificados antes de serem cortados
def test_texto_longo_detectado_antes_da_geracao(area_padrao):
    layout = calcular_layout(TEXTO_LONGO, ConfigTexto(), area_padrao)
    assert not layout.cabe_em_uma_area
    assert layout.numero_paginas > 1
    with pytest.raises(ErroConteudoExcedente) as erro:
        verificar_excesso(layout, permitir_varias_paginas=False)
    assert erro.value.paginas_necessarias == layout.numero_paginas
    with pytest.raises(ErroConteudoExcedente):
        gerar_pdf_texto(layout, permitir_varias_paginas=False)


def test_texto_longo_em_varias_folhas_sem_perder_nada(area_padrao):
    layout, pdf = _gerar(TEXTO_LONGO, area_padrao, varias=True)
    relatorio = verificar_pdf(pdf, area_padrao)
    assert len(relatorio.paginas) == layout.numero_paginas
    assert relatorio.aprovado, relatorio.problemas
    palavras_originais = TEXTO_LONGO.split()
    palavras_pdf = relatorio.texto_extraido.split()
    assert palavras_pdf == palavras_originais
    # Todas as folhas são A4 com a área na mesma posição
    posicoes = {(round(p.caixa_texto.x_mm, 2), round(p.caixa_texto.topo_mm, 1)) for p in relatorio.paginas}
    assert len(posicoes) == 1


def test_ultima_linha_nunca_cortada(area_padrao):
    """Texto que excede a área em exatamente uma linha deve ser detectado."""
    layout = calcular_layout("x", ConfigTexto(), area_padrao)
    n = layout.linhas_por_area
    cabe = calcular_layout("\n".join(f"linha {i}" for i in range(n)), ConfigTexto(), area_padrao)
    excede = calcular_layout("\n".join(f"linha {i}" for i in range(n + 1)), ConfigTexto(), area_padrao)
    assert cabe.cabe_em_uma_area
    assert not excede.cabe_em_uma_area
    assert excede.paginas[1][0].texto == f"linha {n}"


def test_reducao_de_fonte_respeita_minimo(area_padrao):
    texto = TEXTO_LONGO[:2500]
    tamanho = maior_tamanho_que_cabe(texto, ConfigTexto(tamanho_pt=11), area_padrao, minimo_pt=5)
    assert tamanho is not None and 5 <= tamanho < 11
    assert calcular_layout(texto, ConfigTexto(tamanho_pt=tamanho), area_padrao).cabe_em_uma_area
    assert not calcular_layout(texto, ConfigTexto(tamanho_pt=tamanho + 0.25), area_padrao).cabe_em_uma_area
    # Com um mínimo alto demais, informa que não cabe (em vez de cortar)
    assert maior_tamanho_que_cabe(TEXTO_LONGO * 3, ConfigTexto(tamanho_pt=11), area_padrao, minimo_pt=9) is None


def test_tamanho_da_fonte_nao_muda_sozinho(area_padrao):
    layout = calcular_layout(TEXTO_LONGO, ConfigTexto(tamanho_pt=10), area_padrao)
    assert layout.config.tamanho_pt == 10


def test_paragrafos_preservados(area_padrao):
    texto = "Primeiro parágrafo.\n\nSegundo parágrafo."
    layout = calcular_layout(texto, ConfigTexto(), area_padrao)
    linhas = layout.paginas[0]
    assert [linha.texto for linha in linhas] == ["Primeiro parágrafo.", "", "Segundo parágrafo."]


def test_corrigir_quebras_e_espacos():
    texto = "Esta linha foi\nquebrada pelo OCR.\n\nNovo parágrafo com guarda-\nchuva."
    assert corrigir_quebras_de_linha(texto) == (
        "Esta linha foi quebrada pelo OCR.\n\nNovo parágrafo com guarda-chuva."
    )
    assert remover_espacos_extras("a   b\n\n\n\nc  ") == "a b\n\nc"
    assert contar_palavras("um dois  três") == 3


def test_configuracao_invalida(area_padrao):
    with pytest.raises(ErroValidacao):
        calcular_layout("texto", ConfigTexto(tamanho_pt=100), area_padrao)
    with pytest.raises(ErroValidacao):
        calcular_layout("texto", ConfigTexto(tamanho_pt=72, margem_interna_mm=30),
                        calcular_area(ConfigArea(largura_mm=70, altura_mm=70)))
