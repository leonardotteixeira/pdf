"""Reconhecimento de texto (OCR) com Tesseract, em português.

O OCR roda localmente; nenhuma imagem é enviada para serviços externos.
O texto reconhecido nunca é "corrigido" automaticamente: palavras com baixa
confiança são apenas apontadas para revisão manual.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

from .erros import ErroOCR

try:
    import pytesseract
except ImportError:  # pragma: no cover - dependência obrigatória no requirements
    pytesseract = None

PASTA_TESSDATA_PROJETO = Path(__file__).resolve().parent.parent / "tessdata"

CONFIANCA_BAIXA = 75.0  # média abaixo disso gera aviso
CONFIANCA_PALAVRA_BAIXA = 60.0

INSTRUCOES_INSTALACAO = (
    "Para ativar o OCR, instale o Tesseract OCR para Windows "
    "(comando: winget install UB-Mannheim.TesseractOCR) e reinicie o aplicativo. "
    "O arquivo de idioma português (por.traineddata) deve estar na pasta “tessdata” do "
    "aplicativo ou do Tesseract."
)


@dataclass
class StatusOCR:
    disponivel: bool
    executavel: str | None = None
    versao: str | None = None
    idiomas: list[str] = field(default_factory=list)
    pasta_dados: str | None = None
    mensagem: str = ""

    @property
    def tem_portugues(self) -> bool:
        return "por" in self.idiomas


@dataclass
class ResultadoOCR:
    texto: str
    confianca_media: float  # 0 a 100
    idioma: str
    palavras_duvidosas: list[str]
    avisos: list[str]

    @property
    def confianca_baixa(self) -> bool:
        return self.confianca_media < CONFIANCA_BAIXA


def _candidatos_executavel() -> list[str]:
    candidatos = []
    variavel = os.environ.get("FORMATO_FACIL_TESSERACT")
    if variavel:
        candidatos.append(variavel)
    no_path = shutil.which("tesseract")
    if no_path:
        candidatos.append(no_path)
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        candidatos.append(os.path.join(base, "Tesseract-OCR", "tesseract.exe"))
    return candidatos


def _garantir_configs(pasta: Path) -> None:
    """O pytesseract usa o arquivo de configuração ``configs/tsv`` da pasta de
    idiomas; sem ele o Tesseract não gera a tabela de palavras."""
    configs = pasta / "configs"
    try:
        configs.mkdir(exist_ok=True)
        for nome, conteudo in (("tsv", "tessedit_create_tsv 1\n"), ("txt", "tessedit_create_txt 1\n")):
            arquivo = configs / nome
            if not arquivo.is_file():
                arquivo.write_text(conteudo, encoding="ascii")
    except OSError:
        pass


def _listar_idiomas(executavel: str, pasta: str | None) -> list[str]:
    """Lista os idiomas instalados.

    Não usamos ``pytesseract.get_languages`` porque ele falha quando o caminho
    da pasta tem acentos (o Tesseract responde na codificação do Windows).
    """
    comando = [executavel, "--list-langs"]
    if pasta:
        comando[1:1] = ["--tessdata-dir", pasta]
    resultado = subprocess.run(comando, capture_output=True, timeout=30,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if resultado.returncode != 0:
        raise RuntimeError(resultado.stderr.decode("utf-8", "replace"))
    saida = resultado.stdout.decode("utf-8", "replace").splitlines()
    return sorted(linha.strip() for linha in saida[1:] if linha.strip())


@lru_cache(maxsize=1)
def verificar_ocr() -> StatusOCR:
    """Descobre se o Tesseract está instalado e quais idiomas tem."""
    if pytesseract is None:
        return StatusOCR(False, mensagem="O pacote pytesseract não está instalado. " + INSTRUCOES_INSTALACAO)

    executavel = next((c for c in _candidatos_executavel() if c and os.path.isfile(c)), None)
    if executavel is None:
        return StatusOCR(False, mensagem="O Tesseract OCR não foi encontrado neste computador. "
                                         + INSTRUCOES_INSTALACAO)
    pytesseract.pytesseract.tesseract_cmd = executavel
    try:
        versao = str(pytesseract.get_tesseract_version())
    except Exception as exc:  # noqa: BLE001
        return StatusOCR(False, executavel, mensagem=f"O Tesseract foi encontrado, mas não pôde ser executado ({exc}).")

    # Prefere a pasta de idiomas do aplicativo se ela tiver português.
    pastas = []
    if (PASTA_TESSDATA_PROJETO / "por.traineddata").is_file():
        _garantir_configs(PASTA_TESSDATA_PROJETO)
        pastas.append(str(PASTA_TESSDATA_PROJETO))
    pastas.append(None)  # pasta padrão do Tesseract

    melhor = StatusOCR(True, executavel, versao)
    for pasta in pastas:
        try:
            idiomas = _listar_idiomas(executavel, pasta)
        except Exception:  # noqa: BLE001
            continue
        if "por" in idiomas:
            return StatusOCR(True, executavel, versao, idiomas, pasta,
                             "OCR disponível com idioma português.")
        if not melhor.idiomas:
            melhor = StatusOCR(True, executavel, versao, idiomas, pasta)

    melhor.mensagem = (
        "OCR disponível apenas parcialmente: o idioma português não está instalado, "
        "então acentos e palavras em português podem ser reconhecidos com erros. "
        + INSTRUCOES_INSTALACAO
    )
    return melhor


def _preparar(imagem: Image.Image) -> Image.Image:
    """Tons de cinza e ampliação de imagens pequenas (melhora prints de tela)."""
    cinza = ImageOps.grayscale(imagem)
    menor_lado = min(cinza.size)
    if menor_lado < 1000:
        fator = min(3.0, 1500 / max(1, menor_lado))
        if fator > 1.2:
            cinza = cinza.resize((round(cinza.width * fator), round(cinza.height * fator)), Image.LANCZOS)
    return cinza


def reconhecer_texto(imagem: Image.Image) -> ResultadoOCR:
    """Executa o OCR e reconstrói linhas e parágrafos a partir da posição das palavras."""
    status = verificar_ocr()
    if not status.disponivel:
        raise ErroOCR(status.mensagem)

    idioma = "por" if status.tem_portugues else ("eng" if "eng" in status.idiomas else None)
    if idioma is None:
        raise ErroOCR("Nenhum idioma do OCR está instalado. " + INSTRUCOES_INSTALACAO)

    avisos = []
    if idioma != "por":
        avisos.append(status.mensagem)

    # A pasta de idiomas vai pela variável de ambiente: no Windows o pytesseract
    # repassa as aspas de "--tessdata-dir" literalmente e o caminho não é encontrado.
    anterior = os.environ.get("TESSDATA_PREFIX")
    if status.pasta_dados:
        os.environ["TESSDATA_PREFIX"] = status.pasta_dados
    try:
        dados = pytesseract.image_to_data(
            _preparar(imagem),
            lang=idioma,
            config="--psm 3",
            output_type=pytesseract.Output.DICT,
        )
    except Exception as exc:  # noqa: BLE001
        raise ErroOCR("O OCR falhou ao processar a imagem.", detalhe=str(exc)) from exc
    finally:
        if status.pasta_dados:
            if anterior is None:
                os.environ.pop("TESSDATA_PREFIX", None)
            else:
                os.environ["TESSDATA_PREFIX"] = anterior

    paragrafos: dict[tuple[int, int], dict[int, list[str]]] = {}
    ordem: list[tuple[int, int]] = []
    confiancas: list[tuple[float, int]] = []
    duvidosas: list[str] = []
    for i, palavra in enumerate(dados["text"]):
        palavra = (palavra or "").strip()
        try:
            conf = float(dados["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not palavra or conf < 0:
            continue
        chave = (dados["block_num"][i], dados["par_num"][i])
        if chave not in paragrafos:
            paragrafos[chave] = {}
            ordem.append(chave)
        paragrafos[chave].setdefault(dados["line_num"][i], []).append(palavra)
        confiancas.append((conf, len(palavra)))
        if conf < CONFIANCA_PALAVRA_BAIXA and palavra not in duvidosas:
            duvidosas.append(palavra)

    blocos = []
    for chave in ordem:
        linhas = paragrafos[chave]
        blocos.append("\n".join(" ".join(linhas[n]) for n in sorted(linhas)))
    texto = "\n\n".join(blocos)

    if confiancas:
        total = sum(peso for _, peso in confiancas)
        media = sum(conf * peso for conf, peso in confiancas) / total
    else:
        media = 0.0

    if not texto.strip():
        avisos.append("O OCR não encontrou texto legível nesta imagem.")
    elif media < CONFIANCA_BAIXA:
        avisos.append(
            f"O OCR teve confiança baixa ({media:.0f}%). Revise o texto com atenção antes de gerar o PDF."
        )
    return ResultadoOCR(texto, media, idioma, duvidosas, avisos)
