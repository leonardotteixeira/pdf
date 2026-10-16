"""Importação de arquivos: validação do formato e extração inicial do conteúdo."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import PurePath

from PIL import Image

from . import extracao, imagens, ocr
from .erros import ErroArquivo
from .formatacao import texto_esta_vazio

TAMANHO_MAXIMO_MB = 50

EXTENSOES = {
    ".txt": "txt",
    ".docx": "docx",
    ".pdf": "pdf",
    ".png": "imagem",
    ".jpg": "imagem",
    ".jpeg": "imagem",
    ".webp": "imagem",
}

DESCRICAO_TIPOS = {
    "txt": "Texto simples (TXT)",
    "docx": "Documento do Word (DOCX)",
    "pdf": "Documento PDF",
    "imagem": "Imagem",
    "imagens": "Várias imagens",
}

EXTENSOES_IMAGEM = {".png", ".jpg", ".jpeg", ".webp"}
LIMITE_IMAGENS = 40

FORMATOS_ACEITOS = "TXT, DOCX, PDF, PNG, JPG, JPEG e WEBP"


@dataclass
class Documento:
    nome: str
    tipo: str  # txt | docx | pdf | imagem | imagens
    dados: bytes
    texto: str = ""
    avisos: list[str] = field(default_factory=list)
    imagem: Image.Image | None = None  # apenas para tipo "imagem"
    info_pdf: extracao.InfoPDF | None = None  # apenas para tipo "pdf"
    codificacao: str | None = None
    # Apenas para tipo "imagens" (várias imagens enviadas juntas), na ordem de uso:
    lista_imagens: list[Image.Image] = field(default_factory=list)
    nomes_arquivos: list[str] = field(default_factory=list)
    dados_arquivos: list[bytes] = field(default_factory=list)

    @property
    def descricao(self) -> str:
        return DESCRICAO_TIPOS[self.tipo]

    @property
    def precisa_ocr(self) -> bool:
        """Imagens sempre; PDFs quando há páginas sem texto selecionável."""
        if self.tipo in ("imagem", "imagens"):
            return True
        if self.tipo == "pdf" and self.info_pdf is not None:
            return bool(self.info_pdf.paginas_sem_texto)
        return False

    @property
    def permite_preservar_aparencia(self) -> bool:
        return self.tipo in ("imagem", "imagens", "pdf")

    @property
    def numero_paginas(self) -> int:
        return self.info_pdf.numero_paginas if self.info_pdf else 1

    @property
    def imagens_em_ordem(self) -> list[Image.Image]:
        """Imagens usadas no modo aparência (uma ou várias)."""
        if self.tipo == "imagens":
            return self.lista_imagens
        return [self.imagem] if self.imagem is not None else []

    def mover_imagem(self, indice: int, deslocamento: int) -> None:
        """Muda a posição de uma imagem na ordem (tipo "imagens")."""
        destino = indice + deslocamento
        if self.tipo != "imagens" or not (0 <= indice < len(self.lista_imagens))                 or not (0 <= destino < len(self.lista_imagens)):
            return
        for lista in (self.lista_imagens, self.nomes_arquivos, self.dados_arquivos):
            lista[indice], lista[destino] = lista[destino], lista[indice]


def _verificar_assinatura(tipo: str, dados: bytes, nome: str) -> None:
    """Confere se o conteúdo corresponde à extensão (evita arquivos renomeados)."""
    if tipo == "pdf" and not dados.lstrip()[:5].startswith(b"%PDF"):
        raise ErroArquivo(f"“{nome}” não é um PDF válido (o conteúdo não corresponde a um PDF).")
    if tipo == "docx" and not zipfile.is_zipfile(io.BytesIO(dados)):
        raise ErroArquivo(
            f"“{nome}” não é um documento do Word (.docx) válido. Arquivos .doc antigos precisam "
            "ser salvos como .docx no Word."
        )


def importar(nome: str, dados: bytes) -> Documento:
    """Valida o arquivo e extrai seu conteúdo. Erros geram mensagens claras."""
    extensao = PurePath(nome).suffix.lower()
    if extensao not in EXTENSOES:
        raise ErroArquivo(
            f"O formato “{extensao or 'sem extensão'}” não é suportado. "
            f"Envie um arquivo {FORMATOS_ACEITOS}."
        )
    if not dados:
        raise ErroArquivo(f"O arquivo “{nome}” está vazio (0 bytes).")
    if len(dados) > TAMANHO_MAXIMO_MB * 1024 * 1024:
        raise ErroArquivo(f"O arquivo tem mais de {TAMANHO_MAXIMO_MB} MB. Envie um arquivo menor.")

    tipo = EXTENSOES[extensao]
    _verificar_assinatura(tipo, dados, nome)
    documento = Documento(nome=nome, tipo=tipo, dados=dados)

    if tipo == "txt":
        documento.texto, documento.codificacao = extracao.extrair_txt(dados)
        if documento.codificacao not in ("utf-8-sig", "utf-16"):
            documento.avisos.append(
                "O arquivo não estava em UTF-8; ele foi lido como Windows-1252 (padrão antigo do "
                "Bloco de Notas). Confira se os acentos estão corretos."
            )
    elif tipo == "docx":
        documento.texto, avisos = extracao.extrair_docx(dados)
        documento.avisos.extend(avisos)
    elif tipo == "pdf":
        info = extracao.extrair_pdf(dados)
        documento.info_pdf = info
        documento.texto = extracao.juntar_paginas(info.textos_paginas)
        if not info.tem_texto:
            documento.avisos.append(
                "O PDF não tem texto selecionável (parece digitalizado). Use o OCR para extrair o "
                "texto ou preserve a aparência original."
            )
        elif info.paginas_sem_texto:
            paginas = ", ".join(str(i + 1) for i in info.paginas_sem_texto)
            documento.avisos.append(
                f"As páginas {paginas} não têm texto selecionável. Use o OCR para incluí-las."
            )
        if info.numero_paginas > 1:
            documento.avisos.append(
                f"O PDF tem {info.numero_paginas} páginas. No modo texto, o conteúdo das páginas é "
                "unido na ordem original; no modo aparência, cada página vai para uma folha A4."
            )
    else:
        documento.imagem, avisos = imagens.carregar_imagem(dados, nome)
        documento.avisos.extend(avisos)

    if tipo in ("txt", "docx") and texto_esta_vazio(documento.texto):
        documento.texto = ""
        documento.avisos.append("O arquivo não contém texto. Digite o conteúdo na caixa de edição.")
    return documento


def importar_varios(arquivos: list[tuple[str, bytes]]) -> Documento:
    """Importa vários arquivos de uma vez. Com mais de um, todos devem ser imagens,
    que serão montadas juntas (ou reconhecidas por OCR) na ordem recebida."""
    if not arquivos:
        raise ErroArquivo("Nenhum arquivo foi enviado.")
    if len(arquivos) == 1:
        return importar(*arquivos[0])
    nao_imagens = [nome for nome, _ in arquivos if PurePath(nome).suffix.lower() not in EXTENSOES_IMAGEM]
    if nao_imagens:
        raise ErroArquivo(
            "Para enviar vários arquivos ao mesmo tempo, todos precisam ser imagens (PNG, JPG, JPEG ou "
            f"WEBP). Estes não são: {', '.join(nao_imagens)}. Envie documentos TXT, DOCX ou PDF um de cada vez."
        )
    if len(arquivos) > LIMITE_IMAGENS:
        raise ErroArquivo(f"Envie no máximo {LIMITE_IMAGENS} imagens de uma vez (foram {len(arquivos)}).")

    documento = Documento(nome=f"{len(arquivos)} imagens", tipo="imagens", dados=b"")
    for nome, dados in arquivos:
        individual = importar(nome, dados)
        documento.lista_imagens.append(individual.imagem)
        documento.nomes_arquivos.append(nome)
        documento.dados_arquivos.append(dados)
        documento.avisos.extend(f"{nome}: {aviso}" for aviso in individual.avisos)
    return documento


DPI_OCR_PDF = 300


def executar_ocr(documento: Documento, todas_as_paginas: bool = False) -> ocr.ResultadoOCR:
    """Executa OCR na imagem ou nas páginas do PDF.

    Para PDFs, por padrão só as páginas sem texto selecionável passam por OCR;
    as demais mantêm o texto extraído diretamente (mais confiável).
    """
    if documento.tipo == "imagem":
        return ocr.reconhecer_texto(documento.imagem)
    if documento.tipo == "imagens":
        return _ocr_varias_imagens(documento)
    if documento.tipo != "pdf" or documento.info_pdf is None:
        raise ErroArquivo("O OCR só se aplica a imagens e PDFs.")

    info = documento.info_pdf
    resultados = []
    for indice in range(info.numero_paginas):
        if not todas_as_paginas and indice not in info.paginas_sem_texto:
            resultados.append((f"Página {indice + 1}", None, info.textos_paginas[indice]))
            continue
        imagem = extracao.renderizar_pagina(documento.dados, indice, DPI_OCR_PDF)
        resultado = ocr.reconhecer_texto(imagem)
        resultados.append((f"Página {indice + 1}", resultado, resultado.texto))
    return _combinar(resultados)


def _combinar(resultados: list[tuple[str, ocr.ResultadoOCR | None, str]]) -> ocr.ResultadoOCR:
    """Junta os resultados de OCR (rótulo, resultado ou None, texto) na ordem."""
    textos, avisos, duvidosas, confiancas = [], [], [], []
    idioma = "por"
    for rotulo, resultado, texto in resultados:
        textos.append(texto)
        if resultado is None:
            continue
        idioma = resultado.idioma
        duvidosas.extend(p for p in resultado.palavras_duvidosas if p not in duvidosas)
        if resultado.texto.strip():
            confiancas.append((resultado.confianca_media, len(resultado.texto)))
        for aviso in resultado.avisos:
            texto_aviso = f"{rotulo}: {aviso}"
            if texto_aviso not in avisos:
                avisos.append(texto_aviso)
    if confiancas:
        total = sum(peso for _, peso in confiancas)
        media = sum(c * peso for c, peso in confiancas) / total
    else:
        media = 100.0 if any(t.strip() for t in textos) else 0.0
    return ocr.ResultadoOCR(extracao.juntar_paginas(textos), media, idioma, duvidosas, avisos)


def _ocr_varias_imagens(documento: Documento) -> ocr.ResultadoOCR:
    resultados = []
    for nome, imagem in zip(documento.nomes_arquivos, documento.lista_imagens):
        resultado = ocr.reconhecer_texto(imagem)
        resultados.append((nome, resultado, resultado.texto))
    return _combinar(resultados)
