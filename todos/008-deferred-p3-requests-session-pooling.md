---
status: resolved
priority: p3
issue_id: "008"
tags: [code-review, performance]
---

# Usar requests.Session() para connection pooling

## Problem Statement

Tanto `image_provider.py` quanto `anki_connector.py` usam `requests.get()`/`requests.post()` diretamente, criando nova conexão TCP (e TLS handshake) por request. Para 180 palavras, são ~180 TLS handshakes desnecessários ao Pollinations (100-300ms cada = 18-54s extras).

## Acceptance Criteria

- [ ] `requests.Session()` usado em image_provider.py
- [ ] `requests.Session()` usado em anki_connector.py
