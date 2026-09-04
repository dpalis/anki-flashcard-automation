---
title: "Anki Automation V2 Foundation - Plan"
type: feat
date: 2026-08-19
deepened: 2026-08-25
revised: 2026-08-26
topic: anki-automation-v2-foundation
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Anki Automation V2 Foundation - Plan

## O que foi cortado

Este plano trata o Anki Automation como ele é: um aplicativo pessoal, local e sequencial. A versão anterior tinha 11 unidades e mecanismos próprios de banco de dados, recuperação, autorização e operação. Eles não resolviam problemas proporcionais ao uso real.

- Sai o ledger SQLite, junto com WAL, migrações de schema, snapshots e restore. O Anki será a fonte de existência dos itens V2; `processadas.json` continuará sendo apenas o índice read-only da V1.
- Sai a máquina de estados com checkpoints de providers e mídia. Um item termina como criado, pulado ou erro; um resultado incerto encerra o lote e pede decisão humana.
- Saem tokens de autorização, hashes de confirmação, reinicialização obrigatória do Anki e protocolos de reconciliação automática.
- Saem auditorias recorrentes, fingerprints por lote, detecção de writers antigos e aprovação persistida. Haverá uma única auditoria read-only antes do uso real em inglês.
- Saem data home privado, camadas próprias de backup, manifests de mídia, conteúdo endereçado por hash e retenção automatizada.
- Saem HTTP, MCP, daemon, execução concorrente e action registry. ClaudeClaw receberá apenas uma entrada JSON síncrona sobre o mesmo fluxo da CLI.
- Sai o framework genérico de perfis, plugins e providers. Haverá dois perfis fixos e pequenos adapters apenas para os provedores realmente usados.
- Sai a recuperação automática de mídia órfã, notes incertas e falhas raras. O aplicativo para, diz o que sabe e não apaga nem repete nada por conta própria.
- Saem japonês, história e qualquer preparação específica para tipos futuros. Eles só voltam quando houver um requisito real e um plano próprio.

O resultado são três etapas. A primeira cabe em poucos dias ou poucas sessões focadas. Nenhuma etapa exige mudar cards ou dados antigos.

---

## Goal Capsule

- **Objective:** permitir que o usuário crie novos itens de inglês e espanhol latino-americano com dois sentidos de estudo e áudio, sem alterar o acervo existente nem gerar duplicatas silenciosas.
- **Means:** evoluir a CLI Python atual com dois perfis concretos, respostas estruturadas, uma note com dois templates e uma entrada JSON simples, conforme as decisões técnicas abaixo.
- **Authority:** o Product Contract governa o comportamento. As KTDs governam somente o mecanismo mínimo para cumpri-lo.
- **Execution profile:** três etapas sequenciais, testes locais curtos e validação com o Anki aberto. Não há operação autônoma prolongada.
- **Stop conditions:** parar se qualquer caminho puder atualizar ou apagar o legado, se uma mudança de formato parecer necessária ou se o resultado de `addNote` não for conhecido.
- **User-owned tail:** o usuário escolhe a voz de cada idioma, fornece credenciais para smokes pagos e decide o que fazer se a auditoria local encontrar algo além das anomalias já conhecidas.

---

## Product Contract

### Summary

A V2 acrescenta dois fluxos reais ao aplicativo existente: vocabulário em inglês e frases de viagem em espanhol latino-americano geral. Cada item novo vira uma note nova do Anki que gera os dois sentidos de estudo. A mesma função serve à CLI e a uma entrada JSON futura do ClaudeClaw.

Áudio é criado somente para notes V2 novas. O acervo V1 e seus arquivos permanecem intocados. Uma auditoria read-only confirma o estado real, mas não migra, corrige ou apaga nada.

### Problem Frame

A V1 já cria cards úteis, porém depende de um prompt textual frágil, conhece apenas inglês e executa dois `addNote` independentes. Ela também trata qualquer erro de leitura de `processadas.json` como cache vazio, o que pode permitir duplicatas.

O problema atual não pede uma plataforma. Ele pede um caminho curto para acrescentar espanhol e áudio usando a integração Anthropic já existente, sem colocar os 457 registros antigos em risco.

### Key Decisions

