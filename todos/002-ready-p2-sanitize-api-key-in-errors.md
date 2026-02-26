---
status: resolved
priority: p2
issue_id: "002"
tags: [code-review, security]
---

# Sanitizar API key em mensagens de erro

## Problem Statement

Quando `requests.get()` falha, a exceção do `requests` frequentemente inclui a URL completa na mensagem de erro. Como a URL agora contém a API key como query parameter, um erro de rede pode printar a key no terminal. Se alguém colar o output num issue do GitHub, a key vaza.

## Findings

- `modules/image_provider.py:83` — `print(f"... {str(e)}")` sem sanitização
- Encontrado pelo Security Sentinel

## Proposed Solutions

### Opção A: Sanitizar na mensagem de erro (Recomendada)

```python
except requests.exceptions.RequestException as e:
    error_msg = str(e).replace(self.api_key, '***') if self.api_key else str(e)
    print(f"  ✗ Erro ao baixar imagem (tentativa {attempt}): {error_msg}")
```

**Pros:** Simples, eficaz, defensivo
**Cons:** Nenhum
**Effort:** Small (2 linhas)

## Technical Details

**Affected files:**
- `modules/image_provider.py` (bloco except na linha 82-83)

## Acceptance Criteria

- [ ] Mensagens de erro nunca contêm a API key em texto claro
- [ ] Erro continua informativo (mostra tipo de falha, não a URL completa)
