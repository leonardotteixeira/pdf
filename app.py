"""Interface do Formato Fácil PDF (Streamlit, executada localmente).

Execute com:  iniciar.bat   (ou: python -m streamlit run app.py)
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import streamlit as st

from formato_facil import NOME_APLICATIVO, extracao, fontes, imagens, importacao, ocr, previa
from formato_facil.erros import ErroConteudoExcedente, ErroFormatoFacil
from formato_facil.formatacao import (
    ALINHAMENTOS,
    ConfigTexto,
    calcular_layout,
    contar_palavras,
    corrigir_quebras_de_linha,
    descrever_espaco,
    maior_tamanho_que_cabe,
    remover_espacos_extras,
    texto_esta_vazio,
)
from formato_facil.geometria import (
    A4_ALTURA_MM,
    A4_LARGURA_MM,
    ConfigArea,
    Retangulo,
    calcular_area,
    formatar_mm,
)
from formato_facil.pdf_gerador import (
    OpcoesGuias,
    gerar_pdf_imagens,
    gerar_pdf_montagem,
    gerar_pdf_texto,
)
from formato_facil.validacao import verificar_pdf

st.set_page_config(page_title=NOME_APLICATIVO, page_icon="📄", layout="wide",
                   initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# Estilo (inclui a tradução dos textos internos do componente de upload)
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px;}
.ff-titulo {font-size: 2.3rem; font-weight: 800; letter-spacing: -0.02em; margin: 0; color: #0f172a;
            line-height: 1.15;}
.ff-titulo span {color: #2563eb;}
.ff-subtitulo {color: #475569; font-size: 1.05rem; margin: 0.15rem 0 1.1rem 0;}
.ff-etapa {font-size: 0.78rem; font-weight: 700; color: #2563eb; text-transform: uppercase;
           letter-spacing: 0.06em; margin-bottom: 0.1rem;}
.ff-ok {color: #15803d; font-weight: 600;}
.ff-falha {color: #b91c1c; font-weight: 600;}
.ff-medidas {font-size: 0.85rem; color: #475569;}
/* Upload: textos em português */
[data-testid="stFileUploaderDropzoneInstructions"] > div > span,
[data-testid="stFileUploaderDropzoneInstructions"] > div > small {display: none;}
[data-testid="stFileUploaderDropzoneInstructions"] > div::before {
    content: "Arraste e solte um ou mais arquivos aqui"; font-weight: 600; display: block;}
[data-testid="stFileUploaderDropzoneInstructions"] > div::after {
    content: "TXT, DOCX, PDF, PNG, JPG, JPEG ou WEBP — até 50 MB · várias imagens podem ir juntas";
    font-size: 0.85rem; color: #64748b; display: block;}
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p {display: none;}
[data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"]::after {
    content: "Selecionar arquivo(s)";}
[data-testid="stFileUploaderDropzone"] {border: 2px dashed #93c5fd; background: #f1f6ff;}
</style>
""",
    unsafe_allow_html=True,
)

PADROES = {
    "cfg_largura_cm": 7.5,
    "cfg_altura_cm": 14.0,
    "cfg_pos_h": "Centralizada",
    "cfg_pos_v": "Centralizada",
    "cfg_x_mm": (A4_LARGURA_MM - 75.0) / 2,
    "cfg_topo_mm": (A4_ALTURA_MM - 140.0) / 2,
    "cfg_fonte": fontes.fonte_padrao(),
    "cfg_tamanho": 10.0,
    "cfg_espacamento": 1.25,
    "cfg_margem": 3.0,
    "cfg_alinhamento": "esquerda",
    "cfg_tamanho_min": 7.0,
    "cfg_encaixe": "ajustar",
    "cfg_margem_img": 0.0,
    "cfg_por_area": 0,
    "cfg_espaco_img": 2.0,
    "cfg_girar": False,
    "cfg_ref_previa": True,
    "cfg_ref_contorno": False,
    "cfg_ref_marcas": False,
}

ESTADO_INICIAL = {
    "documento": None,
    "id_arquivo": None,
    "texto_editor": "",
    "texto_extraido": "",
    "resultado_ocr": None,
    "ocr_executado": False,
    "erro_ocr": None,
    "pdf_gerado": None,
    "assinatura_gerada": None,
    "relatorio": None,
    "avisos_geracao": [],
    "nome_saida": "formato_facil.pdf",
    "chave_upload": 0,
    "pagina_previa": 1,
}

for chave, valor in {**PADROES, **ESTADO_INICIAL}.items():
    st.session_state.setdefault(chave, valor)
ss = st.session_state


# ---------------------------------------------------------------------------
# Funções auxiliares (com cache: a pré-visualização é atualizada a cada ajuste)
# ---------------------------------------------------------------------------

def _hash(*partes) -> str:
    h = hashlib.sha256()
    for parte in partes:
        h.update(parte if isinstance(parte, bytes) else repr(parte).encode("utf-8"))
    return h.hexdigest()[:16]


