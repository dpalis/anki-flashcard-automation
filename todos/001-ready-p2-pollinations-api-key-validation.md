---
status: resolved
priority: p2
issue_id: "001"
tags: [code-review, security, validation]
---

# Validar pollinations_api_key no startup

## Problem Statement

A `pollinations_api_key` não é validada no startup (diferente da `anthropic_api_key` que tem validação explícita em `load_settings()`). Quando a key está vazia, o sistema aceita silenciosamente e só falha no meio da execução com um HTTP genérico. Além disso, `key=` (string vazia) é incluído na URL mesmo quando não configurado.

## Findings

- **4 agentes convergiram** neste finding: Python reviewer, Security, Architecture, Agent-Native
- `main.py:306` — `settings.get('pollinations_api_key', '')` sem validação
- `image_provider.py:105-108` — `key` sempre incluído nos params, mesmo vazio
- Inconsistência com o tratamento da `anthropic_api_key` (linhas 52-57 de main.py)

## Proposed Solutions

### Opção A: Warning no startup + condicional na URL (Recomendada)
Adicionar warning em `main.py` quando a key estiver vazia. Em `_build_image_url()`, só incluir `key` nos params quando `self.api_key` for truthy.

**Pros:** Não quebra fluxo, mensagem clara, URL limpa
**Cons:** Nenhum
**Effort:** Small (5 linhas)

### Opção B: Exception no startup
Falhar com exceção se a key não estiver configurada, similar à Anthropic key.

**Pros:** Fail-fast total
**Cons:** Impede uso sem key (caso a API permita sem autenticação no futuro)
**Effort:** Small (3 linhas)

## Technical Details

**Affected files:**
- `main.py` (validação no startup)
- `modules/image_provider.py` (`_build_image_url()`)

## Acceptance Criteria

- [ ] Se `pollinations_api_key` estiver vazia/ausente, mensagem clara no startup
- [ ] URL não inclui `key=` quando a key está vazia
- [ ] Comportamento consistente com validação da `anthropic_api_key`
