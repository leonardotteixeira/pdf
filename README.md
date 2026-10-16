# Formato Fácil PDF

**Transforme qualquer conteúdo em um PDF pronto para imprimir.**

O Formato Fácil PDF recebe textos, documentos do Word, PDFs, imagens e capturas de tela e gera um PDF
em **folha A4 (210 × 297 mm)** com todo o conteúdo dentro de uma área de **exatamente 7,5 × 14 cm**,
centralizada na folha. Tudo roda no seu computador — nenhum arquivo é enviado para a internet.

---

## 1. Instalação (Windows)

Pré-requisito: **Python 3.11 ou 3.12** (se não tiver: `winget install Python.Python.3.12`).

1. Dê dois cliques em **`instalar.bat`**. Ele:
   - cria um ambiente Python isolado na pasta `.venv`;
   - instala as dependências de `requirements.txt`;
   - oferece instalar o **Tesseract OCR** (reconhecimento de texto em imagens) via `winget`;
   - baixa o idioma **português** do OCR para a pasta `tessdata` do aplicativo.
2. Pronto. A instalação só precisa ser feita uma vez.

> Sem o Tesseract o aplicativo funciona normalmente com TXT, DOCX e PDFs com texto; apenas a extração de
> texto de imagens e PDFs digitalizados fica indisponível (o aplicativo avisa).

Instalação manual, se preferir o terminal:

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
winget install UB-Mannheim.TesseractOCR
```

## 2. Como usar

1. Dê dois cliques em **`iniciar.bat`**. O navegador abre sozinho com o aplicativo
   (endereço `http://localhost:8501`, acessível apenas neste computador).
   Mantenha a janela preta aberta enquanto usa; feche-a para encerrar.
2. **Arraste e solte** o arquivo (ou várias imagens) na área indicada ou clique em **Selecionar arquivo(s)**.
   Formatos aceitos: TXT, DOCX, PDF, PNG, JPG, JPEG e WEBP (até 50 MB).
   Também é possível apenas digitar ou colar o texto.
3. Escolha o **modo de tratamento** (para imagens e PDFs):
   - **Modo A — Reformatar o texto:** o texto é extraído (diretamente do arquivo ou por OCR) e
     reorganizado tipograficamente na área. O texto fica selecionável e pesquisável no PDF.
   - **Modo B — Preservar a aparência original:**
     - *Ajustar a imagem proporcionalmente* — a imagem (ou cada página do PDF) é encaixada na área sem
       distorção. Nas configurações, escolha **Ajustar** (sem cortes; pode sobrar espaço em branco) ou
       **Preencher** (sem espaço em branco; corta as sobras). O aplicativo explica quanto sobra ou é cortado.
     - *Extrair o texto por OCR e reconstruir* — o mesmo que o Modo A, a partir do OCR.
   - **Várias imagens de uma vez:** selecione ou arraste várias imagens juntas (até 40). No Modo B,
     *Dimensionar e encaixar todas as imagens na área* monta todas dentro dos 7,5 × 14 cm:
     - as imagens são organizadas automaticamente em linhas ou colunas, testando todos os arranjos
       possíveis (até 12 imagens; acima disso, arranjos equilibrados) e escolhendo aquele em que a
       **menor imagem fica a maior possível** — assim nenhuma fica minúscula ao lado de outra enorme;
       entre arranjos equivalentes, vence o que aproveita mais a área;
     - **nenhuma imagem é distorcida nem cortada** (mesma escala na largura e na altura);
     - a ordem é a da lista de miniaturas (use ◀ ▶ para reorganizar);
     - nas configurações (*Várias imagens*): **Imagens por área** (todas juntas, 1 por folha, ou grupos
       de 2, 3, 4… — cada grupo em uma folha A4, sempre na mesma posição), **Espaço entre imagens** (mm)
       e **Girar imagens deitadas** (gira 90° quando isso deixa as imagens maiores);
     - o aplicativo avisa se alguma imagem ficar pequena demais (menos de 15 mm) ou com resolução baixa.
     No Modo A ou no Modo B com OCR, o texto de todas as imagens é reconhecido e unido na ordem atual.
4. **Revise o texto** na caixa de edição: corrija erros de OCR, apague ou acrescente trechos.
   Linhas em branco separam parágrafos. Botões úteis:
   - *Corrigir quebras* — junta linhas quebradas no meio dos parágrafos (comum em OCR e PDFs);
   - *Tirar espaços extras* — remove espaços repetidos e linhas em branco seguidas;
   - *Restaurar original* — volta ao texto extraído.
   Quando o OCR tem baixa confiança, o aplicativo avisa e lista as palavras duvidosas.
   **Nada é inventado ou corrigido automaticamente.**