@st.cache_data(show_spinner=False, max_entries=64)
def pdf_texto_cache(texto: str, cfg: ConfigTexto, area: Retangulo, guias: OpcoesGuias,
                    titulo: str) -> bytes:
    layout = calcular_layout(texto, cfg, area)
    return gerar_pdf_texto(layout, guias, permitir_varias_paginas=True, titulo=titulo)


@st.cache_data(show_spinner=False, max_entries=16)
def pdf_imagem_cache(dados: bytes, tipo: str, area: Retangulo, modo: str, margem: float,
                     guias: OpcoesGuias, titulo: str) -> tuple[bytes, list[str]]:
    caixa = area.recuar(margem) if margem > 0 else area
    if tipo == "pdf":
        lista = extracao.paginas_como_imagens(dados, caixa.largura_mm, caixa.altura_mm)
    else:
        imagem, _ = imagens.carregar_imagem(dados)
        lista = [imagem]
    return gerar_pdf_imagens(lista, area, modo, margem, guias, titulo)


@st.cache_data(show_spinner=False, max_entries=16)
def pdf_varias_imagens_cache(dados_lista: tuple[bytes, ...], nomes: tuple[str, ...], area: Retangulo,
                             margem: float, espaco: float, por_area: int, girar: bool, encaixe: str,
                             guias: OpcoesGuias, titulo: str):
    lista = [imagens.carregar_imagem(dados)[0] for dados in dados_lista]
    if por_area == 1:  # uma imagem por folha: usa o encaixe escolhido (ajustar ou preencher)
        pdf, avisos = gerar_pdf_imagens(lista, area, encaixe, margem, guias, titulo)
        avisos = [a.replace("Página", "Folha") for a in avisos]
        return pdf, avisos, []
    return gerar_pdf_montagem(lista, area, margem, espaco, por_area, girar, guias, list(nomes), titulo)


OPCOES_POR_AREA = [0, 1, 2, 3, 4, 6, 8, 10, 12]


def rotulo_por_area(n: int) -> str:
    if n == 0:
        return "Todas na mesma área"
    if n == 1:
        return "1 por área (uma por folha)"
    return f"{n} por área"


def mover_imagem(indice: int, deslocamento: int) -> None:
    if ss.documento is not None:
        ss.documento.mover_imagem(indice, deslocamento)


@st.cache_data(show_spinner=False, max_entries=32)
def folha_cache(dados_pdf: bytes, pagina: int, area: Retangulo, margem: float, refs: bool):
    return previa.folha_anotada(dados_pdf, pagina, area, margem, refs)


@st.cache_data(show_spinner=False, max_entries=32)
def ampliada_cache(dados_pdf: bytes, pagina: int, area: Retangulo, refs: bool):
    return previa.area_ampliada(dados_pdf, pagina, area, refs)


@st.cache_data(show_spinner=False, max_entries=8)
def miniaturas_pdf(dados: bytes, limite: int = 4):
    info = extracao.extrair_pdf(dados)
    return [extracao.renderizar_pagina(dados, i, 60) for i in range(min(limite, info.numero_paginas))]


@st.cache_data(show_spinner=False, max_entries=32)
def tamanho_que_cabe_cache(texto, cfg, area, minimo, maximo):
    return maior_tamanho_que_cabe(texto, cfg, area, minimo, maximo)


def limpar_tudo() -> None:
    chave = ss.chave_upload + 1
    for k, v in ESTADO_INICIAL.items():
        ss[k] = v
    ss.chave_upload = chave
    ss.pop("modo_uso", None)
    ss.pop("modo_aparencia", None)
    ss.pop("escolha_excesso", None)


def restaurar_padroes() -> None:
    for k, v in PADROES.items():
        ss[k] = v


def acao_corrigir_quebras() -> None:
    ss.texto_editor = corrigir_quebras_de_linha(ss.texto_editor)


def acao_remover_espacos() -> None:
    ss.texto_editor = remover_espacos_extras(ss.texto_editor)


def acao_restaurar_texto() -> None:
    ss.texto_editor = ss.texto_extraido


def acao_definir_tamanho(tamanho: float) -> None:
    ss.cfg_tamanho = float(tamanho)


def executar_ocr(documento: importacao.Documento, todas: bool = False) -> None:
    try:
        with st.spinner("Reconhecendo o texto com OCR… isso pode levar alguns segundos."):
            resultado = importacao.executar_ocr(documento, todas_as_paginas=todas)
        ss.resultado_ocr = resultado
        ss.texto_extraido = resultado.texto
        ss.texto_editor = resultado.texto
        ss.erro_ocr = None
    except ErroFormatoFacil as exc:
        ss.erro_ocr = exc.mensagem
    ss.ocr_executado = True


def marca(ok: bool) -> str:
    return '<span class="ff-ok">✔</span>' if ok else '<span class="ff-falha">✘</span>'


