---
status: resolved
priority: p3
issue_id: "007"
tags: [code-review, architecture]
---

# Tornar modelo LLM configurável via settings.json

## Problem Statement

O modelo está hardcoded como `"claude-sonnet-4-6"` em `llm_provider.py:65`. Já foi trocado uma vez (de `claude-sonnet-4-5-20250929`). Provavelmente será trocado novamente. Extrair para `settings.json` eliminaria a necessidade de editar código-fonte.

## Acceptance Criteria

- [ ] Campo `llm_model` em settings.json
- [ ] ClaudeProvider recebe modelo via construtor
- [ ] Default sensato quando campo não presente
