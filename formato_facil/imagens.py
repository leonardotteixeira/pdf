"""Processamento de imagens: carregamento seguro e encaixe sem distorção."""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from .erros import ErroArquivo
from .geometria import Retangulo, formatar_mm

MODOS_ENCAIXE = {
    "ajustar": "Ajustar inteira (sem cortes, pode sobrar espaço em branco)",
    "preencher": "Preencher a área (sem espaço em branco, corta as sobras)",
}

# Resolução máxima embutida no PDF. Acima disso não há ganho visível na
# impressão e o arquivo só fica maior.
DPI_MAXIMO = 600
DPI_BAIXO = 150

Image.MAX_IMAGE_PIXELS = 120_000_000  # evita "bombas de descompressão"


def carregar_imagem(dados: bytes, nome: str = "imagem") -> tuple[Image.Image, list[str]]:
    """Abre a imagem, corrige a rotação EXIF e devolve-a em RGB sobre fundo branco."""
    avisos: list[str] = []
    try:
        imagem = Image.open(io.BytesIO(dados))
        imagem.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ErroArquivo(
            f"Não foi possível abrir “{nome}” como imagem. O arquivo pode estar corrompido "
            "ou não ser uma imagem PNG, JPG ou WEBP válida.",
            detalhe=str(exc),
        ) from exc

    if getattr(imagem, "n_frames", 1) > 1:
        avisos.append("A imagem é animada; apenas o primeiro quadro será usado.")
        imagem.seek(0)

    imagem = ImageOps.exif_transpose(imagem)
    if imagem.width < 1 or imagem.height < 1:
        raise ErroArquivo(f"A imagem “{nome}” não tem dimensões válidas.")
    return para_rgb(imagem), avisos


def para_rgb(imagem: Image.Image) -> Image.Image:
    """Converte para RGB; transparência vira fundo branco (como no papel)."""
    if imagem.mode in ("RGBA", "LA") or (imagem.mode == "P" and "transparency" in imagem.info):
        rgba = imagem.convert("RGBA")
        fundo = Image.new("RGB", rgba.size, (255, 255, 255))
        fundo.paste(rgba, mask=rgba.getchannel("A"))
        return fundo
    if imagem.mode != "RGB":
        return imagem.convert("RGB")
    return imagem


@dataclass(frozen=True)
class Encaixe:
    """Como a imagem será posicionada dentro do retângulo de destino."""

    modo: str
    destino: Retangulo  # onde a imagem será desenhada (mm)
    recorte_px: tuple[int, int, int, int]  # (esquerda, topo, direita, base) na imagem original
    fracao_area_em_branco: float  # modo ajustar
    fracao_imagem_cortada: float  # modo preencher
    dpi_efetivo: float
    proporcao_imagem: float  # largura / altura
    proporcao_area: float


def calcular_encaixe(largura_px: int, altura_px: int, caixa: Retangulo, modo: str) -> Encaixe:
    """Calcula o encaixe proporcional (nunca distorce: escala igual nos dois eixos)."""
    if modo not in MODOS_ENCAIXE:
        raise ValueError(f"Modo de encaixe desconhecido: {modo}")
    prop_img = largura_px / altura_px
    prop_caixa = caixa.largura_mm / caixa.altura_mm

    if modo == "ajustar":
        escala = min(caixa.largura_mm / largura_px, caixa.altura_mm / altura_px)  # mm por pixel
        w = largura_px * escala
        h = altura_px * escala
        destino = Retangulo(
            caixa.x_mm + (caixa.largura_mm - w) / 2,
            caixa.y_mm + (caixa.altura_mm - h) / 2,
            w,
            h,
        )
        recorte = (0, 0, largura_px, altura_px)
        branco = 1 - (w * h) / (caixa.largura_mm * caixa.altura_mm)
        cortado = 0.0
        dpi = 25.4 / escala
    else:
        if prop_img > prop_caixa:  # imagem mais larga: corta as laterais
            nova_largura = max(1, round(altura_px * prop_caixa))
            esquerda = (largura_px - nova_largura) // 2
            recorte = (esquerda, 0, esquerda + nova_largura, altura_px)
        else:  # imagem mais alta: corta em cima e embaixo
            nova_altura = max(1, round(largura_px / prop_caixa))
            topo = (altura_px - nova_altura) // 2
            recorte = (0, topo, largura_px, topo + nova_altura)
        rw = recorte[2] - recorte[0]
        rh = recorte[3] - recorte[1]
        destino = caixa
        branco = 0.0
        cortado = 1 - (rw * rh) / (largura_px * altura_px)
        dpi = rw / (caixa.largura_mm / 25.4)

    return Encaixe(modo, destino, recorte, max(0.0, branco), max(0.0, cortado), dpi,
                   prop_img, prop_caixa)