- **Aplicar Pareto a um aplicativo pessoal.** (session-settled: user-directed — chosen over infraestrutura de plataforma: aproximadamente 80% do valor deve vir com cerca de 20% da complexidade.) Governs all defined requirements.
- **Usar espanhol latino-americano geral.** (session-settled: user-directed — chosen over uma variante nacional: o perfil deve funcionar nas Américas sem foco em qualquer país.) Governs R1, R9.
- **Usar `Iapetus` em inglês e espanhol dentro do Gemini.** (session-settled: user-approved — chosen after blind listening: a simplicidade operacional vale mais que manter vozes ou fornecedores diferentes.) Governs R11, R14.
- **Não presumir migração.** (session-settled: user-directed — chosen over substituir o armazenamento V1: o formato atual será preservado se continuar seguro como índice read-only.) Governs R15, R16.
- **Falhar de forma clara.** (session-settled: user-directed — chosen over recuperação automática: um erro incomum encerra o lote, preserva o que já existe e devolve a decisão ao usuário.) Governs R18, R19.

### Requirements

**Uso e entrada**

- R1. A entrega deve oferecer os perfis fixos `english_vocabulary` e `spanish_travel` sem prometer um sistema genérico de perfis.
- R3. A aplicação deve aceitar um item ou um arquivo de itens pela CLI e nunca remover linhas do arquivo de entrada.
- R4. A aplicação deve aceitar o mesmo pedido por JSON em stdin e devolver um único resultado JSON em stdout, pronto para futura chamada pelo ClaudeClaw.

**Conteúdo e estudo**

- R5. Nesta entrega, o texto deve usar somente a API direta da Anthropic já existente; a assinatura Claude não conta como credencial de API.
- R6. A Anthropic deve devolver os campos estruturados do perfil, e a aplicação deve validá-los antes de gerar mídia ou chamar o Anki.
- R8. Inglês deve preservar somente os sentidos comuns, IPA, classe gramatical, um exemplo por sentido, apoio em português e imagem conceitual sem texto.
- R9. Espanhol deve produzir a formulação cotidiana mais comum para o contexto, com sentidos comuns, IPA, registro, um exemplo por sentido, apoio em português e imagem conceitual sem texto, em espanhol latino-americano adequado às Américas.

**Segurança do acervo e mídia**

- R11. Toda note de produção criada pela V2 deve ter somente o áudio principal, ao final do verso; o Gemini com a voz `Iapetus` atende os dois idiomas nesta entrega.
- R12. A aplicação não deve gerar áudio para cards, notes ou registros anteriores à V2.
- R14. Antes de um lote, a aplicação deve mostrar uma estimativa simples de bytes de áudio e imagem e pedir uma confirmação sem token persistente.
- R15. `processadas.json` deve permanecer byte a byte intocado e ser lido somente como lista de entradas inglesas conhecidas; nenhuma migração faz parte desta entrega.
- R16. O código V2 não deve oferecer operações de update, delete, mudança de deck ou alteração de note type sobre o acervo antigo.
- R18. Cada item novo deve usar uma note com dois templates, para que um único `addNote` produza os dois sentidos de estudo.
- R19. Antes de qualquer chamada paga, a aplicação deve pular uma entrada já presente no Anki V2. Para inglês, também deve pular entradas presentes no legado; se o resultado da criação for incerto, deve parar sem retry automático.

### Acceptance Examples

- AE1. **Covers R8, R11, R18.** Uma palavra inglesa nova cria uma note V2, dois cards, uma imagem e o mesmo áudio principal compartilhado pelos templates.
- AE2. **Covers R9, R11, R18.** Uma frase espanhola nova cria uma note V2 e dois cards com imagem, áudio, sentidos comuns, exemplos e apoio em português.
- AE3. **Covers R15, R19.** Uma palavra encontrada em `processadas.json` é informada como `skipped_legacy`; nenhum provedor e nenhuma action mutável do Anki são chamados.
- AE4. **Covers R18, R19.** Um timeout durante `addNote` encerra o lote com a entrada e a etapa identificadas; a aplicação não repete a criação nem remove mídia.
- AE5. **Covers R4, R14.** Um lote JSON sem confirmação recebe a estimativa e `needs_confirmation`; o mesmo pedido com `confirmed: true` usa o fluxo da CLI sem prompt interativo.

### Success Criteria

- Duas ou três entradas reais de cada idioma geram exatamente uma note e dois cards por item com o Anki aberto.
- Repetir o mesmo pedido não aumenta a contagem de notes ou cards.
- Inglês mantém os sentidos comuns e a imagem sem texto que dão valor à V1.
- Espanhol soa geral para as Américas e não assume vocabulário de um país específico.
- Todos os novos itens de produção têm áudio; nenhum item antigo recebe mídia nova.
- CLI e JSON produzem o mesmo resultado lógico.
- O hash de `processadas.json` e os arquivos de mídia V1 são iguais antes e depois dos testes; nenhuma action mutável recebe um note ID legado.
- Um erro de provider, mídia ou Anki informa item, etapa e ação humana possível sem executar recuperação automática.

