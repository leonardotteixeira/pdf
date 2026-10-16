"""Várias imagens na mesma área: sem distorção, sem cortes, sem sobreposição, dentro da área."""

import io

import pymupdf
import pytest
from PIL import Image

from formato_facil import importacao, ocr
from formato_facil.erros import ErroArquivo
from formato_facil.geometria import Retangulo, pt_para_mm
from formato_facil.imagens import calcular_encaixe, carregar_imagem
from formato_facil.montagem import montar
from formato_facil.pdf_gerador import gerar_pdf_montagem
from formato_facil.validacao import verificar_pdf

from .conftest import PRECISAO_MM, imagem_bytes

CONJUNTOS = {
    "tres_paisagens": [(1600, 900)] * 3,
    "misturadas": [(800, 600), (600, 800), (1000, 1000), (1920, 1080), (300, 1200)],
    "prints_altos": [(1080, 2400), (1080, 2400)],
    "muitas": [(1920, 1080), (1080, 1920), (800, 800)] * 7,  # 21 imagens
    "uma": [(1000, 700)],
}


def _sobrepoe(a: Retangulo, b: Retangulo, tol=1e-6) -> bool:
    return (a.x_mm < b.direita_mm - tol and b.x_mm < a.direita_mm - tol
            and a.y_mm < b.topo_mm - tol and b.y_mm < a.topo_mm - tol)


@pytest.mark.parametrize("nome", CONJUNTOS)
@pytest.mark.parametrize("espaco", [0.0, 2.0])
@pytest.mark.parametrize("girar", [False, True])
def test_montagem_respeita_area_e_proporcoes(area_padrao, nome, espaco, girar):
    tamanhos = CONJUNTOS[nome]
    resultado = montar(tamanhos, area_padrao, espaco, girar)
    assert sorted(p.indice for p in resultado.posicoes) == list(range(len(tamanhos)))
    for posicao in resultado.posicoes:
        w, h = tamanhos[posicao.indice]
        proporcao = (h / w) if posicao.girada else (w / h)
        destino = posicao.destino
        assert destino.largura_mm / destino.altura_mm == pytest.approx(proporcao, rel=1e-9)
        assert destino.x_mm >= area_padrao.x_mm - 1e-9
        assert destino.direita_mm <= area_padrao.direita_mm + 1e-9
        assert destino.y_mm >= area_padrao.y_mm - 1e-9
        assert destino.topo_mm <= area_padrao.topo_mm + 1e-9
    posicoes = resultado.posicoes
    for i, a in enumerate(posicoes):
        for b in posicoes[i + 1:]:
            assert not _sobrepoe(a.destino, b.destino)
    assert 0 < resultado.ocupacao <= 1


@pytest.mark.parametrize("nome", CONJUNTOS)
def test_ordem_de_leitura_preservada(area_padrao, nome):
    """Em linhas: da esquerda para a direita, de cima para baixo. Em colunas:
    de cima para baixo, da esquerda para a direita."""
    resultado = montar(CONJUNTOS[nome], area_padrao, 2.0)
    por_indice = {p.indice: p.destino for p in resultado.posicoes}
    assert [i for grupo in resultado.linhas for i in grupo] == list(range(len(CONJUNTOS[nome])))
    for grupo in resultado.linhas:
        destinos = [por_indice[i] for i in grupo]
        for a, b in zip(destinos, destinos[1:]):
            if resultado.direcao == "linhas":
                assert b.x_mm >= a.direita_mm - 1e-9
            else:
                assert b.topo_mm <= a.y_mm + 1e-9


def test_imagens_iguais_ficam_do_mesmo_tamanho(area_padrao):
    resultado = montar([(1000, 1000)] * 4, area_padrao, 2.0)
    larguras = {round(p.destino.largura_mm, 6) for p in resultado.posicoes}
    assert len(larguras) == 1


