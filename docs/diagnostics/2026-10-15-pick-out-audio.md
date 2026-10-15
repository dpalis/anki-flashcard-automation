# Falha de áudio de “to Pick out” — 15 de outubro de 2026

A instrução enviada ao Gemini causava uma rejeição reproduzível para “to Pick out”.
Acrescentar `Generate speech.` ao início do prompt resolveu a geração mantendo
transcrição, modelo, voz, locale, revisão da API e demais parâmetros. Uma note com
dois cards foi criada e verificada; as outras 19 notes e seus cards permaneceram
iguais. [Evidências sanitizadas](2026-10-15-pick-out-audio.json).

## Evidência e limite da conclusão

As duas falhas originais foram informadas às 15h10 e 15h31 BRT. Os registros
recuperados contêm `audio_provider`, HTTP 400, `created: []` e
`outcome_uncertain: false`. O código descartava o corpo HTTP; não é possível
recuperar retrospectivamente o detalhe dessas duas respostas. Os timestamps
`source_observed_at` na evidência marcam a captura do registro, não a chamada original.

Na reprodução isolada, o corpo completo foi:

```json
{"error":{"message":"Request contains an invalid argument.","code":"invalid_request"}}
```

| Ensaio controlado | Alteração em relação ao pedido original | Resultado |
| --- | --- | --- |
| “to Pick out”, instrução original | Nenhuma | HTTP 400, `invalid_request` |
| Controle “to Wear off” | Somente a transcrição | HTTP 200 |
| “to Pick out”, instrução explícita | Prefixo `Generate speech.` | HTTP 200, MP3 válido |
| Confirmação da instrução original | Nenhuma | HTTP 400, mesmo corpo |
| Criação com o código corrigido | Prefixo `Generate speech.` | Note e dois cards verificados |

O controle elimina credencial, modelo indisponível e incompatibilidade geral do
payload como explicações para estes ensaios. A sequência antigo → corrigido → antigo
localiza o gatilho na formulação do prompt em conjunto com a transcrição. A resposta
não identifica o campo ou a validação interna do Google: atribuir a falha a um
classificador de síntese ou segurança seria uma hipótese, não uma conclusão.

## Cadeia causal e correção

`main.py:265` usa o campo `term` como transcrição. `GeminiAudioProvider.generate`
monta o pedido em `modules/audio_provider.py`; `_prompt` instruía apenas a leitura
do transcript. Esse pedido recebeu 400 antes de devolver áudio. `raise_for_status`
transformava a resposta em `HTTPError`; o tratamento guardava apenas `str(exc)`,
perdendo o corpo. `process_item` encerrava em `audio_provider` antes de subir mídia
ou executar `addNote`, explicando a ausência da note.

A correção explicita a geração de fala no prompt de todos os perfis e mantém o texto
estudado intacto. O tratamento de `HTTPError` agora inclui a resposta com a chave
ocultada antes de limitar o detalhe a 4.096 caracteres; detalhes maiores recebem
`[truncated]`. A exceção original não aparece em tracebacks públicos. Não foram
introduzidos retries, fallback, regra específica para “Pick out” ou mudança de modelo.

Os testes anteriores cobriam timeout e redaction, mas não a resposta HTTP com corpo.
A cobertura foi ampliada no arquivo existente para erro 400, resposta não JSON,
redaction antes do corte, chamada única e instrução explícita de fala. Testes com
respostas simuladas não demonstram aceitação pelo Google; essa parte foi validada
pelos ensaios reais acima. A API externa continua podendo rejeitar outros pedidos.

## Validação da criação e deduplicação

- Note criada: `1792092624561`.
- Cards: `1792092624561` e `1792092624562`, no deck `English Words & Expressions`.
- Áudio recuperado do Anki: 20.205 bytes, MP3, 1,6 s, mono, 24 kHz, 96 kb/s.
- Imagem recuperada do Anki: 365.185 bytes; hashes dos dois arquivos na evidência.
- O fluxo relê todos os campos da nova note e os dois cards depois de `addNote`.
- Comparação antes/depois: as 19 notes existentes, campos, tags, IDs e cards
  permaneceram iguais; excluído somente `nextReviews`, projeção temporal do Anki.
- Total de notes V2 inglesas criadas hoje: 19 → 20, com exatamente o novo ID.
- Nova passagem pelas 19 entradas, “to Pick out” e o alias “Pick out”: 21
  `skipped_v2`, zero criações e zero chamadas aos provedores. A verificação usou
  provedores que falhariam se fossem chamados.
- Suíte completa: 129 testes passaram. Os três testes macOS Vision exigiram
  execução fora do sandbox; os testes de áudio passaram também dentro dele.

A checagem acima confirma persistência, formato e deduplicação; não é uma avaliação
fonética independente. Nenhuma alteração em Notion fez parte desta correção.

## Revisão e escopo

Base inicial: `1b277452c1177cbcd607ae39173fab7bc70f1d3c`, worktree limpo. Correção
limitada a `modules/audio_provider.py`, testes e este registro. Revisão local das
exceções, redaction, limite do detalhe, contrato do prompt e parada sem retry:
nenhum achado pendente. A revisão foi sequencial no contexto principal conforme
o mapeamento de ferramentas do projeto, sem revisão independente por outro modelo.

O repositório principal tinha dois commits locais anteriores ao trabalho; este
registro não autoriza publicá-los junto com a correção.

Referência oficial consultada para conferir suporte ao modelo:
[Gemini 3.1 Flash TTS Preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-tts-preview).
A documentação hoje apresenta esse modelo como legado, ainda suportado; nenhuma
migração de modelo foi necessária para resolver o incidente.