def explicar_proporcao(encaixe: Encaixe) -> str | None:
    """Mensagem para o usuário quando as proporções da imagem e da área diferem."""
    diferenca = abs(encaixe.proporcao_imagem - encaixe.proporcao_area) / encaixe.proporcao_area
    if diferenca < 0.01:
        return None
    if encaixe.proporcao_imagem > encaixe.proporcao_area:
        sobra, corte = "acima e abaixo da imagem", "nas laterais"
    else:
        sobra, corte = "nas laterais da imagem", "em cima e embaixo"
    prop_img = f"{encaixe.proporcao_imagem:.2f}".replace(".", ",")
    prop_area = f"{encaixe.proporcao_area:.2f}".replace(".", ",")
    base = (
        f"A proporção da imagem (largura/altura = {prop_img}) é diferente da proporção da área "
        f"({prop_area}). Para não distorcer, é preciso deixar espaço em branco ou cortar parte "
        "da imagem: "
    )
    if encaixe.modo == "ajustar":
        return base + (
            f"no modo atual (ajustar) ficarão faixas em branco {sobra}, "
            f"ocupando {encaixe.fracao_area_em_branco:.0%} da área."
        )
    return base + (
        f"no modo atual (preencher) {encaixe.fracao_imagem_cortada:.0%} da imagem "
        f"será cortada {corte}."
    )


def limitar_resolucao(imagem: Image.Image, largura_destino_mm: float) -> tuple[Image.Image, float]:
    """Reduz a imagem se ela tiver mais que ``DPI_MAXIMO`` no tamanho de destino.
    Devolve a imagem e a resolução efetiva (DPI) original."""
    dpi = imagem.width / (largura_destino_mm / 25.4)
    if dpi > DPI_MAXIMO:
        fator = DPI_MAXIMO / dpi
        nova = (max(1, round(imagem.width * fator)), max(1, round(imagem.height * fator)))
        imagem = imagem.resize(nova, Image.LANCZOS)
    return imagem, dpi


def preparar_para_pdf(imagem: Image.Image, encaixe: Encaixe) -> tuple[Image.Image, list[str]]:
    """Recorta (modo preencher) e limita a resolução para o PDF."""
    avisos: list[str] = []
    resultado = imagem.crop(encaixe.recorte_px) if encaixe.modo == "preencher" else imagem
    dpi = encaixe.dpi_efetivo
    if dpi > DPI_MAXIMO:
        fator = DPI_MAXIMO / dpi
        nova = (max(1, round(resultado.width * fator)), max(1, round(resultado.height * fator)))
        resultado = resultado.resize(nova, Image.LANCZOS)
    elif dpi < DPI_BAIXO:
        avisos.append(
            f"A imagem tem resolução baixa para impressão (cerca de {dpi:.0f} DPI na área de "
            f"{formatar_mm(encaixe.destino.largura_mm)} × {formatar_mm(encaixe.destino.altura_mm)} mm). "
            "Ela pode sair borrada."
        )
    return resultado, avisos