### Scope Boundaries

**Nesta entrega**

- Dois perfis fixos, Anthropic para texto, Pollinations para imagem nos dois idiomas e Gemini para áudio.
- CLI, JSON síncrono, criação sequencial e uma auditoria read-only do legado.
- Novos note types V2; nenhuma reutilização ou edição do note type `Basic` existente.

**Adiado**

- Japonês, história, perfis definidos pelo usuário e provider plugins.
- OpenAI como segundo provedor de texto, até existir benefício concreto.
- Integração dentro do ClaudeClaw, HTTP, MCP, daemon, paralelismo e lotes autônomos.
- Qualquer reparo, limpeza, reconciliação ou mudança de formato do legado.

**Fora do produto atual**

- Multiusuário, permissões por papel, alta disponibilidade, telemetria operacional, recuperação automática e backups mantidos pela aplicação.
- Áudio retroativo e alteração de cards existentes.

---

## Planning Contract

### Current Evidence

| Evidência | Estado verificado | Consequência mínima |
|---|---|---|
| Código | `main.py` orquestra quatro módulos concretos e sequenciais | Reusar a estrutura plana; não criar service/repository/framework |
| Criação | A V1 usa dois `addNote` independentes | Uma note V2 com dois templates remove a falha parcial provável |
| Cache | `load_cache()` converte erro em `{}` e `--reset-cache` sobrescreve o arquivo | A V2 deve ler fail-closed e remover qualquer escrita no legado |
| Legado | 457 chaves, 1.101 referências e 973 note IDs únicos | As chaves servem para bloquear duplicatas; os IDs não servem como pares |
| Anomalias | 128 IDs compartilhados; `bout` tem 187; `yarn` tem quatro | Reportar, sem inferir propriedade, corrigir ou migrar |
| Mídia V1 | 458 JPGs e 31,8 MiB; `injunction.jpg` é órfã | Manter tudo intocado; a V2 usa nomes próprios |
| Testes | Não há suíte automatizada no repositório | Criar uma suíte curta com a biblioteca padrão |

O formato V1 não precisa mudar. A V2 só precisa saber se uma entrada inglesa já é conhecida, e as 457 chaves respondem a essa pergunta. Os IDs anômalos seriam um problema para reconstruir pares ou editar cards, mas a V2 não fará nenhuma dessas coisas. Portanto, migrar o arquivo acrescentaria risco sem resolver um problema atual.

O SHA-256 observado em 25 de agosto de 2026 foi `1e24255a94fe155dd67afde04882162febecc331c5c300dc89a82db5d5dfead8`. Ele pertence ao relatório de planejamento e não será hardcoded na aplicação. A auditoria local registra o hash encontrado antes e depois; se o JSON não puder ser lido, a criação inglesa para com erro.

### Mecanismos mantidos e o problema de hoje

| Mecanismo | Problema concreto e provável que resolve |
|---|---|
| Dois perfis fixos (KTD2) | Inglês e espanhol precisam de conteúdo e cards diferentes agora |
| Output estruturado por API direta (KTD3) | O parser textual atual quebra quando o modelo muda formatação |
| Leitura fail-closed do legado (KTD4) | Um JSON ausente ou inválido hoje é tratado como cache vazio |
| `ItemId` + uma note/dois templates (KTD5) | A V1 pode criar só um dos dois sentidos ou repetir um item |
| Nome V2 único por mídia (KTD6) | O filename atual deriva apenas da palavra e pode colidir ou sobrescrever |
| Piloto pequeno de voz por idioma (KTD7) | A qualidade percebida varia por voz e idioma |
| Falha sequencial e explícita (KTD9) | Continuar após resultado incerto pode esconder duplicata ou dano parcial |
| Estimativa e confirmação simples (KTD10) | Um lote pode consumir espaço e API sem o usuário perceber antes |

### Desenho técnico mínimo

O aplicativo continua sendo um único processo local. CLI e JSON são apenas duas portas para o mesmo fluxo:

```text
CLI ou JSON -> processar item -> texto -> mídia -> AnkiConnect -> resultado
                         |                         |
                         +-- qualquer erro: parar + explicar
```

Antes de gastar ou criar qualquer coisa, o fluxo faz uma preflight curta:

```text
validar pedido -> procurar ItemId exato -> consultar legado, só em inglês -> conferir note type -> continuar
        erro ou conflito -----------------------------------------------> parar
```

Não existe serviço de fundo, fila, banco da V2 ou processo de reconciliação.

### Key Technical Decisions

