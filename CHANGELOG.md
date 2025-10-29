# Changelog - Anki Automation

## [27 Out 2025] - Auto-remoção de Palavras Processadas

### ✨ Nova Funcionalidade

**Auto-remoção de `data/palavras.txt`**

Agora, após processar uma palavra com sucesso, ela é **automaticamente removida** de `data/palavras.txt`.

#### Como Funciona:

1. **Processamento bem-sucedido** → Palavra removida imediatamente
2. **Processamento falhou** → Palavra **mantida** no arquivo para nova tentativa
3. **Modo `--word "palavra"`** → Palavra **não é removida** (pois foi digitada manualmente)

#### Benefícios:

✅ Não precisa editar manualmente o arquivo
✅ Palavras falhadas ficam automaticamente para retry
✅ Seguro contra interrupções (remove apenas após sucesso)
✅ Arquivo sempre sincronizado com o processamento

#### Exemplo de Uso:

```bash
# Arquivo inicial: data/palavras.txt
cellar
fateful
to boast
to heed
dismay

# Execute:
./run.sh

# Se "cellar" e "fateful" processarem com sucesso,
# o arquivo será atualizado automaticamente:
to boast
to heed
dismay

# Se "to boast" falhar, permanece no arquivo para retry
```

#### Casos Especiais:

**Palavra já processada (no cache):**
- É **pulada** e **não removida** do arquivo
- Para forçar reprocessamento: `./run.sh --reset-cache`

**Palavra específica (`--word`):**
- É processada normalmente
- **NÃO é removida** de `palavras.txt`
- Útil para testes sem alterar o arquivo

**Interrupção (Ctrl+C):**
- Apenas palavras já processadas são removidas
- Palavras não processadas permanecem no arquivo

---

## Arquivos Modificados

- `main.py`:
  - Adicionada função `remove_word_from_file()`
  - Modificado loop principal para remover após sucesso
  - Comportamento diferente para `--word` vs arquivo

---

## Retrocompatibilidade

✅ **Totalmente compatível** com versões anteriores
✅ Cache (`processadas.json`) funciona da mesma forma
✅ Argumentos CLI não mudaram

Se quiser **desabilitar** a remoção automática, basta usar sempre `--word "palavra"` ao invés de editar `palavras.txt`.
