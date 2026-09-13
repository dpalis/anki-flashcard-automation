# QA japonês — 2026-09-04

> Estado atual — 2026-09-13: QA aprovado pelo usuário, incluindo romaji na frente
> e IPA abaixo da classificação. Autorizados revisão final, commit e PR da expansão.
> Os dois áudios, as imagens e o agendamento foram preservados. A aprovação não
> ativa a criação em decks reais. O OCR ainda pode produzir falsos positivos e negativos;
> isso não foi resolvido nem deve ser apresentado como garantia de imagens corretas.
> Custo acumulado estimado: US$ 0,026834. Detalhes da correção ao final.

## Histórico da primeira rodada: reprovado; criação parcial

Escopo autorizado: duas notes novas (quatro cards) no deck descartável
`Anki Automation V2 Japanese QA`, teto de US$ 0,05, uma tentativa por geração.
Nenhum deck real ou dado legado foi alterado. Sem commit, push, PR ou ativação.

| Entrada | Resultado |
| --- | --- |
| Onde fica a estação? | Uma note, dois cards e áudio criados; imagem reprovada na conferência visual posterior. |
| Gostaria de fazer uma reserva. | Texto e imagem gerados; imagem bloqueada pelo OCR antes de áudio, upload e criação da note. |

Primeira note: `1788567928606`; cards `1788567928607` e `1788567928608`.
Frase: `駅はどこですか？`; pronúncia: `えきはどこですか？ — Eki wa doko desu ka?`.
Segunda frase gerada, mas não inserida: `予約をしたいのですが。`.

## Problema encontrado

A imagem da estação contém letreiros japoneses e passou indevidamente pelo OCR.
Uma execução diagnóstica local, sobre a mesma imagem e com a mesma configuração,
retornou `チルしある` com confiança `0.3`; o filtro descarta resultados abaixo de
`0.70`. Reconhecer texto japonês limpo em teste automatizado não assegurou a
detecção de letreiros na imagem gerada. Não foi reduzido o limite sem avaliar
o efeito sobre falsos positivos.

A imagem da reserva contém letras na parede e foi bloqueada com achado `ac/on`.
Não houve nova tentativa paga, contorno do filtro ou correção automática da note.
O áudio funcional e as imagens de diagnóstico foram preservados. O próximo
trabalho é corrigir a lacuna do detector e repetir o QA de imagem com aprovação;
não liberar a expansão como concluída.

## Verificações

- 101 testes automatizados passaram após a correção de transporte descrita abaixo.
- `git diff --check` passou.
- `notesInfo`/`cardsInfo`: uma note nova com exatamente dois cards no deck de QA,
  frase azul e negrito, imagem preservada na resposta dos dois sentidos,
  conteúdo japonês, kana/romanização e referência ao MP3.
- Comparação dos IDs globais antes/depois: apenas a note e os dois cards acima
  foram acrescentados; nenhum ID removido. Não foi feita auditoria dos campos
  de todas as notes antigas; o fluxo executado não escreveu nelas.
- MP3: Gemini Iapetus, 2,08 segundos, 25.965 bytes. Avaliação perceptiva humana
  ainda pendente; duração e integridade técnica não comprovam pronúncia.
- A prévia visual dentro do Anki não foi concluída por falha da captura de tela.
  As duas imagens geradas foram inspecionadas diretamente.

## Transporte

Antes de qualquer chamada paga, o primeiro preflight falhou na leitura
`retrieveMediaFile` com conexão encerrada. Deck e note type de QA já existiam
nesse ponto; nenhuma note/card havia sido criado e o custo era zero.
O servidor AnkiConnect instalado encerra a conexão após a resposta sem anunciar
`Connection: close`. O conector passou a usar uma conexão por operação para
evitar reutilizar essa conexão. Não foram adicionados retries ou recuperação.
O segundo fluxo não repetiu nenhuma geração paga anterior.

## Custo e armazenamento