- KTD1. **Manter uma única função de processamento.** `main.py` continua como composition root; `--profile` combina com `--item` ou `--file`, e `--json` lê stdin. As duas entradas convertem o pedido para a mesma chamada síncrona. Logs humanos vão para stderr no modo JSON. Governs R3, R4.
- KTD2. **Adicionar somente dois perfis concretos.** `modules/profiles.py` contém fields, prompts, tags, note types e defaults. A configuração escolhe deck, modelo Anthropic e voz para cada perfil; não há registry dinâmico ou linguagem de configuração. Governs R1, R8, R9.
- KTD3. **Usar Structured Outputs da Anthropic com validação local pequena.** A integração existente retorna o schema do perfil. As duas validações concretas verificam campos, tipos, cardinalidade e strings vazias; não haverá protocolo universal de mensagens nem framework de schema. Governs R5, R6.
- KTD4. **Não criar armazenamento operacional V2.** (session-settled: user-directed — chosen over SQLite ou novo JSON mutável: o Anki já informa se a note V2 existe, e o legado só precisa ser lido.) O caminho de `processadas.json` é configurável, read-only e consultado apenas por `english_vocabulary`. Suas chaves formam em memória uma blocklist com a mesma normalização de KTD5. Entradas de arquivo também são read-only. Governs R15, R19.
- KTD5. **Usar um note type V2 por perfil, uma note por item e dois templates.** A entrada canônica usa Unicode NFC, trim, espaços internos colapsados e casefold. `ItemId` é o SHA-256 hexadecimal de `profile_id`, um byte NUL e essa entrada. Para inglês, a busca trata somente o prefixo convencional minúsculo `to ` como alias da forma sem esse marcador, preservando os IDs já existentes; uma frase iniciada por `To ` permanece literal, e espanhol também permanece literal. A busca usa apenas esses hex seguros e confirma igualdade exata em `notesInfo`; um resultado total pula e informa o `Input` já existente, enquanto múltiplos resultados param. `addNote` é a única criação dos dois sentidos. O deck configurado deve existir; a aplicação não cria nem reorganiza decks. Governs R8, R9, R16, R18, R19.
- KTD6. **Manter mídia simples e isolada.** Imagem e áudio usam filenames `aa2_<ItemId>_<slot>.<ext>` e são enviados ao Anki a partir de arquivo temporário. Antes do upload, a resposta deve ter o MIME esperado, tamanho não trivial e assinatura JPEG, PNG ou MP3 reconhecível. Se o filename já existir sem a note correspondente, o item para e informa a colisão; não há overwrite nem limpeza automática. Governs R11, R12, R16, R19.
- KTD7. **Escolher voz com um piloto pequeno e descartável.** `gemini-3.1-flash-tts-preview` gerou, para cada idioma, oito utterances com `Iapetus` e oito com `Erinome`, totalizando 32 amostras. Houve uma tentativa por clipe, sem retry; cada saída foi convertida para MP3 e o WAV temporário foi descartado imediatamente. A avaliação cega escolheu `Iapetus` para inglês e espanhol. O relatório separa qualidade perceptiva de preço, sucessos e falhas observados, latência e bytes. O código do piloto fica fora do produto; a aplicação recebe um único adapter Gemini com `Iapetus`. Governs R11, R14.
- KTD8. **Manter Pollinations como único gerador de imagem.** Os dois idiomas usam o endpoint atual `https://gen.pollinations.ai/image` com `flux`. O prompt condensa todos os significados apresentados em uma imagem coerente; se isso for impossível, usa o significado mais comum. Falha terminal para o item, sem fallback. A chave vai em header de autorização, nunca na URL. Governs R8, R9.
- KTD9. **Processar um item por vez e parar no primeiro erro.** O conector propaga um erro pequeno com `action` e `outcome_uncertain`. Erro declarado pelo AnkiConnect é definitivo; timeout, falha de transporte ou resposta inválida durante uma operação mutável (`createModel`, `storeMediaFile` ou `addNote`) é incerto. O resultado informa item, etapa e incerteza. Não há retry dessas operações, rollback, delete ou correção automática. Governs R16, R18, R19.
- KTD10. **Confirmar lotes sem protocolo de autorização.** Para mais de um item, a CLI mostra a projeção e pergunta uma vez. JSON devolve `needs_confirmation` até receber o mesmo pedido com `confirmed: true`; não há token, hash ou estado persistido. Governs R4, R14.

Credenciais vêm somente do ambiente: `ANTHROPIC_API_KEY`, `POLLINATIONS_API_KEY` e `GEMINI_API_KEY`. Arquivos versionados guardam apenas nomes de providers, modelos, decks e placeholders. stdout, stderr e relatórios nunca exibem chaves, headers ou URLs autenticadas. Isso evita o vazamento provável de segredos sem criar um sistema próprio de autorização.

