# Piloto de vozes Gemini

Status: piloto e avaliação cega concluídos em 27 de agosto de 2026 com 32 de 32 MP3s válidos. `Iapetus` foi escolhida para inglês e espanhol; o Anki não foi acessado, nenhum card foi criado e nenhuma integração foi iniciada.

## O piloto mínimo

Serão comparadas somente quatro combinações do mesmo fornecedor, com as mesmas oito amostras por idioma:

| Idioma | Fornecedor | Modelo ou engine | Voz | Configuração |
|---|---|---|---|---|
| Inglês | Gemini TTS | `gemini-3.1-flash-tts-preview` | `Iapetus` | PCM mono a 24 kHz convertido para MP3 a 96 kb/s |
| Inglês | Gemini TTS | `gemini-3.1-flash-tts-preview` | `Erinome` | PCM mono a 24 kHz convertido para MP3 a 96 kb/s |
| Espanhol | Gemini TTS | `gemini-3.1-flash-tts-preview` | `Iapetus` | PCM mono a 24 kHz convertido para MP3 a 96 kb/s |
| Espanhol | Gemini TTS | `gemini-3.1-flash-tts-preview` | `Erinome` | PCM mono a 24 kHz convertido para MP3 a 96 kb/s |

Isso produz exatamente 32 clipes: duas vozes × dois idiomas × oito amostras. Haverá uma única geração por clipe, sem retry. Cada resposta será envolvida em um WAV temporário apenas para a conversão; o WAV será apagado imediatamente, inclusive se a conversão falhar.

Por que estas candidatas:

- O Gemini descreve `Iapetus` e `Erinome` como vozes claras. Usar o mesmo par nos dois idiomas mantém o piloto pequeno e permite escolher a voz separadamente por idioma.
- A decisão deliberada é privilegiar simplicidade operacional: o piloto avalia somente vozes Gemini e não tenta comparar todos os fornecedores disponíveis.

## Amostras

Cada voz recebe exatamente o mesmo texto e a mesma instrução mínima por idioma: inglês americano contemporâneo ou espanhol latino-americano geral, ambos claros e em ritmo confortável de estudo. Não há SSML.

### Inglês

1. Could you explain what you mean by subtle?
2. The meeting was postponed until Thursday.
3. She bought a warm jacket for the trip.
4. I didn't expect the train to arrive so early.
5. The rural road curves through the valley.
6. Would you mind speaking a little more slowly?
7. I keep a written record, and I record every change.
8. Although it was raining, we decided to continue.

### Espanhol latino-americano

1. ¿Dónde está la estación?
2. Quisiera pedir la cuenta, por favor.
3. ¿A qué hora sale el próximo tren?
4. Necesito una habitación tranquila para esta noche.
5. ¿Aceptan tarjeta o solamente efectivo?
6. Perdón, no entendí. ¿Podría hablar un poco más despacio?
7. Mi vuelo sale a las 7:45 del 23 de agosto.
8. Aunque está lloviendo, queremos continuar con el recorrido.

O roteiro tem 689 caracteres e 120 palavras. Ele cobre perguntas, afirmações, palavras de pronúncia menos óbvia, números, horário, data e frases mais longas, sem vocabulário espanhol específico de um país.

## Custo máximo proposto

| Parte | Base objetiva | Limite desta rodada |
|---|---|---:|
| Gemini 3.1 Flash TTS Preview | US$ 1 por 1 milhão de tokens de texto e US$ 20 por 1 milhão de tokens de áudio; 25 tokens de áudio por segundo equivalem a cerca de US$ 0,03 por minuto | US$ 0,24 |
| **Teto autorizado** | Limite operacional sem contar eventual free tier | **US$ 0,25** |

Com dois a quatro minutos estimados, o áudio deve custar cerca de US$ 0,06 a US$ 0,12 no preço pago, mais uma fração de centavo pelo texto. O piloto fará somente as 32 chamadas curtas previstas. Qualquer erro ou resposta inválida interrompe a execução, preservando os MP3s já gerados e sem repetir chamadas.

## Armazenamento estimado

As 32 amostras devem somar aproximadamente dois a quatro minutos. Usando a faixa de planejamento de 64 a 128 kb/s, a estimativa é de 0,9 a 3,7 MiB. O piloto reservará **até 4 MiB** para os MP3s.

Os bytes reais serão registrados por combinação. As amostras serão locais e descartáveis; não serão enviadas ao Anki nem versionadas.

## Como a escolha será feita