def test_colunas_quando_aproveitam_melhor(area_padrao):
    """Quatro imagens em pé e uma bem alta: empilhar em colunas é melhor."""
    resultado = montar(CONJUNTOS["misturadas"], area_padrao, 2.0)
    assert resultado.direcao == "colunas"
    assert resultado.ocupacao > 0.9


def test_espaco_minimo_entre_imagens(area_padrao):
    resultado = montar([(1000, 1000)] * 6, area_padrao, 3.0)
    for linha in resultado.linhas:
        destinos = [next(p.destino for p in resultado.posicoes if p.indice == i) for i in linha]
        for a, b in zip(destinos, destinos[1:]):
            assert b.x_mm - a.direita_mm == pytest.approx(3.0)


def test_uma_imagem_equivale_ao_ajuste_simples(area_padrao):
    resultado = montar([(1600, 900)], area_padrao, 2.0)
    encaixe = calcular_encaixe(1600, 900, area_padrao, "ajustar")
    destino = resultado.posicoes[0].destino
    assert destino.largura_mm == pytest.approx(encaixe.destino.largura_mm)
    assert destino.altura_mm == pytest.approx(encaixe.destino.altura_mm)


def test_quatro_quadrados_em_grade(area_padrao):
    """Quatro quadrados: 2 × 2 (37,5 mm cada) é melhor que empilhar (35 mm cada)."""
    resultado = montar([(1000, 1000)] * 4, area_padrao, 0.0)
    assert len(resultado.linhas) == 2
    assert resultado.menor_lado_mm == pytest.approx(37.5)


def test_girar_aumenta_imagens_deitadas(area_padrao):
    deitadas = [(1600, 900)] * 4
    normal = montar(deitadas, area_padrao, 2.0, permitir_girar=False)
    girada = montar(deitadas, area_padrao, 2.0, permitir_girar=True)
    assert girada.ocupacao > normal.ocupacao
    assert all(p.girada for p in girada.posicoes)


def test_espaco_grande_demais(area_padrao):
    with pytest.raises(ValueError):
        montar([(100, 100)] * 30, Retangulo(0, 0, 20, 20), espaco_mm=5)


# --- PDF ---------------------------------------------------------------------

def _imagens(tamanhos):
    cores = [(200, 40, 40), (40, 160, 60), (40, 70, 200), (220, 170, 30)]
    return [carregar_imagem(imagem_bytes(w, h, cor=cores[i % 4]))[0] for i, (w, h) in enumerate(tamanhos)]


def test_pdf_com_varias_imagens_na_mesma_area(area_padrao):
    tamanhos = CONJUNTOS["misturadas"]
    pdf, _, montagens = gerar_pdf_montagem(_imagens(tamanhos), area_padrao, espaco_mm=2)
    relatorio = verificar_pdf(pdf, area_padrao, tolerancia_mm=PRECISAO_MM)
    assert relatorio.aprovado, relatorio.problemas
    assert len(relatorio.paginas) == 1 and relatorio.todas_a4
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        infos = documento[0].get_image_info()
    assert len(infos) == len(tamanhos)
    proporcoes_pdf = sorted(round(pymupdf.Rect(i["bbox"]).width / pymupdf.Rect(i["bbox"]).height, 3)
                            for i in infos)
    proporcoes_orig = sorted(round(w / h, 3) for w, h in tamanhos)
    assert proporcoes_pdf == pytest.approx(proporcoes_orig, abs=0.002)
    # A imagem embutida tem a mesma proporção da caixa onde foi desenhada (sem distorção)
    for info in infos:
        caixa = pymupdf.Rect(info["bbox"])
        assert info["width"] / info["height"] == pytest.approx(caixa.width / caixa.height, rel=0.01)


def test_pdf_grupos_por_folha(area_padrao):
    pdf, _, montagens = gerar_pdf_montagem(_imagens([(1000, 800)] * 7), area_padrao, imagens_por_area=3)
    relatorio = verificar_pdf(pdf, area_padrao, tolerancia_mm=PRECISAO_MM)
    assert len(relatorio.paginas) == 3 and len(montagens) == 3
    assert relatorio.aprovado and relatorio.todas_a4
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        assert [len(p.get_image_info()) for p in documento] == [3, 3, 1]


