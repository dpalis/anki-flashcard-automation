# Uso Rápido - Anki Automation

## 🚀 Como Usar

### Opção 1: Script Completo (recomendado)

```bash
./run.sh
```

**✨ Novo:** Palavras processadas com sucesso são **automaticamente removidas** de `palavras.txt`!

**Recursos:**
- ✅ Verifica ambiente virtual
- ✅ Verifica se Anki está rodando
- ✅ Instala dependências se necessário
- ✅ Valida configuração da API key
- ✅ Mensagens coloridas e informativas

**Exemplos:**
```bash
# Processar todas as palavras do arquivo
./run.sh

# Processar uma palavra específica
./run.sh --word "nimble"

# Resetar cache e reprocessar tudo
./run.sh --reset-cache
```

### Opção 2: Script Simples

```bash
./run-simple.sh
```

Versão minimalista que apenas ativa o venv e executa o main.py.

### Opção 3: Manual

```bash
source venv/bin/activate
python main.py
deactivate
```

## 📝 Preparação Inicial (primeira vez)

1. **Configure a API key:**
   ```bash
   nano config/settings.json
   # ou
   open -e config/settings.json
   ```
   Adicione sua chave da Anthropic.

2. **Edite a lista de palavras:**
   ```bash
   nano data/palavras.txt
   ```
   Uma palavra/expressão por linha.

3. **Abra o Anki:**
   - Certifique-se de que o AnkiConnect está instalado e ativo
   - O Anki precisa estar aberto durante a execução

## ❓ Problemas Comuns

**Erro: "Permission denied"**
```bash
chmod +x run.sh run-simple.sh
```

**Erro: "venv not found"**
```bash
python3 -m venv venv
pip install -r requirements.txt
```

**Erro: "AnkiConnect não responde"**
- Abra o Anki
- Verifique se o plugin AnkiConnect está instalado
- Reinicie o Anki se necessário

## 📊 Estrutura de Arquivos

```
├── run.sh              ← Use este (completo)
├── run-simple.sh       ← Ou este (simples)
├── main.py             ← Script principal
├── config/
│   ├── settings.json   ← Configure sua API key aqui
│   └── prompt_template.txt
├── data/
│   └── palavras.txt    ← Adicione palavras aqui
└── venv/               ← Ambiente virtual
```

## 🎯 Fluxo Típico

1. Adicionar palavras em `data/palavras.txt`
2. Abrir o Anki
3. Executar: `./run.sh`
4. Aguardar processamento
5. **Palavras processadas são removidas automaticamente!** ✨
6. Estudar os cards no Anki! 📚

## ✨ Auto-Remoção de Palavras

### Como funciona:

- ✅ **Sucesso** → Palavra removida de `palavras.txt` imediatamente
- ❌ **Falha** → Palavra **mantida** para nova tentativa
- 🔄 **Interrupção** → Apenas processadas são removidas

### Exemplos:

**Antes de executar:**
```
data/palavras.txt:
cellar
fateful
to boast
```

**Após `./run.sh` (2 sucessos, 1 falha):**
```
data/palavras.txt:
to boast    ← Falhou, mantida para retry
```

**Modo `--word` não remove:**
```bash
./run.sh --word "test"    # NÃO remove "test" do arquivo
```