1. Os arquivos serão apresentados por idioma com rótulos neutros, sem voz no nome.
2. Primeiro será registrada somente a qualidade perceptiva: naturalidade, clareza da pronúncia e conforto para ouvir repetidamente.
3. Depois os nomes serão revelados e será mostrada uma tabela objetiva com custo estimado pelo uso, sucessos e falhas, latência e bytes.
4. O usuário escolherá uma vencedora para inglês e outra para espanhol.

O piloto não tenta provar confiabilidade estatística. Ele responde apenas qual voz soa melhor neste uso e registra o comportamento observado nesta pequena rodada.

## Resultado da tentativa de 26 de agosto de 2026

- Requisições aceitas pelo modelo: **0**.
- Clipes gerados: **0 de 32**.
- Custo de TTS: **US$ 0,00**.
- Armazenamento de áudio: **0 bytes**.
- Motivo da parada: a `GEMINI_API_KEY` disponível no ambiente foi recusada pela API como inválida antes da geração.
- Próxima ação: configurar uma credencial válida e obter autorização explícita para uma rodada nova; não haverá retry automático desta tentativa.

## Resultado da rodada autorizada de 27 de agosto de 2026

- Requisições que chegaram à API: **1**.
- Requisições aceitas para geração pelo modelo: **0**.
- Clipes gerados: **0 de 32**.
- Custo de TTS: **US$ 0,00**.
- Armazenamento de áudio: **0 bytes**.
- Motivo da parada: a API rejeitou `delivery: inline` no formato de resposta com `Audio delivery mode is not supported`.
- Diagnóstico: o exemplo REST oficial vigente usa somente `response_format: {"type":"audio"}`; o WAV deve ser criado localmente a partir do áudio retornado antes da conversão para MP3.
- Regra preservada: não houve segunda chamada, retry, Anki, integração ou criação de card.

Uma tentativa local anterior nem chegou à API porque o sandbox bloqueou DNS; ela não gerou áudio nem custo e não entra nas métricas do provider.

## Resultado da rodada concluída de 27 de agosto de 2026

- Clipes gerados: **32 de 32**, com uma chamada por clipe e sem retry.
- Duração total: **111,960 segundos**.
- Custo estimado pelo uso registrado: **US$ 0,073568**.
- Armazenamento: **1.376.064 bytes (1,312 MiB)**.
- Formato verificado: **32 MP3s**, mono, 24 kHz e 96 kb/s nominal.
- Arquivos temporários restantes: **nenhum WAV ou MP3 parcial**.
- Anonimização: filenames contêm somente idioma, rótulo A/B e número da frase; o mapa privado fica fora da pasta das amostras com permissão `0600`.

| Combinação cega | Clipes | Duração | Bytes | Custo estimado |
|---|---:|---:|---:|---:|
| Inglês A | 8 | 27,400 s | 337.032 | US$ 0,017976 |
| Inglês B | 8 | 27,080 s | 333.000 | US$ 0,017756 |
| Espanhol A | 8 | 28,760 s | 353.448 | US$ 0,018938 |
| Espanhol B | 8 | 28,720 s | 352.584 | US$ 0,018898 |

## Resultado da avaliação cega

O usuário escolheu **Inglês A** e **Espanhol B**. Como os rótulos foram sorteados separadamente por idioma, ambas as escolhas correspondem à mesma voz: **`Iapetus`**.

| Idioma | Escolha | Voz revelada | Duração | Bytes | Custo estimado |
|---|---|---|---:|---:|---:|
| Inglês | A | `Iapetus` | 27,400 s | 337.032 | US$ 0,017976 |
| Espanhol latino-americano | B | `Iapetus` | 28,720 s | 352.584 | US$ 0,018898 |

Mapa completo revelado: Inglês A = `Iapetus`, Inglês B = `Erinome`, Espanhol A = `Erinome` e Espanhol B = `Iapetus`.

## Regra de parada e próximo gate

O gate da avaliação perceptiva cega foi concluído. O piloto para aqui:

- nenhuma integração do Gemini foi iniciada;
- o Anki continuará fechado;
- nenhum card será criado, nem no QA nem nos decks reais;
- nenhum fornecedor adicional ou fallback será acrescentado.
- nenhum WAV temporário será preservado.

A integração mínima da voz escolhida na Etapa 3 depende de nova autorização explícita.

## Fontes oficiais verificadas em 27 de agosto de 2026

- [Gemini: geração text-to-speech, vozes e idiomas](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Gemini API: preços do modelo TTS](https://ai.google.dev/gemini-api/docs/pricing)
