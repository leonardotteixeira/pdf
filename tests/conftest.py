import io
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from formato_facil.geometria import calcular_area  # noqa: E402

# Precisão numérica do leitor de PDF (PyMuPDF usa float de 32 bits): 5 micrômetros.
PRECISAO_MM = 0.005

TEXTO_ACENTOS = (
    "Ação, coração, pão, mãe, avó, avô, órgão, ônibus, útil, você, à, às, "
    "lâmpada, pêssego, saúde, Ç, Ã, Õ, Á, É, Í, Ó, Ú, Â, Ê, Ô, À, ü, ª, º, "
    "“aspas”, ‘simples’, travessão — reticências… € R$ 1.234,56 §"
)

TEXTO_LONGO = "\n\n".join(
    f"Parágrafo {i}: A formatação automática distribui as palavras na área útil, "
    "respeitando a largura de 7,5 centímetros e a altura de 14 centímetros, "
    "sem cortar nenhuma linha e sem distorcer o conteúdo original do usuário."
    for i in range(1, 41)
)


@pytest.fixture
def area_padrao():
    return calcular_area()


def imagem_bytes(largura, altura, formato="PNG", cor=(30, 80, 160)):
    imagem = Image.new("RGB", (largura, altura), cor)
    saida = io.BytesIO()
    imagem.save(saida, format=formato)
    return saida.getvalue()