# ---------------------------------------------------------------------------
# Painel de configurações (barra lateral)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configurações")

    st.subheader("Área de conteúdo")
    c1, c2 = st.columns(2)
    c1.number_input("Largura (cm)", min_value=1.0, max_value=21.0, step=0.1, format="%.2f",
                    key="cfg_largura_cm")
    c2.number_input("Altura (cm)", min_value=1.0, max_value=29.7, step=0.1, format="%.2f",
                    key="cfg_altura_cm")
    st.radio("Posição horizontal", ["Centralizada", "Personalizada"], horizontal=True, key="cfg_pos_h")
    if ss.cfg_pos_h == "Personalizada":
        st.number_input("Distância da borda esquerda (mm)", min_value=0.0, max_value=210.0,
                        step=0.5, key="cfg_x_mm")
    st.radio("Posição vertical", ["Centralizada", "Personalizada"], horizontal=True, key="cfg_pos_v")
    if ss.cfg_pos_v == "Personalizada":
        st.number_input("Distância da borda superior (mm)", min_value=0.0, max_value=297.0,
                        step=0.5, key="cfg_topo_mm")
    st.selectbox("Áreas por folha", ["1 área por folha", "Múltiplas áreas (em breve)"], index=0,
                 disabled=True, help="Opção futura: várias áreas na mesma folha A4.")

    st.subheader("Texto")
    nomes_fontes = list(fontes.fontes_disponiveis())
    if ss.cfg_fonte not in nomes_fontes:
        ss.cfg_fonte = fontes.fonte_padrao()
    st.selectbox("Fonte tipográfica", nomes_fontes, key="cfg_fonte")
    st.number_input("Tamanho da fonte (pt)", min_value=4.0, max_value=72.0, step=0.5,
                    key="cfg_tamanho")
    st.slider("Espaçamento entre linhas", min_value=0.8, max_value=3.0, step=0.05,
              key="cfg_espacamento", help="Múltiplo do tamanho da fonte (1,0 = simples).")
    st.number_input("Margem interna (mm)", min_value=0.0, max_value=30.0, step=0.5,
                    key="cfg_margem", help="Espaço entre a borda da área e o texto.")
    st.radio("Alinhamento", list(ALINHAMENTOS), format_func=ALINHAMENTOS.get, key="cfg_alinhamento")
    st.number_input("Tamanho mínimo ao reduzir a fonte (pt)", min_value=4.0, max_value=72.0,
                    step=0.5, key="cfg_tamanho_min",
                    help="Limite usado quando você escolhe reduzir a fonte para o texto caber.")

    st.subheader("Imagem (modo aparência)")
    st.radio("Encaixe da imagem", list(imagens.MODOS_ENCAIXE), format_func=imagens.MODOS_ENCAIXE.get,
             key="cfg_encaixe")
    st.number_input("Margem ao redor da imagem (mm)", min_value=0.0, max_value=30.0, step=0.5,
                    key="cfg_margem_img")
    st.markdown("**Várias imagens**")
    st.selectbox("Imagens por área", OPCOES_POR_AREA, format_func=rotulo_por_area, key="cfg_por_area",
                 help="Todas juntas na mesma área de 7,5 × 14 cm, ou em grupos (um grupo por folha A4).")
    st.number_input("Espaço entre imagens (mm)", min_value=0.0, max_value=20.0, step=0.5,
                    key="cfg_espaco_img")
    st.checkbox("Girar imagens deitadas para aproveitar melhor o espaço", key="cfg_girar",
                help="Gira 90° as imagens horizontais quando isso as deixa maiores na área vertical.")
    st.caption("Imagens montadas juntas são sempre encaixadas inteiras: sem distorção e sem cortes. "
               "O encaixe “preencher” vale quando há uma imagem por área.")

    st.subheader("Linhas de referência")
    st.checkbox("Mostrar na pré-visualização", key="cfg_ref_previa")
    st.checkbox("Incluir contorno da área no PDF", key="cfg_ref_contorno",
                help="Linha tracejada fina na borda da área (desenhada por dentro dela).")
    st.checkbox("Incluir marcas de corte no PDF", key="cfg_ref_marcas",
                help="Pequenas marcas nos cantos, do lado de fora da área, para recortar.")
    st.button("Restaurar configurações padrão", on_click=restaurar_padroes, width="stretch")

# ---------------------------------------------------------------------------
# Cabeçalho e importação
# ---------------------------------------------------------------------------
st.markdown('<div class="ff-titulo">Formato <span>Fácil</span> PDF</div>'
            '<div class="ff-subtitulo">Transforme qualquer conteúdo em um PDF pronto para imprimir.</div>',
            unsafe_allow_html=True)

