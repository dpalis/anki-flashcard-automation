---
title: Atualizar dependencias e migrar API do Pollinations
type: fix
status: completed
date: 2026-02-26
---

# Atualizar dependencias e migrar endpoint do Pollinations.ai

## Overview

O projeto parou em outubro/2025. Antes de rodar uma nova leva de 180 palavras, a revisao identificou:

1. **Bloqueante**: Endpoint antigo do Pollinations (`image.pollinations.ai/prompt/`) retorna 530. Novo endpoint (`gen.pollinations.ai/image/`) exige API key
2. **Importante**: SDK anthropic desatualizado (0.71.0 → 0.84.0)
3. **Importante**: Modelo LLM desatualizado — migrar para `claude-sonnet-4-6`
4. **Menor**: requirements.txt sem versoes pinadas, typo no nome da classe

## ~~Etapa 0 — Conta no Pollinations~~ CONCLUIDA

- Conta criada via GitHub OAuth em enter.pollinations.ai
- Secret key criada (nome: `anki-automation`) e configurada em `config/settings.json`
- Key validada com curl: HTTP 200, imagem gerada com sucesso
- Tier gratuito (Spore): 1.5 pollen/semana = ~7.500 imagens com Flux Schnell (0.0002/img)
- **Nao precisa pagar** — free tier cobre as 180 imagens com folga

## Etapa 1 — Atualizar SDK anthropic

```bash
source venv/bin/activate && pip install --upgrade anthropic
```

Sem mudanca de codigo — SDK e retrocompativel.

## Etapa 2 — Atualizar modelo LLM

**Arquivo**: `modules/llm_provider.py:65`

```python
# De:
model="claude-sonnet-4-5-20250929"

# Para:
model="claude-sonnet-4-6"
```

## Etapa 3 — Migrar image_provider.py para novo endpoint

**Arquivo**: `modules/image_provider.py`

### 3a. Renomear classe

`PollutionsImageProvider` → `PollinationsImageProvider`

Atualizar em todos os arquivos que referenciam:
- `modules/image_provider.py:13` (definicao)
- `main.py:20` (import)
- `main.py:302` (instanciacao)

### 3b. Adicionar suporte a API key

Novo parametro no `__init__`:

```python
def __init__(self, output_dir: str, max_retries: int = 3, quality: str = "high", api_key: str = ""):
```

Armazenar como `self.api_key`.

### 3c. Atualizar base_url

```python
# De:
self.base_url = "https://image.pollinations.ai/prompt"

# Para:
self.base_url = "https://gen.pollinations.ai/image"
```

### 3d. Atualizar `_build_image_url()`

Adicionar `model=flux` e `key={self.api_key}`:

```python
def _build_image_url(self, concept: str) -> str:
    encoded_concept = urllib.parse.quote(concept)
    params = {
        "model": "flux",
        "nologo": "true",
        "key": self.api_key,
    }
    if self.quality == "high":
        params.update({"width": "1024", "height": "1024"})
    elif self.quality == "medium":
        params.update({"width": "768", "height": "768"})
    else:
        params.update({"width": "512", "height": "512"})

    query_string = urllib.parse.urlencode(params)
    return f"{self.base_url}/{encoded_concept}?{query_string}"
```

## Etapa 4 — Atualizar config e main.py

### `config/settings.json`

Ja configurado (Etapa 0).

### `config/settings.example.json`

Adicionar campo:
```json
"pollinations_api_key": "YOUR_POLLINATIONS_API_KEY_HERE"
```

### `main.py:302`

Passar API key ao instanciar o provider:

```python
image_provider = PollinationsImageProvider(
    str(IMAGES_DIR),
    settings['max_retries_image'],
    settings['image_quality'],
    settings.get('pollinations_api_key', '')
)
```

## Etapa 5 — Pinar requirements.txt

Rodar `pip freeze` e pinar as versoes das 3 dependencias diretas.

## Etapa 6 — Testar com 2-3 palavras

1. Abrir Anki com AnkiConnect
2. `python main.py --word "Harsh"` (palavra nova da lista)
3. Verificar no Anki: 2 cards criados, imagem sem texto, conteudo correto
4. Se OK, rodar 1-2 palavras a mais para confirmar
5. Apos validacao, rodar batch completo

## Acceptance Criteria

- [x] Pollinations gera imagens via novo endpoint com API key
- [x] Imagens usam modelo FLUX (melhor qualidade que antes)
- [x] Claude usa modelo `claude-sonnet-4-6`
- [x] SDK anthropic atualizado para versao mais recente
- [x] Classe renomeada para `PollinationsImageProvider`
- [x] requirements.txt com versoes pinadas
- [x] Teste com 2-3 palavras bem-sucedido antes do batch

## Arquivos modificados

| Arquivo | Mudanca |
|---|---|
| `modules/image_provider.py` | Endpoint, API key, nome da classe, build_url |
| `modules/llm_provider.py` | Model ID (1 linha) |
| `main.py` | Import, instanciacao com API key, nome da classe |
| `config/settings.json` | Novo campo `pollinations_api_key` |
| `config/settings.example.json` | Novo campo `pollinations_api_key` |
| `requirements.txt` | Pinar versoes |
