"""Extração de texto de TXT, DOCX e PDF, e renderização de páginas de PDF."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF
from PIL import Image

from .erros import ErroArquivo
from .formatacao import normalizar_texto

# Uma página com menos caracteres que isso é tratada como "sem texto"
# (provavelmente digitalizada) e pode passar por OCR.
MINIMO_CARACTERES_PAGINA = 15
LIMITE_PAGINAS_PDF = 200


# ---------------------------------------------------------------------------
# TXT
# ---------------------------------------------------------------------------

def extrair_txt(dados: bytes) -> tuple[str, str]:
    """Decodifica um arquivo de texto. Devolve (texto, codificação detectada)."""
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        tentativas = ["utf-16"]
    else:
        tentativas = ["utf-8-sig", "cp1252", "latin-1"]
    for codificacao in tentativas:
        try:
            texto = dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
        if "\x00" in texto:
            break
        return normalizar_texto(texto), codificacao
    raise ErroArquivo(
        "O arquivo .txt não parece conter texto (pode ser um arquivo binário renomeado)."
    )


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------

def extrair_docx(dados: bytes) -> tuple[str, list[str]]:
    """Extrai parágrafos e tabelas do corpo do documento, na ordem original."""
    import docx  # python-docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    avisos: list[str] = []
    if not zipfile.is_zipfile(io.BytesIO(dados)):
        raise ErroArquivo(
            "O arquivo não é um documento do Word (.docx) válido. Se ele for um .doc antigo, "
            "abra-o no Word e salve como .docx."
        )
    try:
        documento = docx.Document(io.BytesIO(dados))
    except Exception as exc:  # noqa: BLE001
        raise ErroArquivo("Não foi possível ler o documento do Word. O arquivo pode estar corrompido.",
                          detalhe=str(exc)) from exc

    blocos: list[str] = []
    tem_tabela = False
    tem_imagem = False
    corpo = documento.element.body
    for elemento in corpo.iterchildren():
        marcador = elemento.tag.rsplit("}", 1)[-1]
        if marcador == "p":
            paragrafo = Paragraph(elemento, documento)
            if elemento.xpath(".//w:drawing") or elemento.xpath(".//w:pict"):
                tem_imagem = True
            blocos.append(paragrafo.text)
        elif marcador == "tbl":
            tem_tabela = True
            tabela = Table(elemento, documento)
            for linha in tabela.rows:
                celulas = []
                for celula in linha.cells:
                    valor = " ".join(celula.text.split())
                    if not celulas or celulas[-1] != valor:  # células mescladas se repetem
                        celulas.append(valor)
                blocos.append(" | ".join(celulas))

    # Parágrafos do Word viram parágrafos separados por linha em branco;
    # parágrafos vazios consecutivos são reduzidos a um só separador.
    paragrafos = [normalizar_texto(b).strip("\n") for b in blocos]
    texto = "\n\n".join(p for p in paragrafos if p.strip())

    if tem_tabela:
        avisos.append("O documento tem tabelas; cada linha da tabela foi convertida em uma linha "
                      "de texto com as células separadas por “|”.")
    if tem_imagem:
        avisos.append("O documento tem imagens incorporadas, que não são incluídas no modo texto.")
    return texto, avisos


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@dataclass
class InfoPDF:
    numero_paginas: int
    textos_paginas: list[str]
    paginas_sem_texto: list[int]  # índices (base 0)

    @property
    def tem_texto(self) -> bool:
        return any(t.strip() for t in self.textos_paginas)


def abrir_pdf(dados: bytes) -> fitz.Document:
    try:
        documento = fitz.open(stream=dados, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise ErroArquivo("Não foi possível abrir o PDF. O arquivo pode estar corrompido.",
                          detalhe=str(exc)) from exc
    if documento.needs_pass:
        documento.close()
        raise ErroArquivo("O PDF está protegido por senha. Remova a senha e envie novamente.")
    if documento.page_count == 0:
        documento.close()
        raise ErroArquivo("O PDF não tem nenhuma página.")
    return documento


def extrair_pdf(dados: bytes) -> InfoPDF:
    """Extrai o texto selecionável de cada página, em ordem de leitura."""
    flags = fitz.TEXTFLAGS_TEXT & ~fitz.TEXT_PRESERVE_LIGATURES
    with abrir_pdf(dados) as documento:
        if documento.page_count > LIMITE_PAGINAS_PDF:
            raise ErroArquivo(
                f"O PDF tem {documento.page_count} páginas; o limite é {LIMITE_PAGINAS_PDF}."
            )
        textos: list[str] = []
        sem_texto: list[int] = []
        for indice, pagina in enumerate(documento):
            blocos = pagina.get_text("blocks", sort=True, flags=flags)
            partes = [b[4].strip() for b in blocos if b[6] == 0 and b[4].strip()]
            texto = normalizar_texto("\n\n".join(partes))
            textos.append(texto)
            if len(texto.strip()) < MINIMO_CARACTERES_PAGINA:
                sem_texto.append(indice)
        return InfoPDF(documento.page_count, textos, sem_texto)


def juntar_paginas(textos: list[str]) -> str:
    """Texto das páginas em ordem, separadas por linha em branco."""
    return "\n\n".join(t for t in textos if t.strip())


def renderizar_pagina(dados: bytes, indice: int, dpi: float) -> Image.Image:
    with abrir_pdf(dados) as documento:
        pagina = documento[indice]
        pixmap = pagina.get_pixmap(dpi=max(36, int(dpi)), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


LIMITE_PAGINAS_APARENCIA = 50


def paginas_como_imagens(dados: bytes, caixa_largura_mm: float, caixa_altura_mm: float,
                         dpi_alvo: float = 400) -> list[Image.Image]:
    """Rasteriza cada página do PDF com resolução suficiente para a área de destino
    (cerca de ``dpi_alvo`` DPI depois de reduzida), sem desperdiçar memória."""
    imagens: list[Image.Image] = []
    with abrir_pdf(dados) as documento:
        if documento.page_count > LIMITE_PAGINAS_APARENCIA:
            raise ErroArquivo(
                f"O modo de preservar a aparência aceita até {LIMITE_PAGINAS_APARENCIA} páginas; "
                f"este PDF tem {documento.page_count}."
            )
        for pagina in documento:
            largura_mm = pagina.rect.width * 25.4 / 72
            altura_mm = pagina.rect.height * 25.4 / 72
            fator = max(caixa_largura_mm / largura_mm, caixa_altura_mm / altura_mm)
            dpi = min(600, max(72, dpi_alvo * fator))
            pixmap = pagina.get_pixmap(dpi=int(dpi), alpha=False)
            imagens.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
    return imagens


def tamanho_pagina_mm(dados: bytes, indice: int) -> tuple[float, float]:
    with abrir_pdf(dados) as documento:
        retangulo = documento[indice].rect
        return retangulo.width * 25.4 / 72, retangulo.height * 25.4 / 72