col_upload, col_limpar = st.columns([6, 1], vertical_alignment="center")
with col_upload:
    arquivos = st.file_uploader(
        "Arquivos de entrada", type=["txt", "docx", "pdf", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True, key=f"upload_{ss.chave_upload}", label_visibility="collapsed",
    ) or []
with col_limpar:
    st.button("🧹 Limpar", on_click=limpar_tudo, width="stretch",
              help="Remove os arquivos, o texto e o PDF gerado.")

erro_importacao = None
if arquivos:
    entradas = [(a.name, a.getvalue()) for a in arquivos]
    id_arquivo = _hash(*[parte for entrada in entradas for parte in entrada])
    if id_arquivo != ss.id_arquivo:
        for k in ("resultado_ocr", "erro_ocr", "pdf_gerado", "assinatura_gerada", "relatorio"):
            ss[k] = ESTADO_INICIAL[k]
        ss.ocr_executado = False
        ss.pop("modo_uso", None)
        ss.pop("modo_aparencia", None)
        ss.pop("escolha_excesso", None)
        ss.id_arquivo = id_arquivo
        try:
            with st.spinner("Lendo o arquivo…"):
                documento = importacao.importar_varios(entradas)
            ss.documento = documento
            ss.texto_extraido = documento.texto
            ss.texto_editor = documento.texto
            base = Path(entradas[0][0]).stem if len(entradas) == 1 else "imagens"
            ss.nome_saida = base + "_formatado.pdf"
        except ErroFormatoFacil as exc:
            ss.documento = None
            ss.texto_extraido = ""
            ss.texto_editor = ""
            erro_importacao = exc.mensagem
            ss.erro_importacao_salvo = exc.mensagem
    elif ss.documento is None:
        erro_importacao = ss.get("erro_importacao_salvo")

if erro_importacao:
    st.error(f"**Não foi possível usar o(s) arquivo(s).** {erro_importacao}")

documento: importacao.Documento | None = ss.documento

# ---------------------------------------------------------------------------
# Configurações efetivas
# ---------------------------------------------------------------------------
erro_config = None
area = None
try:
    largura_mm = round(ss.cfg_largura_cm * 10, 3)
    altura_mm = round(ss.cfg_altura_cm * 10, 3)
    cfg_area = ConfigArea(
        largura_mm=largura_mm,
        altura_mm=altura_mm,
        centralizar_horizontal=ss.cfg_pos_h == "Centralizada",
        centralizar_vertical=ss.cfg_pos_v == "Centralizada",
        x_mm=ss.cfg_x_mm,
        y_mm=A4_ALTURA_MM - ss.cfg_topo_mm - altura_mm,
    )
    area = calcular_area(cfg_area)
except ErroFormatoFacil as exc:
    erro_config = exc.mensagem

cfg_texto = ConfigTexto(
    fonte=ss.cfg_fonte,
    tamanho_pt=float(ss.cfg_tamanho),
    espacamento=float(ss.cfg_espacamento),
    margem_interna_mm=float(ss.cfg_margem),
    alinhamento=ss.cfg_alinhamento,
)
guias_pdf = OpcoesGuias(contorno=ss.cfg_ref_contorno, marcas_corte=ss.cfg_ref_marcas)

# ---------------------------------------------------------------------------
# Coluna esquerda: conteúdo original, modo e edição
# ---------------------------------------------------------------------------
col_esq, col_dir = st.columns([1.05, 1], gap="large")

modo_imagem = False  # True = Modo B, ajustar a imagem
with col_esq:
    st.markdown('<p class="ff-etapa">1 · Conteúdo original</p>', unsafe_allow_html=True)
    if documento is None:
        st.info("Envie um arquivo acima — ou digite/cole o texto diretamente na caixa de edição abaixo.")
    else:
        with st.expander(f"📎 {documento.nome} — {documento.descricao}", expanded=True):
            if documento.tipo == "imagem":
                st.image(documento.imagem, width="stretch")
                st.caption(f"{documento.imagem.width} × {documento.imagem.height} pixels")
            elif documento.tipo == "imagens":
                st.caption("A ordem abaixo é a ordem de montagem (da esquerda para a direita, de cima "
                           "para baixo). Use ◀ ▶ para reorganizar.")
                total_imgs = len(documento.lista_imagens)
                por_linha = 4
                for inicio in range(0, total_imgs, por_linha):
                    colunas = st.columns(por_linha)
                    for coluna, i in zip(colunas, range(inicio, min(inicio + por_linha, total_imgs))):
                        imagem_i = documento.lista_imagens[i]
                        coluna.image(imagem_i, width="stretch")
                        coluna.caption(f"**{i + 1}** · {documento.nomes_arquivos[i]} · "
                                       f"{imagem_i.width}×{imagem_i.height}")
                        m1, m2 = coluna.columns(2)
                        m1.button("◀", key=f"esq_{i}", on_click=mover_imagem, args=(i, -1),
                                  disabled=i == 0, width="stretch", help="Mover para antes")
                        m2.button("▶", key=f"dir_{i}", on_click=mover_imagem, args=(i, 1),
                                  disabled=i == total_imgs - 1, width="stretch", help="Mover para depois")
            elif documento.tipo == "pdf":
                miniaturas = miniaturas_pdf(documento.dados)
                colunas = st.columns(max(1, len(miniaturas)))
                for i, (coluna, miniatura) in enumerate(zip(colunas, miniaturas), start=1):
                    coluna.image(miniatura, caption=f"Página {i}", width="stretch")
                st.caption(f"{documento.numero_paginas} página(s)")
            else:
                st.text_area("Texto original (somente leitura)", documento.texto or "(vazio)",
                             height=160, disabled=True)
        for aviso in documento.avisos:
            st.warning(aviso)

        if documento.permite_preservar_aparencia:
            st.markdown('<p class="ff-etapa">2 · Modo de tratamento</p>', unsafe_allow_html=True)
            padrao = 1 if documento.tipo in ("imagem", "imagens") or not documento.info_pdf.tem_texto else 0
            modo_uso = st.radio(
                "Como usar este arquivo?",
                ["Modo A — Reformatar o texto", "Modo B — Preservar a aparência original"],
                index=padrao, key="modo_uso",
                help="Modo A extrai o texto e o reorganiza tipograficamente. Modo B mantém o visual.",
            )
            if modo_uso.startswith("Modo B"):
                opcoes_b = ["Ajustar a imagem proporcionalmente na área (sem distorcer)",
                            "Extrair o texto por OCR e reconstruir o documento na área"]
                if documento.tipo == "imagens":
                    opcoes_b[0] = "Dimensionar e encaixar todas as imagens na área (sem distorcer)"
                opcao_b = st.radio("No Modo B:", range(2), format_func=lambda i: opcoes_b[i],
                                   key="modo_aparencia")
                modo_imagem = opcao_b == 0

    if not modo_imagem:
        # Texto vindo de OCR quando necessário
        if documento is not None and documento.tipo in ("imagem", "imagens", "pdf"):
            status = ocr.verificar_ocr()
            precisa_auto = (documento.tipo in ("imagem", "imagens")
                            or (documento.info_pdf is not None and not documento.info_pdf.tem_texto))
            if not status.disponivel:
                if documento.precisa_ocr:
                    st.error("**OCR indisponível.** " + status.mensagem)
            else:
                if not status.tem_portugues:
                    st.warning(status.mensagem)
                if precisa_auto and not ss.ocr_executado:
                    executar_ocr(documento)
                    st.rerun()
                elif documento.tipo == "imagens":
                    if st.button("🔎 Refazer o OCR na ordem atual das imagens",
                                 help="Substitui o texto da caixa de edição pelo OCR de todas as imagens."):
                        executar_ocr(documento)
                        st.rerun()
                elif documento.tipo == "pdf" and documento.precisa_ocr and not precisa_auto:
                    c_ocr, c_todas = st.columns([1, 1])
                    todas = c_todas.checkbox("Refazer OCR em todas as páginas")
                    if c_ocr.button("🔎 Executar OCR nas páginas sem texto", width="stretch"):
                        executar_ocr(documento, todas)
                        st.rerun()
                elif documento.tipo == "pdf" and documento.info_pdf.tem_texto:
                    if st.button("🔎 Ignorar o texto do PDF e usar OCR em todas as páginas"):
                        executar_ocr(documento, True)
                        st.rerun()
            if ss.erro_ocr:
                st.error("**O OCR falhou.** " + ss.erro_ocr)
            resultado_ocr = ss.resultado_ocr
            if resultado_ocr is not None:
                confianca = resultado_ocr.confianca_media
                texto_conf = f"Confiança média do OCR: **{confianca:.0f}%** (idioma: {resultado_ocr.idioma})"
                if resultado_ocr.confianca_baixa:
                    st.warning(texto_conf + " — revise o texto com atenção.")
                else:
                    st.success(texto_conf)
                for aviso in resultado_ocr.avisos:
                    if "confiança baixa" not in aviso:
                        st.warning(aviso)
                if resultado_ocr.palavras_duvidosas:
                    exemplos = ", ".join(f"“{p}”" for p in resultado_ocr.palavras_duvidosas[:25])
                    st.caption(f"Palavras reconhecidas com baixa confiança (confira no texto): {exemplos}")

        st.markdown('<p class="ff-etapa">3 · Revisão e edição do texto</p>', unsafe_allow_html=True)
        st.text_area(
            "Texto que irá para o PDF — corrija, apague ou acrescente o que quiser",
            key="texto_editor", height=340,
            placeholder="Digite ou cole aqui o texto…",
        )
        b1, b2, b3 = st.columns(3)
        b1.button("Corrigir quebras", on_click=acao_corrigir_quebras, width="stretch",
                  help="Junta linhas quebradas no meio dos parágrafos (útil em OCR e PDFs). "
                       "Linhas em branco continuam separando parágrafos.")
        b2.button("Tirar espaços extras", on_click=acao_remover_espacos, width="stretch",
                  help="Reduz espaços repetidos e linhas em branco seguidas.")
        b3.button("Restaurar original", on_click=acao_restaurar_texto, width="stretch",
                  disabled=not ss.texto_extraido)
        texto_atual = ss.texto_editor
        st.caption(f"{contar_palavras(texto_atual)} palavras · {len(texto_atual)} caracteres · "
                   "linhas em branco separam parágrafos")

# ---------------------------------------------------------------------------
# Coluna direita: análise, pré-visualização e geração
# ---------------------------------------------------------------------------
with col_dir:
    st.markdown('<p class="ff-etapa">4 · Pré-visualização do resultado</p>', unsafe_allow_html=True)
    if area is not None:
        st.markdown(
            f'<p class="ff-medidas">Folha A4 {formatar_mm(A4_LARGURA_MM)} × {formatar_mm(A4_ALTURA_MM)} mm · '
            f'área {formatar_mm(area.largura_mm)} × {formatar_mm(area.altura_mm)} mm · '
            f'posição x = {formatar_mm(area.x_mm)} mm, y = {formatar_mm(area.y_mm)} mm '
            f'(a partir do canto inferior esquerdo)</p>', unsafe_allow_html=True)

    pdf_previa: bytes | None = None
    pode_gerar = False
    motivo_bloqueio = None
    permitir_varias = False
    cfg_final = cfg_texto
    avisos_previa: list[str] = []
    titulo_pdf = Path(ss.nome_saida).stem

    if erro_config:
        st.error(erro_config)
        motivo_bloqueio = "Corrija as configurações da área."
    elif modo_imagem and documento.tipo == "imagens":
        try:
            with st.spinner("Dimensionando as imagens…"):
                pdf_previa, avisos_previa, montagens = pdf_varias_imagens_cache(
                    tuple(documento.dados_arquivos), tuple(documento.nomes_arquivos), area,
                    float(ss.cfg_margem_img), float(ss.cfg_espaco_img), int(ss.cfg_por_area),
                    bool(ss.cfg_girar), ss.cfg_encaixe, guias_pdf, titulo_pdf)
            n_imgs = len(documento.lista_imagens)
            if montagens:
                folhas = len(montagens)
                ocupacao = sum(m.ocupacao for m in montagens) / folhas
                giradas = sum(1 for m in montagens for p in m.posicoes if p.girada)
                arranjo = "; ".join(sorted({m.descricao for m in montagens}))
                st.success(
                    f"✔ {n_imgs} imagens dimensionadas em {folhas} área(s)/folha(s) A4 — "
                    f"arranjo em {arranjo}, ocupando em média {ocupacao:.0%} do espaço. "
                    "Nenhuma imagem foi distorcida ou cortada."
                    + (f" {giradas} imagem(ns) girada(s) 90°." if giradas else "")
                )
            else:
                st.success(f"✔ {n_imgs} imagens, uma por folha A4, todas na mesma posição.")
            for aviso in avisos_previa:
                st.warning(aviso)
            pode_gerar = True
        except ErroFormatoFacil as exc:
            st.error(exc.mensagem)
            motivo_bloqueio = exc.mensagem
    elif modo_imagem:
        try:
            with st.spinner("Preparando a imagem…"):
                pdf_previa, avisos_previa = pdf_imagem_cache(
                    documento.dados, documento.tipo, area, ss.cfg_encaixe, float(ss.cfg_margem_img),
                    guias_pdf, titulo_pdf)
            caixa = area.recuar(ss.cfg_margem_img) if ss.cfg_margem_img > 0 else area
            if documento.tipo == "imagem":
                encaixe = imagens.calcular_encaixe(documento.imagem.width, documento.imagem.height,
                                                   caixa, ss.cfg_encaixe)
                explicacao = imagens.explicar_proporcao(encaixe)
                if explicacao:
                    st.info("📐 " + explicacao + " Você pode trocar o encaixe nas configurações.")
            elif ss.cfg_encaixe == "preencher":
                st.info("📐 No modo preencher, as partes das páginas que não couberem na proporção "
                        "da área serão cortadas.")
            for aviso in avisos_previa:
                st.warning(aviso)
            pode_gerar = True
        except ErroFormatoFacil as exc:
            st.error(exc.mensagem)
            motivo_bloqueio = exc.mensagem
    else:
        texto = ss.texto_editor
        if texto_esta_vazio(texto):
            motivo_bloqueio = "Não há texto para gerar o PDF. Importe um arquivo ou digite o conteúdo."
            st.info(motivo_bloqueio)
        else:
            try:
                layout = calcular_layout(texto, cfg_texto, area)
                st.caption(descrever_espaco(layout))
                if layout.caracteres_sem_glifo:
                    lista = " ".join(layout.caracteres_sem_glifo[:30])
                    st.warning(f"A fonte {cfg_texto.fonte} não tem estes caracteres, que sairiam como "
                               f"caixas vazias: {lista}. Experimente outra fonte ou edite o texto.")
                if cfg_texto.tamanho_pt < 7:
                    st.warning("Fontes menores que 7 pt podem ficar difíceis de ler impressas.")

                if layout.cabe_em_uma_area:
                    uso = len(layout.paginas[0]) if layout.paginas else 0
                    st.success(f"✔ O texto cabe na área: usa {uso} de {layout.linhas_por_area} linhas.")
                    pode_gerar = True
                    if layout.ocupacao_ultima_area < 0.6:
                        sugestao = tamanho_que_cabe_cache(texto, cfg_texto, area, cfg_texto.tamanho_pt,
                                                          max(cfg_texto.tamanho_pt, 14.0))
                        if sugestao and sugestao >= cfg_texto.tamanho_pt + 1:
                            c_s1, c_s2 = st.columns([3, 1], vertical_alignment="center")
                            c_s1.caption(f"Sobra espaço na área: com fonte de {formatar_mm(sugestao)} pt o texto "
                                         "continua cabendo em uma área. (As sugestões vão até 14 pt; "
                                         "nada é alterado sem o seu clique.)")
                            c_s2.button(f"Usar {formatar_mm(sugestao)} pt", on_click=acao_definir_tamanho,
                                        args=(sugestao,), width="stretch")
                else:
                    st.warning(
                        f"⚠ **O texto não cabe em uma única área.** São {layout.total_linhas} linhas e "
                        f"cabem {layout.linhas_por_area} por área — seriam necessárias "
                        f"{layout.numero_paginas} folhas. Nenhum trecho será cortado: escolha como resolver."
                    )
                    minimo = float(ss.cfg_tamanho_min)
                    tamanho_ok = (tamanho_que_cabe_cache(texto, cfg_texto, area, minimo, cfg_texto.tamanho_pt)
                                  if minimo < cfg_texto.tamanho_pt else None)
                    opcoes = [
                        f"Distribuir em {layout.numero_paginas} folhas A4 (mesma área em cada folha)",
                        (f"Reduzir a fonte para {formatar_mm(tamanho_ok)} pt (cabe em uma área)"
                         if tamanho_ok else
                         f"Reduzir a fonte (não cabe nem com o mínimo de {formatar_mm(minimo)} pt)"),
                        "Vou editar ou reduzir o texto",
                    ]
                    escolha = st.radio("Como resolver o excesso?", range(3), format_func=lambda i: opcoes[i],
                                       index=None, key="escolha_excesso")
                    if escolha == 0:
                        permitir_varias = True
                        pode_gerar = True
                    elif escolha == 1:
                        if tamanho_ok:
                            cfg_final = replace(cfg_texto, tamanho_pt=tamanho_ok)
                            pode_gerar = True
                            st.caption(f"O PDF usará fonte de {formatar_mm(tamanho_ok)} pt. "
                                       "O tamanho escolhido nas configurações não foi alterado.")
                        else:
                            motivo_bloqueio = ("Nem com a fonte mínima o texto cabe. Diminua o tamanho mínimo, "
                                               "distribua em várias folhas ou edite o texto.")
                            st.error(motivo_bloqueio)
                    elif escolha == 2:
                        motivo_bloqueio = "Edite o texto até que ele caiba na área."
                    else:
                        motivo_bloqueio = "Escolha como resolver o excesso de texto antes de gerar o PDF."
                with st.spinner("Atualizando a pré-visualização…"):
                    pdf_previa = pdf_texto_cache(texto, cfg_final, area, guias_pdf, titulo_pdf)
            except ErroFormatoFacil as exc:
                st.error(exc.mensagem)
                motivo_bloqueio = exc.mensagem

    # --- Imagens da pré-visualização
    if pdf_previa is not None:
        total = previa.contar_paginas(pdf_previa)
        pagina = 1
        if total > 1:
            if ss.pagina_previa > total:
                ss.pagina_previa = total
            pagina = st.slider("Folha", 1, total, key="pagina_previa")
            if motivo_bloqueio:
                st.caption("A pré-visualização mostra todas as folhas, mas o PDF só será gerado "
                           "depois que você escolher como resolver o excesso.")
        margem_previa = float(ss.cfg_margem_img if modo_imagem else ss.cfg_margem)
        aba_folha, aba_area = st.tabs(["Folha A4 inteira", "Área ampliada"])
        with aba_folha:
            st.image(folha_cache(pdf_previa, pagina - 1, area, margem_previa, ss.cfg_ref_previa),
                     width="stretch")
        with aba_area:
            st.image(ampliada_cache(pdf_previa, pagina - 1, area, ss.cfg_ref_previa),
                     width="stretch")
        st.caption("A pré-visualização está em escala de tela e não corresponde ao tamanho impresso. "
                   "O tamanho físico é definido pelo PDF (página A4 e área em milímetros). "
                   "Tracejado azul: área de conteúdo; tracejado laranja: margem interna; cinza: distâncias "
                   "até as bordas da folha. Essas linhas aparecem só aqui, a menos que você as inclua no PDF.")

    # --- Geração
    st.markdown('<p class="ff-etapa">5 · Gerar e baixar</p>', unsafe_allow_html=True)
    if modo_imagem:
        ordem = tuple(documento.nomes_arquivos) + tuple(_hash(d) for d in documento.dados_arquivos)
        assinatura = _hash("img", ss.id_arquivo, ordem, area, ss.cfg_encaixe, ss.cfg_margem_img,
                           ss.cfg_por_area, ss.cfg_espaco_img, ss.cfg_girar, guias_pdf)
    else:
        assinatura = _hash("txt", ss.texto_editor, cfg_final, area, guias_pdf, permitir_varias)

    g1, g2 = st.columns(2)
    gerar = g1.button("📄 Gerar PDF", type="primary", width="stretch", disabled=not pode_gerar)
    if gerar and pode_gerar:
        try:
            with st.spinner("Gerando e verificando o PDF…"):
                if modo_imagem and documento.tipo == "imagens":
                    pdf, avisos, _ = pdf_varias_imagens_cache(
                        tuple(documento.dados_arquivos), tuple(documento.nomes_arquivos), area,
                        float(ss.cfg_margem_img), float(ss.cfg_espaco_img), int(ss.cfg_por_area),
                        bool(ss.cfg_girar), ss.cfg_encaixe, guias_pdf, titulo_pdf)
                elif modo_imagem:
                    pdf, avisos = pdf_imagem_cache(documento.dados, documento.tipo, area, ss.cfg_encaixe,
                                                   float(ss.cfg_margem_img), guias_pdf, titulo_pdf)
                else:
                    layout_final = calcular_layout(ss.texto_editor, cfg_final, area)
                    pdf = gerar_pdf_texto(layout_final, guias_pdf, permitir_varias, titulo_pdf)
                    avisos = []
                relatorio = verificar_pdf(pdf, area, considerar_desenhos=not guias_pdf.marcas_corte)
            ss.pdf_gerado = pdf
            ss.relatorio = relatorio
            ss.assinatura_gerada = assinatura
            ss.avisos_geracao = avisos
        except ErroConteudoExcedente as exc:
            st.error(exc.mensagem)
        except ErroFormatoFacil as exc:
            st.error(exc.mensagem)

    atualizado = ss.pdf_gerado is not None and ss.assinatura_gerada == assinatura
    g2.download_button("⬇️ Baixar PDF", data=ss.pdf_gerado or b"", file_name=ss.nome_saida,
                       mime="application/pdf", width="stretch", disabled=not atualizado)

    if not pode_gerar and motivo_bloqueio:
        st.caption(f"Para gerar o PDF: {motivo_bloqueio}")
    if ss.pdf_gerado is not None and not atualizado:
        st.info("O conteúdo ou as configurações mudaram desde a última geração. Clique em **Gerar PDF** "
                "novamente para baixar a versão atualizada.")
    if atualizado and ss.relatorio is not None:
        rel = ss.relatorio
        if rel.aprovado:
            st.success(f"PDF gerado e verificado: {len(rel.paginas)} folha(s) A4.")
        else:
            st.error("O PDF foi gerado, mas a verificação encontrou problemas: " + " ".join(rel.problemas))
        p1 = rel.paginas[0]
        caixa = p1.caixa_conteudo
        linhas_rel = [
            f"{marca(rel.todas_a4)} Página: {formatar_mm(p1.largura_mm)} × {formatar_mm(p1.altura_mm)} mm "
            f"(A4 retrato) em todas as folhas",
            f"{marca(True)} Área de conteúdo: {formatar_mm(area.largura_mm)} × {formatar_mm(area.altura_mm)} mm "
            f"em x = {formatar_mm(area.x_mm)} mm, y = {formatar_mm(area.y_mm)} mm",
            f"{marca(all(p.dentro_da_area for p in rel.paginas))} Todo o conteúdo dentro da área"
            + (f" (conteúdo medido: {formatar_mm(caixa.largura_mm)} × {formatar_mm(caixa.altura_mm)} mm)"
               if caixa else ""),
            f"{marca(rel.fontes_embutidas)} Fontes incorporadas ao PDF",
        ]
        st.markdown("<br>".join(linhas_rel), unsafe_allow_html=True)
        for aviso in ss.avisos_geracao:
            st.warning(aviso)

# ---------------------------------------------------------------------------
# Instruções de impressão
# ---------------------------------------------------------------------------
st.divider()
with st.expander("🖨️ Como imprimir em tamanho real (100%)", expanded=True):
    st.markdown(
        """
Para que a área saia com **exatamente** as medidas escolhidas no papel:

1. **Papel:** A4 (210 × 297 mm).
2. **Orientação:** retrato.
3. **Escala:** *Tamanho real* ou *100%* — no Adobe Acrobat Reader, em *Tamanho e manuseio de página*, escolha **Tamanho real**; no Edge/Chrome, em *Mais configurações*, escolha **Escala: 100** (ou *Padrão*, nunca *Ajustar*).
4. **Desative** “Ajustar à página”, “Reduzir páginas grandes” ou “Ajustar à área de impressão”.
5. **Desative** redimensionamentos automáticos nas preferências do driver da impressora (por exemplo “Ajustar ao papel” ou “Zoom”).

Dica: na primeira vez, ative *Incluir contorno da área no PDF*, imprima e confira com uma régua: a área deve medir 7,5 cm × 14 cm (ou a medida que você configurou).

**Observação:** a posição física impressa pode variar alguns décimos de milímetro (ou até 1–2 mm) por limitações mecânicas da impressora, como o alinhamento do papel na bandeja. O PDF mantém as dimensões geométricas corretas mesmo quando a impressora não consegue imprimir até as bordas da folha.
"""
    )
st.caption(f"{NOME_APLICATIVO} — os arquivos são processados apenas onde o aplicativo está rodando "
           "(no uso local pelo iniciar.bat, neste computador) e não são enviados a outros serviços.")
