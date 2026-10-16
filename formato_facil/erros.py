"""Exceções do Formato Fácil PDF.

Todas as mensagens são escritas em português brasileiro e pensadas para serem
exibidas diretamente ao usuário final.
"""


class ErroFormatoFacil(Exception):
    """Erro base: a mensagem é sempre compreensível pelo usuário."""

    def __init__(self, mensagem: str, detalhe: str | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhe = detalhe

    def __str__(self) -> str:
        return self.mensagem


class ErroArquivo(ErroFormatoFacil):
    """Arquivo vazio, corrompido, protegido ou de formato não suportado."""


class ErroOCR(ErroFormatoFacil):
    """OCR indisponível ou falhou."""


class ErroGeometria(ErroFormatoFacil):
    """Dimensões ou posição da área de conteúdo inválidas."""


class ErroValidacao(ErroFormatoFacil):
    """Entrada inválida para a geração (por exemplo, texto vazio)."""


class ErroConteudoExcedente(ErroFormatoFacil):
    """O texto não cabe na área e o usuário ainda não escolheu como resolver."""

    def __init__(self, mensagem: str, paginas_necessarias: int, linhas_totais: int,
                 linhas_por_area: int):
        super().__init__(mensagem)
        self.paginas_necessarias = paginas_necessarias
        self.linhas_totais = linhas_totais
        self.linhas_por_area = linhas_por_area
