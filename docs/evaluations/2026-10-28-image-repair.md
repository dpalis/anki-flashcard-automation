# Troca de imagem existente — implementação de 28/10/2026

Decisão: a lacuna era a ausência de reparo de imagem exposto pela bridge; a operação agora troca uma referência identificada e oferece recuperação.
Alternativa: duplicar o fluxo de áudio; escolhido extrair sua transação/snapshot para `media_repair.py`, mantendo o contrato V2 de dois cards.
Corte: nenhum gerador, editor geral de HTML, banco de operações ou biblioteca de imagem nova; somente `sips` já presente no macOS.
Aceite local: testes de preservação/conflito/recuperação e captura Chromium da fixture sintética; validação real no Anki continua dependente de autorização de alvo concreto.

## Contrato e provas

- `--image-repair-json`, read/preview com `card_id` ou `note_id`, descobre
  `field` e `old_filename`; uma seleção ambígua retorna candidatos sem token.
- Aplicação exige `apply_request` completo e `confirmed:true`: note explícita,
  campo, imagem anterior, arquivo/hash novos e estado atual da prévia.
- Campos suportados: V2 `Image` (contrato de dois cards preservado) e Basic
  `Front`/`Back`; HTML misto preservado fora do `src` selecionado.
- Arquivo PNG/JPEG até 5 MiB, absoluto sob outputs, sem symlink; hash e decode
  reais. A imagem anterior também deve passar pelo mesmo limite/formato/decode
  antes de uma prévia aplicável ou upload: GIF, arquivo acima de 5 MiB e imagem
  corrompida são recusados antes de alterar a note. Upload usa nome novo limitado
  a 77 bytes; colisão não sobrescreve.
- Releitura independente confere referência, bytes, campos, tags, modelo,
  templates/CSS, cards/decks, agendamento, histórico e mídias já referenciadas.
- `recovery` restaura a imagem anterior preservada, sem novo upload, por prévia
  e confirmação atuais. Uma candidata já referenciada na note é recusada para
  manter a recuperação unívoca; mídia idêntica ainda sem referência na note pode
  ser reutilizada. Nomes locais são codificados como URL antes do escape HTML,
  inclusive na recuperação. Falha depois de possível mutação é incerta, sem retry.
- `rendered_reference_verified` compara a frente/verso do `cardsInfo`; o nome
  evita confundir HTML+decode com aparência. A fixture visual complementa isso.

Não há garantia de transação atômica entre o último snapshot e `updateNoteFields`:
AnkiConnect não oferece compare-and-swap. A operação detecta alterações desde
a prévia, durante upload e na releitura; não revisar/editar a mesma note durante
o reparo. Não houve acesso ou escrita no Anki pessoal nesta implementação.

## Evidência de teste

Caracterização antes das mudanças: 12 testes de áudio e 45 testes da action Anki
passaram. Os testes novos falharam primeiro por ausência das interfaces de imagem;
a jornada partindo somente de card_id falhou primeiro por rejeição do pedido.
Resultado inicial: 140 testes Anki passaram (13,086 s), incluindo os 12 de áudio e
11 de imagem; 52 testes da action da bridge passaram (0,08 s). `git diff --check`
limpo nas duas worktrees. Chromium carregou as três imagens da fixture com
dimensões 4×4, 1024×1024 e 4×4; captura inspecionada com texto/frente preservados.

Comandos (a partir das respectivas worktrees):