5. Ajuste o layout na barra lateral (**Configurações**): dimensões e posição da área, fonte, tamanho,
   espaçamento entre linhas, margem interna, alinhamento (à esquerda — padrão —, justificado ou
   centralizado) e linhas de referência. A pré-visualização é atualizada a cada mudança.
6. Se o texto **não couber** em uma área, o aplicativo avisa antes de gerar e pede que você escolha:
   - distribuir em várias folhas A4 (a mesma área, na mesma posição, em cada folha);
   - reduzir a fonte até o tamanho mínimo configurado (o tamanho que cabe é calculado e mostrado);
   - editar ou reduzir o texto.
   **Nenhum trecho é eliminado silenciosamente.**
7. Clique em **Gerar PDF**. O aplicativo gera o arquivo e o **verifica lendo o próprio PDF**: tamanho
   da página, posição e medidas da área, conteúdo dentro da área e fontes incorporadas.
8. Clique em **Baixar PDF**. Se você mudar algo depois de gerar, o botão de baixar é bloqueado até
   gerar novamente — assim nunca se baixa uma versão desatualizada.
9. **Limpar** remove o arquivo, o texto e o PDF gerado para começar de novo.

## 3. Hospedagem gratuita (Streamlit Community Cloud)

O código está no GitHub e pode ser publicado de graça no Streamlit Community Cloud:

1. Acesse <https://share.streamlit.io> e entre com a conta do GitHub.
2. Clique em **Create app** → **Deploy a public app from GitHub**.
3. Escolha o repositório `leonardotteixeira/pdf`, branch `main`, arquivo principal **`app.py`**.
4. Em *Advanced settings*, escolha Python **3.12**.
5. Clique em **Deploy**. A primeira publicação leva alguns minutos.

O arquivo `packages.txt` faz o servidor instalar o Tesseract com o idioma português e as fontes livres
Liberation (com as mesmas medidas de Arial e Times New Roman) e DejaVu. As medidas do PDF são as
mesmas em qualquer lugar.

Atenção: no app hospedado, os arquivos enviados são processados no servidor da plataforma. Para
documentos sensíveis, restrinja o acesso (nas configurações do app, em *Sharing*, escolha
quem pode ver) ou use a versão local pelo `iniciar.bat`.

## 4. Como imprimir em tamanho real (100%)

Para que a área saia com exatamente 7,5 × 14 cm no papel:

- **Papel:** A4.
- **Orientação:** retrato.
- **Escala:** *Tamanho real* ou *100%*.
  - Adobe Acrobat Reader: em *Tamanho e manuseio de página*, escolha **Tamanho real**.
  - Microsoft Edge / Google Chrome: em *Mais configurações*, **Escala: 100** (ou *Padrão*).
- **Desative “Ajustar à página”**, “Reduzir páginas grandes” ou “Ajustar à área de impressão”.
- **Desative redimensionamentos automáticos do driver da impressora** (opções como “Ajustar ao papel”
  ou “Zoom”, nas preferências da impressora).

O PDF também informa aos leitores de PDF que ele deve ser impresso sem escala (`PrintScaling = None`),
o que faz o Acrobat Reader já sugerir *Tamanho real*.

Dica: na primeira impressão, ative **Incluir contorno da área no PDF** (ou as **marcas de corte**) e
confira com uma régua.

**Observação:** a posição física impressa pode sofrer pequenas variações (normalmente décimos de
milímetro, às vezes 1–2 mm) por limitações mecânicas da impressora, como o alinhamento do papel na
bandeja. O PDF mantém as dimensões geométricas corretas mesmo quando a impressora não consegue
imprimir até as bordas da folha.

## 5. Geometria do PDF

Medidas com origem no **canto inferior esquerdo** da página (padrão do PDF):

| Item                      | Valor        |
|---------------------------|--------------|
| Largura da página         | 210 mm       |
| Altura da página          | 297 mm       |
| X inicial da área         | 67,5 mm      |
| Y inicial da área         | 78,5 mm      |
| Largura da área           | 75 mm        |
| Altura da área            | 140 mm       |

- O PDF é gerado com **ReportLab** usando milímetros convertidos em pontos PDF (1 mm = 72 / 25,4 pt).
  Não há pixels CSS nem transformações de escala envolvidas.
- A página nunca tem o tamanho da área: é sempre A4 retrato. Em PDFs com várias folhas, todas são A4
  com a área na mesma posição.
