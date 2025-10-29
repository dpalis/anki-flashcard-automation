# Alias Opcional para Facilitar Ainda Mais

Se você quiser executar de **qualquer lugar** sem precisar estar no diretório do projeto, adicione este alias ao seu `~/.zshrc` ou `~/.bashrc`:

## Para Zsh (padrão no macOS)

```bash
# Abra o arquivo de configuração
nano ~/.zshrc

# Adicione esta linha no final:
alias anki-auto='cd "/Users/dpalis/Coding/Anki Automation" && ./run.sh'

# Salve (Ctrl+O, Enter, Ctrl+X) e recarregue:
source ~/.zshrc
```

## Para Bash

```bash
# Abra o arquivo de configuração
nano ~/.bashrc

# Adicione esta linha no final:
alias anki-auto='cd "/Users/dpalis/Coding/Anki Automation" && ./run.sh'

# Salve e recarregue:
source ~/.bashrc
```

## Uso Após Configurar

```bash
# De qualquer lugar no terminal:
anki-auto                    # Processa data/palavras.txt
anki-auto --word "nimble"    # Processa uma palavra
anki-auto --reset-cache      # Reseta cache
```

## Aliases Adicionais Úteis

```bash
# Adicione também:
alias anki-edit='nano "/Users/dpalis/Coding/Anki Automation/data/palavras.txt"'
alias anki-config='nano "/Users/dpalis/Coding/Anki Automation/config/settings.json"'
alias anki-cd='cd "/Users/dpalis/Coding/Anki Automation"'
```

**Uso:**
```bash
anki-edit      # Abre o editor para adicionar palavras
anki-auto      # Processa as palavras
```

Muito mais prático! 🚀