```sh
# Anki Automation: suíte completa, inclui Vision nativo do macOS
PYTHONDONTWRITEBYTECODE=1 '/Users/dpalis/Coding/Anki Automation/venv/bin/python' -m unittest discover -s tests -q
# Somente reparos
PYTHONDONTWRITEBYTECODE=1 '/Users/dpalis/Coding/Anki Automation/venv/bin/python' -m unittest discover -s tests -p '*repair.py' -v
# ClaudeClaw: rota e recibos da bridge
PYTHONPATH=data PYTHONDONTWRITEBYTECODE=1 /Users/dpalis/.claudeclaw/venvs/data-py314/bin/python -m pytest data/tests/test_cli_bridge/test_actions_anki.py -q -p no:cacheprovider
# Fixture sintética, somente transporte em memória; diretório de saída gerenciado
PYTHONPATH=.:tests PYTHONDONTWRITEBYTECODE=1 '/Users/dpalis/Coding/Anki Automation/venv/bin/python' tests/render_image_repair_fixture.py --output DIRETORIO_TEMPORARIO
```

As três verificações Vision existentes exigiram execução fora do sandbox
(dentro dele: `Failed to create CVPixelBuffer`). Sem dependências novas.
A integração da bridge deve atualizar manifesto, superfície e política no
ClaudeClaw; o arquivo instalado `main.py` tem WIP anterior e recebe somente o
delta do novo argumento/dispatch, sem substituir o arquivo integralmente.

## Correções encontradas na revisão

A revisão reproduziu dois erros antes de qualquer escrita pessoal: o cálculo
de posição confundia quebras LF com CR/VT/U+2028, e a busca textual de `src`
podia atingir texto dentro de outro atributo. Os testes de regressão falharam
antes das correções. O leitor agora conta linhas como o HTMLParser e consome
cada atributo completo, preservando seu trecho original; um `src` sem aspas
continua recusado. Os 26 testes de imagem e áudio e a suíte completa de 143
testes passaram após as correções (5,349 s na execução completa).

A revisão final confirmou mais cinco achados. Quatro regressões novas reproduziram
a aceitação de originais sem recuperação possível (GIF, tamanho e corrupção), a
referência duplicada à candidata no mesmo campo ou em outro, a recuperação errada
do nome literal `100%25.png` e a ausência de render de `Basic.Front` na fixture.
Antes das correções, houve seis falhas de asserção e um erro nesses cenários.
As correções reutilizam o decoder e a seleção de mídia existentes, codificam o
filename antes de inseri-lo no HTML e fazem a fixture Basic renderizar Front e
Back nos lados correspondentes. O novo teste de Front troca JPEG por PNG e
restaura o JPEG anterior, conferindo pergunta e resposta separadamente.
Os 18 testes de imagem passaram após as correções (9,693 s). A inspeção AST
encontrou 19 funções sem anotações antes; as 23 funções atuais têm parâmetros e
retorno anotados. As correções anteriores do parser foram preservadas.
A suíte completa foi executada uma única vez após esses ajustes: **147 testes
passaram em 14,188 s**, incluindo Vision nativo, com temporários gerenciados.

Recibo da revisão: `/Users/dpalis/.claudeclaw/tmp/run-9_jdi76n/ce-code-review-anki/review.json`
(`status: complete`, `Ready with fixes`). Os cinco achados confirmados foram
aplicados e verificados nas regressões acima; a revisão descreve o estado anterior
às correções. A bridge teve recibo separado em `ce-code-review-bridge/review.json`
no mesmo diretório gerenciado; sua classificação de escrita reversível foi
incluída na seção existente da skill. Nenhum achado confirmado ficou pendente
na preparação; instalação e aceite visual pessoal continuam separados.

## Teste real a autorizar

O catálogo atual não lista o antigo deck QA e o card histórico de teste não foi
encontrado. Não presumir que esse alvo ainda existe. Selecionar um cartão atual
e obter autorização para a troca temporária e restauração nesse alvo concreto;
excluir o card e a imagem de off-putting. Primeiro executar preview somente com
o `card_id` lido, sem escrita. Preparar um PNG/JPEG aprovado sob outputs e apresentar
modelo/campo, imagem anterior/nova e `apply_request`; a autorização deve cobrir
troca e restauração desse alvo específico. Capturar frente/verso no Anki depois
da troca e depois da recuperação, além das releituras automatizadas. Nenhum ID
histórico deste documento autoriza ou identifica sozinho um alvo atual.
