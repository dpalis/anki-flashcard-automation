---
status: resolved
priority: p3
issue_id: "006"
tags: [code-review, quality, simplification]
---

# Simplificar quality mapping em _build_image_url

## Problem Statement

O bloco `if/elif/else` para quality dimensions em `_build_image_url()` repete a mesma estrutura 3 vezes. Poderia ser um dict lookup:

```python
sizes = {"high": "1024", "medium": "768"}
size = sizes.get(self.quality, "512")
```

Reduz 15 linhas para 10 e elimina repetição.

## Acceptance Criteria

- [ ] Quality mapping usa dict lookup em vez de if/elif/else