| Componente | Estimativa de custo |
| --- | ---: |
| Anthropic, duas gerações de texto | US$ 0,013968 |
| Pollinations Flux, duas imagens | US$ 0,004000 |
| Gemini, um áudio | US$ 0,001383 |
| Total | **US$ 0,019351** |

Estimativa, não valor confirmado em fatura. Anthropic/Gemini usam os tokens
retornados pelas APIs. Flux usa a estimativa de US$ 0,002 por imagem do piloto.
Referências consultadas: [Sonnet 4.6](https://platform.claude.com/docs/en/models/sonnet-4-6/overview),
[Gemini TTS](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-tts-preview),
[catálogo Pollinations](https://gen.pollinations.ai/image/models).

Mídia inserida no QA: 340.701 bytes (0,325 MiB), incluindo a imagem reprovada.
Mídia gerada total, contando também a imagem rejeitada antes da inserção:
572.400 bytes (0,546 MiB). Sem WAV persistente.

Evidências locais desta execução:
`/private/tmp/anki-japanese-qa-fixed-YnzRgT/` (`result.json`, `verification.json`,
`cost.json`, `text-1.json`, `text-2.json`, `image-1.jpg`, `image-2.jpg`, `audio-1.mp3`).
O diretório é temporário; este registro preserva o resultado e os identificadores.

## Segunda tentativa — 2026-09-05

Uma nova geração por imagem, sem repetir texto. O teto acumulado continuou em
US$ 0,05. As descrições visuais desta tentativa foram simplificadas manualmente
para cenas isoladas, sem fachadas/placas; isso não alterou os prompts do aplicativo.

### Debug Summary

- **Problema/causa:** `scripts/detect_visible_text.swift` descartava os achados
  abaixo de 0,70; os letreiros reais da primeira imagem tinham confiança 0,3.
- **Correção:** limite reduzido para 0,30. O teste nativo com a própria imagem
  falhou antes e passou depois. Foi acrescentado um controle negativo sem texto.
  A fixture é `tests/fixtures/japanese-station-signs.jpg`; testes no arquivo
  existente `tests/test_media_and_providers.py`.
- **Limite da correção:** preserva o achado japonês conhecido, mas não garante
  ausência de falsos positivos/negativos. A nova imagem da estação não apresenta
  escrita na inspeção visual; o OCR confundiu dois faróis com `00`, confiança 1,0.
  Esse achado também seria bloqueado pelo limite anterior de 0,70. A imagem não
  foi importada, e não houve contorno do filtro nem outra geração paga.
- **Confiança:** alta para a regressão reproduzida; insuficiente para aprovar o
  fluxo japonês completo. O falso positivo dos faróis permanece pendente.

### Resultado no Anki

- Reserva: `予約をしたいのですが。`, note `1788579229303`, cards
  `1788579229304` e `1788579229305`; ambos no deck descartável de QA.
- Texto reutilizado. Imagem nova passou no OCR e na inspeção direta; áudio novo
  Gemini/Iapetus, 2,24 s, 27.981 bytes. Avaliação perceptiva humana pendente.
- Imagem: 94.762 bytes; mídia nova total: 122.743 bytes (0,117 MiB).
- As mídias recuperadas do Anki conferem com os arquivos locais por SHA-256.
  Os dois cards mantêm a imagem na resposta e referência ao áudio.
- Todos os campos da note anterior da estação permaneceram idênticos. O áudio
  anterior foi preservado. Apenas uma note/dois cards foram acrescentados,
  sem IDs removidos; nenhum deck real foi modificado.

### Custo acumulado

Rodada anterior: US$ 0,019351. Novas imagens: US$ 0,004. Novo áudio: US$ 0,001483.
**Total estimado: US$ 0,024834**. O catálogo Flux foi reconfirmado antes das chamadas;
uso Gemini retornado: 43 tokens de entrada e 72 de áudio. Estimativa, não fatura.
Mídia referenciada pelas duas notes de QA: 463.444 bytes (0,442 MiB), incluindo a
imagem antiga reprovada da estação. Sem WAV persistente.

### Post-Fix Quality

- **Escopo:** ajuste do filtro, fixture, dois testes e este relatório; o restante
  do trabalho de expansão preexistente foi preservado.
- **Simplificação:** não executada; correção de uma condição, sem abstrações.
- **Revisão:** manual e restrita ao ajuste, pois a branch já continha outras edições.
- **Verificação:** 103 testes passaram; `git diff --check` passou; leitura real de
  notes/cards e comparação das mídias. Sem nova prévia gráfica nesta rodada.
- **Pendência:** tratar o falso positivo nos faróis antes de considerar o QA
  completo. Nada foi registrado em tracker externo, commit, push ou PR.

Evidências temporárias desta rodada:
`/private/tmp/anki-japanese-retry-20260905-OZFgi4/` (`image-results.json`,
`result.json`, `verification.json`, `cost.json`, `prompts.json`, duas imagens e
`audio-2.mp3`). O script temporário reutilizou as saídas anteriores; não acrescentou
retry, cache de recuperação ou modo de reparo ao aplicativo.

## Preferência de escrita — romaji, 2026-09-05

O usuário não quer aprender a escrita japonesa. O perfil agora exibe a frase e
os exemplos em romaji Hepburn, com explicações/traduções em português. A escrita
japonesa permanece somente em `phrase_ja`, usada internamente para gerar áudio;
não é renderizada nos cards. Nenhum serviço ou camada nova foi acrescentado.

Os mesmos quatro cards de QA foram preservados. Alterados apenas `Target` e
`ContentHtml` das notes `1788567928606` e `1788579229303`:

- `Eki wa doko desu ka?`
- `Yoyaku o shitai no desu ga.`

Áudios, referências às imagens, IDs e dados de agendamento conferidos como
inalterados. Custo adicional zero; acumulado continua em US$ 0,024834. A imagem
antiga da estação ainda contém letreiros e continua pendente; esta mudança foi
somente dos textos, não uma aprovação dessa imagem ou do QA completo.

103 testes passaram após atualizar schema, validação, prompt e formatação.
As expectativas novas falharam antes da implementação. Cobertura inclui romaji
com mácrons, rejeição de escrita japonesa nos campos visíveis e preservação do
texto japonês enviado ao áudio. Inglês e espanhol mantiveram os testes verdes.
Verificação real por `notesInfo`/`cardsInfo`, sem nova prévia gráfica. Evidências:
`/private/tmp/anki-japanese-romaji-GjbHI9/` (`before.json`, `updates.json`,
`content.json`, `after.json`).

Revisão manual restrita às mudanças de romaji. A revisão formal da branch e o
fechamento permanecem adiados durante o gate de QA; nenhum commit, push ou PR.

## Correção da imagem da estação — 2026-09-05

### Debug Summary

- **Problema:** os letreiros da imagem antiga não seguem o modelo aprovado; a
  substituta sem escrita foi bloqueada pelo OCR, que confundiu faróis com `00`.
- **Causa:** o Vision retorna `00` com confiança 1,0 tanto no helper atual como no
  helper de `HEAD`. Portanto, reduzir anteriormente o limiar para detectar os
  letreiros japoneses não causou esse falso positivo. O adapter tratava qualquer
  achado como prova de escrita legível (`modules/image_provider.py:121–127`).
- **Alternativas testadas e rejeitadas:** exigir sobreposição com regiões de texto
  do Vision liberaria os faróis, mas também liberaria letreiros reais e controles
  impressos `00`, `23` e `駅`. O modo rápido perdeu escrita real; redimensionar a
  imagem produziu outras leituras espúrias. Não foi acrescentada nenhuma dessas
  heurísticas, nem exceção para números, faróis ou uma imagem específica.
- **Correção aplicada:** a mensagem agora informa possível texto e possível falso
  positivo, mantendo o bloqueio e a ausência de retry. Um teste novo reproduziu a
  falsa certeza antes da alteração e passou depois. O algoritmo de OCR não mudou
  nesta rodada; a limitação permanece explícita, não foi corrigida.
- **Imagem de QA:** uma única nova geração Pollinations/Flux, com cena simplificada
  de orientação na estação, trem lateral e superfícies sem escrita. Passou pelo
  mesmo OCR do app e pela inspeção do arquivo. O prompt desta correção foi manual;
  não é evidência de melhoria na geração automática de prompts para itens futuros.
- **Confiança:** alta para a mensagem corrigida e a substituição verificada nesta
  amostra; nenhuma garantia de ausência de falsos positivos/negativos futuros.

### Alteração e verificação no Anki

- Somente o campo `Image` da note `1788567928606` foi alterado. A imagem nova usa
  `aa2_4ee255d9bdbc1aacbda3fdbfaf5fe99cccf114073c04b8a9999e7a42a69b0ea4_image.jpg`.
  Ela foi armazenada com nome novo; a mídia anterior não foi sobrescrita ou apagada.
- Exatamente os mesmos quatro cards continuam no deck `Anki Automation V2 Japanese QA`:
  `1788567928607`, `1788567928608`, `1788579229304`, `1788579229305`.
- Textos em romaji, demais campos, tags, IDs, parâmetros de agendamento, imagem da
  reserva e ambos os áudios foram conferidos como inalterados. SHA-256 das mídias
  originais preservado; bytes da imagem importada idênticos aos do arquivo validado.
- `cardsInfo` confirma imagem na resposta dos dois sentidos, frase azul/negrito e
  referência ao áudio. Nenhum card/note criado ou removido; nenhum deck real alterado.
- Anki foi aberto somente para esta validação por AnkiConnect. A exclusão do Anki
  da observação do Histórico do computador foi reconfirmada; não foi usada inspeção
  de interface por acessibilidade. A conferência visual no app fica com o usuário.

### Custo e armazenamento

Uma chamada Flux: 0,002 Pollen, estimados como US$ 0,002 pela mesma base das rodadas
anteriores; catálogo conferido antes da chamada. Sem chamadas de texto ou áudio.
Acumulado estimado: **US$ 0,026834**, abaixo do teto de US$ 0,05; não é fatura.
Imagem nova: 122.512 bytes. Mídia atualmente referenciada pelos quatro cards:
271.220 bytes (0,259 MiB), dos quais 53.946 bytes são os MP3 preservados.
A imagem antiga não referenciada permanece armazenada; nenhuma limpeza foi feita.

### Post-Fix Quality

- **Escopo:** mensagem do adapter, um teste novo, uma expectativa ajustada e este
  registro. As edições anteriores da expansão foram preservadas.
- **Simplificação:** dispensada; alteração de mensagem sem abstração nova e com
  testes no arquivo que já continha trabalho anterior.
- **Revisão:** manual e independente, restrita aos novos trechos; nenhum achado
  acionável. A revisão formal da expansão inteira permanece no próximo gate.
- **Verificações:** 104 testes passaram, incluindo OCR nativo; `git diff --check`
  passou. Verificação real de notes, cards e mídias concluída sem inspeção da UI.
- **Pendência:** avaliação humana dos quatro cards e aceite explícito do limite
  conhecido do OCR antes do fechamento. Sem commit, push, PR ou ticket externo.

## IPA no mesmo lugar do inglês — 2026-09-12

O usuário pediu a escrita fonética, mantendo romaji na frente. A geração japonesa
agora separa `romaji` (frente), `ipa` (linha abaixo da classificação) e `phrase_ja`
(somente entrada do áudio). Os seis campos do Anki, templates e CSS não mudaram.
Não há migração nem alteração automática de notes existentes no aplicativo.

Somente a última linha de `ContentHtml` das duas notes descartáveis foi corrigida:

- `1788567928606`: `Eki wa doko desu ka?` → `/eki wa doko desɯ ka/`.
- `1788579229303`: `Yoyaku o shitai no desu ga.` → `/jojakɯ o ɕitai no desɯ ɡa/`.

São transcrições amplas para estudo, elaboradas para estas frases, não citações
nem transcrições acústicas dos MP3. Omitem acento tonal e detalhes de ensurdecimento;
as barras mantêm a apresentação dos cards de inglês. Referência fonética:
[Hiki, Kakita e Okada, ICPhS 2011](https://www.internationalphoneticassociation.org/icphs-proceedings/ICPhS2011/OnlineProceedings/RegularSession/Hiki/Hiki.pdf).

Verificação por AnkiConnect: mesmos quatro IDs, mesmas frentes, respostas alteradas
somente na linha IPA, ordem classificação → IPA → áudio, imagem mantida nos dois
sentidos. Demais campos, tags e parâmetros de agendamento inalterados; SHA-256 dos
dois MP3 e das duas imagens idênticos antes/depois. Nenhum deck real alterado.
Sem uso de acessibilidade/captura da interface do Anki e sem sincronização acionada.

106 testes passaram, incluindo validação de romaji/IPA separados, IPA ausente
barrado antes de gerar mídia, ordem no HTML e áudio ainda alimentado por japonês.
Os testes focados falharam no contrato antigo antes da implementação. Revisão
independente local deste ajuste sem achados; revisão formal/publicação da expansão
inteira permanece fora deste gate de QA. `git diff --check` passou.

Custo adicional: **US$ 0**; nenhuma chamada paga ou nova mídia. Armazenamento de
mídia permanece em 271.220 bytes. Evidências temporárias:
`/private/tmp/anki-japanese-ipa-DnL5ha/{before,after,verification}.json`.
Sem commit, push, PR ou ativação em decks reais; aguardando conferência humana.

Evidências: `/private/tmp/anki-headlights-fix-XrQTG4/` (`prompt.txt`, `station.jpg`,
`generation-result.json`, `cost.json`, `apply-before.json`, `after.json`,
`verification.json` e experimentos locais). A imagem definitiva também permanece
na mídia da coleção Anki, sob o nome registrado acima.

## Fechamento do QA e revisão final — 2026-09-13

O usuário aprovou a apresentação final e autorizou revisão, commit e PR. Os
registros anteriores descrevem gates já concluídos; não há ativação em decks reais.

- Revisão da expansão inteira: lógica, testes, manutenção, regras do projeto,
  segurança, transporte, helper Swift e entrada agêntica. Revisão independente
  via Claude Code encontrou uma rejeição indevida de `ª` e `º` em explicações
  portuguesas do perfil japonês. O defeito foi reproduzido e corrigido, mantendo
  a rejeição de escrita japonesa nos campos visíveis.
- A checagem de simplicidade resultou apenas em tipagem mais precisa. Divisões
  cosméticas de arquivos de teste foram descartadas pelo recorte Pareto.
- **108 testes passaram**, incluindo OCR nativo, ordinais portugueses e uso do
  transporte padrão sem sessão persistente. O teste dos ordinais falhou antes
  da correção. `git diff --check` passou.
- O OCR continua sujeito a falsos positivos e negativos. A taxa de erro não foi
  medida em um conjunto representativo de imagens inglesas e espanholas; os
  testes não garantem qualidade linguística ou equivalência entre texto e áudio.
- Nenhuma chamada de geração, abertura do Anki, criação/alteração de note, mídia
  ou agendamento neste fechamento. Custo adicional de geração: **US$ 0**;
  armazenamento das mídias aprovadas permanece em **271.220 bytes**.

Revisão e evidências locais: run `20260913-172908-857c975f` em
`/tmp/compound-engineering-501/ce-code-review/`. Merge e uso em decks reais não
fazem parte desta autorização.