def test_pdf_imagem_girada_mantem_proporcao(area_padrao):
    pdf, _, montagens = gerar_pdf_montagem(_imagens([(1600, 900)] * 4), area_padrao, permitir_girar=True)
    assert all(p.girada for p in montagens[0].posicoes)
    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        for info in documento[0].get_image_info():
            caixa = pymupdf.Rect(info["bbox"])
            assert caixa.height / caixa.width == pytest.approx(1600 / 900, rel=0.002)
            assert pt_para_mm(caixa.width) <= 75 + PRECISAO_MM


def test_aviso_quando_imagens_ficam_pequenas(area_padrao):
    _, avisos, _ = gerar_pdf_montagem(_imagens([(2000, 2000)] * 40), area_padrao, nomes=None)
    assert any("ficou pequena" in aviso for aviso in avisos)


# --- Importação de várias imagens ---------------------------------------------

def test_importar_varias_imagens_na_ordem():
    arquivos = [(f"foto{i}.png", imagem_bytes(100 + i, 80)) for i in range(3)]
    documento = importacao.importar_varios(arquivos)
    assert documento.tipo == "imagens"
    assert documento.nomes_arquivos == ["foto0.png", "foto1.png", "foto2.png"]
    assert [im.width for im in documento.imagens_em_ordem] == [100, 101, 102]
    documento.mover_imagem(2, -1)
    assert documento.nomes_arquivos == ["foto0.png", "foto2.png", "foto1.png"]
    assert [im.width for im in documento.lista_imagens] == [100, 102, 101]
    documento.mover_imagem(0, -1)  # fora dos limites: nada muda
    assert documento.nomes_arquivos[0] == "foto0.png"


def test_um_arquivo_continua_no_fluxo_normal():
    documento = importacao.importar_varios([("a.jpg", imagem_bytes(50, 50, "JPEG"))])
    assert documento.tipo == "imagem"


def test_varios_arquivos_que_nao_sao_imagens_geram_erro():
    with pytest.raises(ErroArquivo) as erro:
        importacao.importar_varios([("a.png", imagem_bytes(10, 10)), ("b.txt", b"texto")])
    assert "todos precisam ser imagens" in erro.value.mensagem and "b.txt" in erro.value.mensagem


def test_imagem_invalida_entre_varias_gera_erro():
    with pytest.raises(ErroArquivo) as erro:
        importacao.importar_varios([("a.png", imagem_bytes(10, 10)), ("b.png", b"quebrado")])
    assert "b.png" in erro.value.mensagem


@pytest.mark.skipif(not ocr.verificar_ocr().tem_portugues, reason="OCR em português indisponível")
def test_ocr_de_varias_imagens_na_ordem():
    from .test_importacao import _imagem_com_texto

    arquivos = []
    for texto in ["Primeira imagem", "Segunda imagem"]:
        saida = io.BytesIO()
        _imagem_com_texto([texto]).save(saida, "PNG")
        arquivos.append((texto + ".png", saida.getvalue()))
    documento = importacao.importar_varios(arquivos)
    resultado = importacao.executar_ocr(documento)
    assert resultado.texto.index("Primeira") < resultado.texto.index("Segunda")
    documento.mover_imagem(1, -1)
    resultado = importacao.executar_ocr(documento)
    assert resultado.texto.index("Segunda") < resultado.texto.index("Primeira")


def test_transparencia_em_varias_imagens(area_padrao):
    rgba = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    saida = io.BytesIO()
    rgba.save(saida, "PNG")
    documento = importacao.importar_varios([("t1.png", saida.getvalue()), ("t2.png", saida.getvalue())])
    assert all(im.mode == "RGB" for im in documento.lista_imagens)