### Perfis mínimos

| Aspecto | `english_vocabulary` | `spanish_travel` |
|---|---|---|
| Entrada | Palavra ou expressão inglesa | Frase ou intenção de viagem |
| Output estruturado | `term`, `ipa`, `parts_of_speech`, `senses`, `visual_prompt_en` | `phrase_es`, `ipa`, `register`, `senses`, `visual_prompt_en` |
| Cardinalidade | Sentidos comuns em ordem de frequência; cada um tem `definition_en`, `meaning_pt_br` e `example_en` | Sentidos comuns da formulação cotidiana escolhida; cada um tem `definition_es`, `meaning_pt_br` e `example_es` |
| Frente 1 | Palavra ou expressão em azul e bold | Frase em azul e bold |
| Frente 2 | Imagem | Imagem |
| Mídia | Imagem e áudio de `term` ao final do verso | Imagem e áudio de `phrase_es` ao final do verso |
| Locale | Inglês contemporâneo geral | Espanhol latino-americano geral, sem país-alvo |

Os dois note types usam os fields, nesta ordem: `ItemId`, `Input`, `Target`, `ContentHtml`, `Image`, `MainAudio`. Seus templates finais são `Target to Meaning` e `Image to Target`. No primeiro, o verso começa pela imagem; no segundo, começa pelo target azul e bold. Ambos seguem com significados separados, um exemplo por significado, traduções, classificação, IPA e áudio ao final.

U1 cria cada note type somente se ele não existir, já com os fields finais. Em toda execução, compara ordem dos fields, nomes dos templates e HTML de frente e verso com o contrato local. Qualquer desvio para antes das chamadas pagas; o aplicativo nunca edita um note type existente. Os dois templates usam os mesmos filenames da note, sem duplicar mídia.

### Entrada JSON mínima

```json
{"profile":"spanish_travel","items":["Quero pedir a conta"],"confirmed":false}
```

O resultado possui apenas `status`, `estimate`, `created`, `skipped` e `error`. `status` pode ser `ok`, `needs_confirmation` ou `error`. Cada item criado devolve `item_id` e `note_id`; cada item pulado devolve `reason`. Em erro, `error` inclui item, etapa, mensagem e `outcome_uncertain`. Não existem actions separadas de auditoria, aprovação ou retry.

### Estimativa de armazenamento

O piloto parte de 4 a 12 segundos de áudio por note e MP3 entre 64 e 128 kb/s: cerca de 32 a 192 KiB por item. A imagem V1 observada acrescenta de 55,8 KiB (mediana) a 172,3 KiB (p95).

| Lote novo | Cada idioma com imagem |
|---:|---:|
| 1 item | 88-364 KiB |
| 100 itens | 8,6-35,6 MiB |
| 1.000 itens | 86-356 MiB |

Esses valores são uma faixa de planejamento. U3 substitui a parte de áudio por bytes reais das vozes escolhidas. O armazenamento de produção fica no media collection do Anki; a aplicação não mantém uma segunda cópia permanente.

### Riscos conscientemente aceitos

- Um timeout de `addNote` pode deixar uma note criada sem resposta conclusiva. A aplicação para e pede uma verificação pelo `ItemId`; não tenta resolver sozinha.
- Uma falha após upload pode deixar mídia V2 órfã no Anki. O filename é informado, mas a aplicação não remove o arquivo automaticamente.
- Uma indisponibilidade de Anthropic, Gemini TTS, Pollinations ou AnkiConnect interrompe o lote. O usuário tenta novamente quando quiser.
- Execuções concorrentes não são suportadas. O uso previsto é uma única CLI ou chamada ClaudeClaw por vez.
- O piloto de oito utterances por voz compara qualidade perceptiva, mas não prova confiabilidade estatística. O relatório diz apenas o que foi observado e usa preço oficial vigente.
- O índice V1 pode pular um termo cujos cards já não existam. Esse falso positivo é preferível a recriar silenciosamente; o usuário decide qualquer exceção fora do fluxo automático.
- A identidade bloqueia variantes que diferem apenas por maiúsculas, como `Polish` e `polish`. Esse falso positivo explícito é aceito para evitar duplicatas comuns; o usuário pode usar uma entrada mais específica se quiser estudar os dois sentidos.
- A identidade impede a repetição da mesma entrada canônica, mas não tenta reconhecer paráfrases ou sinônimos como duplicatas. Fazer essa inferência exigiria complexidade e poderia bloquear itens legítimos.
- A validação leve de MIME, tamanho e assinatura não detecta toda corrupção possível de mídia. A reprodução e renderização no deck de QA são o teste final; não serão adicionados decoders pesados para uma falha rara.
- Uma edição manual em note type V2 bloqueia novas criações até o usuário decidir como proceder. A aplicação não repara templates.

