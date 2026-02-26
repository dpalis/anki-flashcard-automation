---
status: wont_fix
priority: p2
issue_id: "003"
tags: [code-review, performance]
---

# Benchmark latência do modelo FLUX antes do batch

## Problem Statement

O endpoint antigo usava o modelo default do Pollinations. O novo endpoint força `model=flux`, que é um modelo de difusão de maior qualidade mas tipicamente mais lento. Para 180 palavras, a diferença pode ser de 10-30 minutos extras no total do batch.

## Findings

- `modules/image_provider.py:106` — `"model": "flux"` hardcoded
- Encontrado pelo Performance Oracle
- Timeout de 30s por request (`image_provider.py:72`) com retry até 3x = potencial de 96s por palavra no pior caso

## Proposed Solutions

### Opção A: Benchmark manual e decidir (Recomendada)
Rodar 3-5 palavras e medir o tempo por imagem. Se aceitável, seguir. Se não, considerar modelo alternativo (ex: `flux-schnell` que é mais rápido).

**Pros:** Decisão informada, zero código
**Cons:** Requer teste manual
**Effort:** Small (5 min de teste)

### Opção B: Tornar modelo configurável em settings.json
Adicionar campo `pollinations_model` em settings para poder trocar sem editar código.

**Pros:** Flexibilidade futura
**Cons:** Mais um campo de config
**Effort:** Small (5 linhas)

## Acceptance Criteria

- [ ] Latência por imagem medida com o endpoint atual
- [ ] Decisão documentada sobre modelo (manter flux ou trocar)
