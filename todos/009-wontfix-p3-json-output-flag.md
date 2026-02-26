---
status: wont_fix
priority: p3
issue_id: "009"
tags: [code-review, agent-native]
---

# Adicionar flag --json para output estruturado

## Problem Statement

O output atual usa emojis e texto em português, não parseável por agentes/automação. Uma flag `--json` emitiria output estruturado como `{"success": 5, "skipped": 3, "failed": 2}`.

## Acceptance Criteria

- [ ] Flag `--json` disponível no CLI
- [ ] Output JSON inclui contagens e lista de palavras que falharam