### Alternatives Rejected

- **SQLite ou JSON mutável V2:** cria estado para reconciliar com outro estado; `ItemId` no Anki resolve a necessidade atual.
- **Duas notes Basic por item:** mantém a janela real de criação parcial.
- **Framework universal de perfis/providers:** não há terceiro caso concreto que justifique a abstração.
- **`claude -p` ou `codex exec` como backend:** são ferramentas de agente e assinatura, não substitutos simples das APIs diretas.
- **Migração ou correção do legado:** os IDs anômalos não são usados pelo novo fluxo; mudar o arquivo só adicionaria risco.
- **Retry, rollback e reconciliação automáticos:** escondem incerteza justamente quando o usuário prefere parar e decidir.
- **Fallback automático de voz, texto ou imagem:** pode mudar qualidade e custo sem consentimento.

### Deferred User Decisions

Estas escolhas não bloqueiam U1, mas precisam existir antes do uso real:

- Disponibilizar credenciais e autorizar o custo nominal dos smokes e do piloto.
- Revisar o relatório local do legado antes de ativar criação inglesa nos decks reais.

### Sources and Research

Fontes oficiais consultadas ou revalidadas em 26 de agosto de 2026:

- Código atual: `main.py`, `modules/llm_provider.py`, `modules/anki_connector.py`, `modules/image_provider.py` e `modules/card_formatter.py`.
- [Anthropic Structured Outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) e [billing de assinatura versus API](https://support.claude.com/en/articles/9876003).
- [Gemini text-to-speech](https://ai.google.dev/gemini-api/docs/speech-generation) e [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing).
- [Anki: card types e reverse cards](https://docs.ankiweb.net/templates/generation.html#reverse-cards), [busca por field](https://docs.ankiweb.net/searching.html#limiting-to-a-field) e [media](https://docs.ankiweb.net/media.html).
- [AnkiConnect upstream](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md) e [AnkiWeb add-on](https://ankiweb.net/shared/info/2055492159).
- [Pollinations API](https://github.com/pollinations/pollinations/blob/main/APIDOCS.md) e [model catalog](https://gen.pollinations.ai/image/models).

---

## Implementation Units

### U1. Etapa 1 — Núcleo bilíngue funcional em deck de QA

- **Goal:** criar e revisar cards de inglês e espanhol em um deck descartável, com uma note e dois sentidos, sem tocar no legado. Esta etapa valida conteúdo, identidade, templates e entrada JSON. Uma imagem-fixture local preenche o card inglês; áudio continua vazio. Cabe em poucos dias ou poucas sessões focadas.
- **Requirements:** R1, R3, R4, R5, R6, R8, R9, R15, R16, R18, R19.
- **Dependencies:** nenhuma.
- **Files:** `main.py`, `run.sh`, `modules/profiles.py`, `modules/llm_provider.py`, `modules/anki_connector.py`, `modules/card_formatter.py`, `config/prompt_template.txt`, `config/spanish_prompt_template.txt`, `config/settings.example.json`, `tests/test_core_flow.py`, `tests/fixtures/qa-image.png`.
- **Approach:**
  1. Extrair do fluxo atual uma única função `process_item`; remover do executável `--reset-cache`, `save_cache()` e qualquer remoção de linhas de entrada. Reduzir `run.sh` a ativar o ambiente e repassar argumentos, sem banners, instalação ou validação própria.
  2. Definir exatamente os dois schemas e os dois contratos finais de note type em `modules/profiles.py`.
  3. Adaptar primeiro o provider Anthropic existente para Structured Outputs, sem criar uma hierarquia genérica de providers.
  4. Calcular o `ItemId`, confirmar o resultado exato no Anki e, somente em inglês, consultar também o alias com ou sem o marcador minúsculo `to ` e comparar as identidades contra uma blocklist das 457 chaves normalizadas. Fazer toda essa preflight antes do provider.
  5. Criar os note types V2 somente se ausentes; se fields ou templates existentes divergirem, parar sem reparo. No QA, usar mídia-fixture para validar `Target to Meaning` e `Image to Target`. Usar um único `addNote` por item.
  6. Fazer CLI e JSON chamarem o mesmo fluxo; JSON nunca mistura logs humanos em stdout.
- **Test scenarios:**
  - JSON legado inválido ou ausente encerra inglês antes de qualquer provider ou action mutável, mas não bloqueia espanhol.
  - O fluxo não abre `processadas.json` nem o arquivo de entrada em modo de escrita e não expõe `--reset-cache`.
  - Entrada inglesa presente no legado retorna `skipped_legacy` e faz zero chamadas pagas, inclusive com variações de caixa, Unicode e espaços.
  - A mesma entrada canônica produz o mesmo hash; `Polish` e `polish` colidem de propósito, e a segunda tentativa é pulada com o `Input` existente informado. A busca só pula depois de confirmar o field exato.
  - Um `ItemId` exato retorna `skipped_v2`; dois resultados exatos param e explicam o conflito.
  - Os dois schemas aceitam somente os campos e cardinalidades definidos; refusal ou campo vazio para antes do Anki. Sentidos ingleses adicionais continuam válidos quando seguem o mesmo schema.
  - Note type ausente pode ser criado; divergência de field, ordem, template ou HTML para sem modificar o modelo.
  - O conector não oferece update, delete ou mudança de deck; toda action mutável de teste usa apenas note types V2, mídia `aa2_` e um deck já existente.
  - Cada operação mutável é chamada no máximo uma vez por item. Erro declarado é definitivo; timeout ou resposta inválida retorna `outcome_uncertain: true` e não dispara retry.
  - A CLI direta e `run.sh` escrevem um único objeto em stdout no modo JSON, enquanto mensagens humanas vão para stderr.
  - HTML vindo de input ou provider é escapado antes de chegar aos fields.
- **Verification:** a suíte local passa e, com o Anki aberto, duas entradas por idioma geram uma note e dois cards no deck de QA. Inglês usa a fixture local; os fields de áudio ficam vazios. Repetir as quatro entradas não muda as contagens.

### U2. Etapa 2 — Auditoria read-only do índice inglês

- **Goal:** confirmar uma vez que o arquivo V1 pode continuar como blocklist read-only. A etapa produz informação para a ativação inglesa; não consulta nem altera cards e não condiciona o espanhol.
- **Requirements:** R15, R16, R19.
- **Dependencies:** U1.
- **Files:** `scripts/audit_legacy.py`, `tests/test_legacy_audit.py`.
- **Approach:**
  1. Criar um script independente que abre `processadas.json` e `data/images/` somente para leitura e calcula agregados.
  2. Na execução real, reproduzir 457 chaves, 1.101 referências, 973 IDs únicos, 128 compartilhados e 458 JPGs; mostrar separadamente `bout`, `yarn` e `injunction.jpg` sem inferir propriedade ou correção.
  3. Gravar um único relatório local ignorado pelo Git e comparar o hash do JSON antes e depois. O relatório não lista os 973 IDs nem consulta cada note no Anki, porque o runtime não usa essa informação.
- **Test scenarios:**
  - Uma fixture pequena com ID compartilhado, quantidade incomum e imagem órfã prova os agregados sem copiar as 457 entradas para a suíte.
  - O script não importa o conector do Anki e não abre o legado nem as imagens para escrita.
  - JSON inválido ou diretório ausente encerra a auditoria com relatório parcial claro, sem criar ou corrigir nada.
  - O relatório mostra IDs compartilhados e quantidades incomuns, mas nunca sugere que uma chave seja dona de um ID.
- **Verification:** a execução cobre as 457 entradas e 458 imagens locais. O usuário recebe os agregados e discrepâncias, e o SHA-256 de `processadas.json` permanece igual. Se houver evidência nova, a ativação inglesa espera a decisão do usuário; o espanhol não é bloqueado.

### U3. Etapa 3 — Áudio e ativação real

- **Goal:** escolher uma voz por idioma e criar notes novas completas com mídia e estimativa simples.
- **Requirements:** R3, R4, R8, R9, R11, R12, R14, R16, R18, R19.
- **Dependencies:** U1. U2 bloqueia somente a ativação inglesa em deck real.
- **Files:** `main.py`, `modules/image_provider.py`, `modules/audio_provider.py`, `requirements.txt`, `config/settings.example.json`, `tests/test_media_and_providers.py`, `docs/evaluations/audio-provider-bakeoff.md`, `README.md`, `CLAUDE.md`.
- **Approach:**
  1. Gerar o piloto cego em script descartável, registrar qualidade humana separada das medidas objetivas e obter uma escolha por idioma.
  2. Implementar um único adapter Gemini com `Iapetus` nos dois idiomas. Não criar uma abstração genérica de providers.
  3. Baixar mídia em temporário, validar MIME, tamanho e assinatura, usar filenames por `ItemId` e enviar ao Anki. Pollinations atende os dois idiomas.
  4. Medir os bytes das vozes escolhidas, calcular a faixa do lote e aplicar a confirmação simples. Ler segredos somente do ambiente.
  5. Validar primeiro em QA; depois ativar espanhol no deck real e inglês somente após a revisão de U2. Atualizar README e CLAUDE com o fluxo final.
- **Test scenarios:**
  - Uma note nova recebe somente áudio principal ao final do verso; item legado ou V2 pulado não chama TTS.
  - MIME, tamanho ou assinatura inválida para antes de `storeMediaFile`; filename existente sem note correspondente não é sobrescrito.
  - Os dois templates referenciam os mesmos filenames e a reprodução funciona nos lados definidos.
  - Lote sem confirmação retorna estimativa; lote confirmado segue sem token ou estado persistido.
  - Falha de texto, Pollinations ou TTS encerra o lote com provider e item identificados, sem fallback.
  - Valores sentinela de todas as credenciais não aparecem em stdout, stderr, relatório nem URLs de erro.
- **Verification:** smokes mínimos das APIs passam com custo previamente autorizado. O usuário aceita uma voz por idioma. Quatro entradas novas, duas de cada idioma, funcionam no deck de QA; depois, duas ou três entradas novas por idioma funcionam nos decks reais permitidos. Repetir os pedidos não muda as contagens, e o hash do legado inglês permanece igual.

---

## Verification Contract

### Automated Gate

- `python -m unittest discover -s tests -v` cobre os três arquivos de teste sem adicionar um framework de testes ao projeto.
- Testes de unidade usam fakes para providers e AnkiConnect. Eles nunca chamam APIs pagas nem a coleção real.
- Smokes de providers ficam separados e exigem credenciais e autorização de custo nominal.

### Real Anki Gate

1. Abrir o Anki com AnkiConnect e usar primeiro um deck de QA.
2. Em U1, criar duas notes inglesas e duas espanholas no deck de QA; confirmar dois cards por note e os contratos finais de fields e templates.
3. Repetir as mesmas entradas; confirmar zero notes ou cards adicionais. Fechar o Anki antes de outra entrada e confirmar erro claro antes de chamada paga.
4. Em U2, revisar uma vez a auditoria local das 457 entradas. A decisão do usuário libera somente o inglês real.
5. Em U3, usar quatro entradas novas no deck de QA, com áudio e imagem Pollinations nos dois idiomas; conferir o layout e ouvir o áudio no verso dos dois templates.
6. Criar duas ou três notes espanholas no deck real. Criar as inglesas após a liberação de U2. Confirmar zero duplicatas, somente novos note IDs V2 e hash legado inalterado.

### Requirement Traceability

| Requirements | Primary unit | Evidence |
|---|---|---|
| R1, R3, R4, R9, R18 | U1 | Testes do fluxo e cards no deck de QA |
| R5, R6 | U1 | Structured Outputs da Anthropic e validação dos schemas |
| R8, R9 | U1, U3 | Schemas, templates compartilhados e imagem Pollinations nos dois idiomas |
| R11, R12, R14 | U3 | Smokes, piloto cego, mídia e estimativa |
| R15, R16 | U1, U2 | Ausência de escrita no legado e relatório local antes/depois |
| R19 | U1, U2, U3 | Duplicatas, timeouts e falha explícita em cada fronteira |

---

## Definition of Done

- O documento continua sendo o único plano da V2 e contém no máximo três unidades ativas.
- `english_vocabulary` e `spanish_travel` passam nos testes locais e reais.
- Cada note nova de produção gera exatamente dois cards e contém o áudio definido para seu idioma.
- Repetir uma entrada legada ou V2 nunca cria uma duplicata silenciosa.
- CLI e JSON usam o mesmo fluxo e retornam resultados equivalentes.
- `processadas.json`, suas 457 chaves e as 458 imagens V1 permanecem inalterados; nenhuma action mutável recebe note IDs legados.
- A auditoria conclui que o formato V1 pode continuar read-only ou, se encontrar nova evidência, para com um relatório; ela nunca aplica mudança.
- O usuário escolhe uma voz aceitável por idioma com qualidade perceptiva cega e medidas objetivas separadas.
- README e CLAUDE descrevem apenas o fluxo implementado, as estimativas e as limitações aceitas.
- Não existem ledger V2, state machine, tokens, retry de operações mutáveis, recuperação automática, HTTP/MCP, daemon, paralelismo ou operações de update/delete sobre o legado.
- Qualquer erro incomum deixa claro o que foi criado, o que pode ter sido criado e qual decisão permanece com o usuário.
