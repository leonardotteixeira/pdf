"""Interface: executa o app.py sem navegador (streamlit.testing) e percorre o fluxo principal."""

from pathlib import Path

import pymupdf
import pytest
from streamlit.testing.v1 import AppTest

from .conftest import TEXTO_LONGO

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def _app():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    return at


def _botao(at, texto):
    return next(b for b in at.button if texto in b.label)


def test_tela_inicial_em_portugues():
    at = _app()
    textos = " ".join(m.value for m in at.markdown)
    assert "Formato" in textos and "Transforme qualquer conteúdo em um PDF pronto para imprimir." in textos
    assert _botao(at, "Gerar PDF").disabled  # sem conteúdo não gera
    assert any("Como imprimir" in e.label for e in at.expander)


def test_fluxo_texto_gerar_pdf():
    at = _app()
    at.text_area(key="texto_editor").set_value("Olá! Ação, coração e informação.").run()
    assert not at.exception
    assert any("O texto cabe na área" in s.value for s in at.success)
    _botao(at, "Gerar PDF").click().run()
    assert not at.exception
    assert any("PDF gerado e verificado" in s.value for s in at.success)
    pdf = at.session_state["pdf_gerado"]
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        assert documento.page_count == 1
        assert "coração" in documento[0].get_text()
    assert at.session_state["relatorio"].aprovado


def test_texto_longo_exige_escolha_antes_de_gerar():
    at = _app()
    at.text_area(key="texto_editor").set_value(TEXTO_LONGO).run()
    assert any("não cabe em uma única área" in w.value for w in at.warning)
    assert _botao(at, "Gerar PDF").disabled
    at.radio(key="escolha_excesso").set_value(0).run()  # distribuir em várias folhas
    assert not _botao(at, "Gerar PDF").disabled
    _botao(at, "Gerar PDF").click().run()
    relatorio = at.session_state["relatorio"]
    assert len(relatorio.paginas) > 1 and relatorio.aprovado


def test_pdf_desatualizado_nao_pode_ser_baixado():
    at = _app()
    at.text_area(key="texto_editor").set_value("Primeira versão.").run()
    _botao(at, "Gerar PDF").click().run()
    assert at.session_state["assinatura_gerada"]
    at.text_area(key="texto_editor").set_value("Segunda versão.").run()
    assert any("mudaram desde a última geração" in i.value for i in at.info)


def test_area_invalida_mostra_erro():
    at = _app()
    at.text_area(key="texto_editor").set_value("Texto").run()
    at.radio(key="cfg_pos_h").set_value("Personalizada").run()
    at.number_input(key="cfg_x_mm").set_value(200.0).run()
    assert not at.exception
    assert any("sairia da folha" in e.value for e in at.error)
    assert _botao(at, "Gerar PDF").disabled


@pytest.mark.parametrize("acao,esperado", [
    ("Corrigir quebras", "linha   um linha dois"),
    ("Tirar espaços extras", "linha um\nlinha dois"),
])
def test_ferramentas_de_edicao(acao, esperado):
    at = _app()
    at.text_area(key="texto_editor").set_value("linha   um\nlinha dois").run()
    _botao(at, acao).click().run()
    assert at.text_area(key="texto_editor").value == esperado
