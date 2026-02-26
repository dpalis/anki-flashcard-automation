---
status: resolved
priority: p3
issue_id: "010"
tags: [code-review, quality]
---

# Atualizar run.sh para verificar pollinations_api_key

## Problem Statement

O `run.sh` verifica a `anthropic_api_key` mas não verifica a nova `pollinations_api_key` adicionada neste PR. Inconsistência com os checks de startup.

## Acceptance Criteria

- [ ] run.sh verifica se pollinations_api_key está configurada