- As dimensões e a posição podem ser alteradas nas configurações, mas **nunca** são alteradas
  automaticamente durante a geração.
- Fontes TrueType são **incorporadas** ao PDF (acentos corretos em qualquer computador).
- A altura das linhas usa as métricas que cobrem todos os glifos da fonte (inclusive maiúsculas
  acentuadas como Á, Ã, Ê), garantindo que nenhuma letra ultrapasse a área.
- Linhas de referência (contorno e cotas) aparecem só na pré-visualização, a menos que você ative
  *Incluir contorno da área no PDF* (desenhado por dentro da área) ou *Incluir marcas de corte no PDF*
  (pequenas marcas nos cantos, do lado de fora da área, para recorte).

## 6. Testes automatizados

```bash
.venv\Scripts\python.exe -m pytest
```

Os testes medem o **PDF gerado** (com PyMuPDF), e não apenas as configurações internas. Eles verificam:

1. dimensões A4 exatas (210 × 297 mm, retrato, sem escala ou caixa de recorte);
2. área de conteúdo de 75 × 140 mm (medida pela imagem que preenche a área e pelo texto justificado);
3. área centralizada (x = 67,5 mm, y = 78,5 mm) e posições personalizadas;
4. conteúdo dentro dos limites — para todas as fontes e alinhamentos, inclusive rasterizando o PDF e
   conferindo que não há nenhum pixel de tinta fora da área;
5. acentos do português preservados no texto extraído do PDF, fontes incorporadas e texto pesquisável;
6. arquivos e textos vazios tratados com mensagens claras;
7. textos longos detectados antes da geração, sem perda de nenhuma palavra ao distribuir em folhas;
8. imagens de várias proporções encaixadas sem distorção (ajustar e preencher);
9. arquivos inválidos, renomeados, corrompidos ou protegidos por senha com mensagens de erro;
10. PDFs de várias páginas tratados em ordem e com a mesma posição em todas as folhas;
11. várias imagens na mesma área: dentro dos limites, sem sobreposição, sem distorção, na ordem
    escolhida, com o espaço configurado entre elas, em grupos por folha e com giro opcional;

além de OCR em português (quando o Tesseract está instalado), leitura de DOCX com tabelas,
codificações de TXT (UTF-8, UTF-16, Windows-1252) e a pré-visualização.

## 7. Estrutura do projeto

```
app.py                      Interface (Streamlit, executada localmente)
iniciar.bat / iniciar.py    Inicia o aplicativo e abre o navegador
instalar.bat                Instalação em um clique
requirements.txt            Dependências Python
.streamlit/config.toml      Configuração do Streamlit (sem estatísticas de uso)
packages.txt                Pacotes do sistema para a hospedagem (Tesseract, fontes livres)
tessdata/                   Idiomas do OCR (português)
formato_facil/
    importacao.py           Importação e validação dos arquivos; orquestra o OCR
    extracao.py             Extração de texto de TXT, DOCX e PDF; renderização de páginas
    ocr.py                  OCR com Tesseract (português), confiança e palavras duvidosas
    imagens.py              Carregamento de imagens e encaixe sem distorção
    montagem.py             Várias imagens na mesma área (arranjo em linhas/colunas)
    formatacao.py           Limpeza do texto, quebra de linhas e paginação
    geometria.py            Unidades físicas e cálculo da área na folha A4
    fontes.py               Fontes TrueType incorporadas e suas métricas
    pdf_gerador.py          Geração do PDF com ReportLab
    validacao.py            Verificação do PDF gerado (medidas reais do arquivo)
    previa.py               Pré-visualização com cotas
    erros.py                Erros com mensagens em português
tests/                      Testes automatizados (pytest)
```

## 8. Solução de problemas

| Problema | Solução |
|----------|---------|
| “OCR indisponível” | Instale o Tesseract: `winget install UB-Mannheim.TesseractOCR` e reinicie o aplicativo. |
| “OCR disponível apenas parcialmente” | Falta o idioma português: execute `instalar.bat` novamente (ele baixa `tessdata\por.traineddata`). |
| Arquivo `.doc` antigo não abre | Abra no Word e salve como `.docx`. |
| PDF protegido por senha | Remova a senha (por exemplo, imprimindo para PDF) e envie novamente. |
| Caracteres saem como caixas | A fonte escolhida não tem esses símbolos (o aplicativo avisa quais). Troque de fonte. |
| A área impressa saiu menor | A impressão não estava em 100%: veja a seção 3. |
| O navegador não abriu | Acesse `http://localhost:8501` manualmente. |
