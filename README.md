# Anki Automation - Gerador Automático de Flashcards

> **Estado atual da V2:** a entrada `./run.sh --json` aceita os perfis explícitos
> `english_vocabulary`, `spanish_travel` e `japanese_travel`. Cada perfil aponta
> para um deck já existente; a aplicação não cria decks. As instruções detalhadas
> abaixo descrevem a V1 e permanecem apenas como referência histórica.

## Entrada JSON da V2

`./run.sh --json` recebe pela entrada padrão exatamente `profile` (texto),
`items` (lista de textos) e `confirmed` (booleano opcional, padrão `false`):

```json
{"profile":"japanese_travel","items":["Onde fica a estação?"],"confirmed":false}
```

Com `confirmed:false`, nenhuma note é criada: a resposta tem status
`needs_confirmation` e a estimativa de armazenamento. Para executar, reenvie o
mesmo pedido trocando apenas o valor para `"confirmed":true`.

Os status são `needs_confirmation` (aguarda aprovação), `ok` (itens criados ou
ignorados por duplicidade) e `error` (parou no primeiro erro, sem retry ou
rollback automático). Deck e modelo Anthropic de cada perfil ficam em
[`config/settings.example.json`](config/settings.example.json).

No perfil japonês, frase e exemplos aparecem em romaji (alfabeto latino), com
explicações e traduções em português. A transcrição fonética em IPA aparece abaixo
da classificação e antes do áudio, como no inglês. A escrita japonesa fica somente
na geração de áudio, sem aparecer nos cards. Os demais perfis mantêm seu formato.

Sistema modular em Python para automatizar a criação de flashcards no Anki, com vocabulário em inglês, definições geradas por LLM (Claude API) e imagens conceituais.

## 📋 Pré-requisitos

### Software Necessário

1. **Python 3.1+**
   - Verifique a versão: `python --version`

2. **Anki** (aplicativo desktop)
   - Download: https://apps.ankiweb.net/

3. **Plugin AnkiConnect**
   - Instale através do Anki: Tools → Add-ons → Get Add-ons
   - Código: `2055492159`
   - Reinicie o Anki após instalar

4. **API Key da Anthropic (Claude)**
   - Obtenha em: https://console.anthropic.com/
   - Plano pago necessário para usar a API

## 🚀 Instalação

### 1. Clone ou baixe o projeto

```bash
cd "Anki Automation"
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure a API Key

Edite o arquivo `config/settings.json` e adicione sua chave de API:

```json
{
  "anthropic_api_key": "sk-ant-api03-...",
  "deck_name": "Inglês",
  "default_tags": ["english"],
  "image_provider": "pollinations",
  "anki_url": "http://localhost:8765",
  "max_retries_image": 3,
  "image_quality": "high"
}
```

### 4. Verifique a instalação do AnkiConnect

1. Abra o Anki
2. Vá em Tools → Add-ons
3. Verifique se "AnkiConnect" está listado e habilitado
4. O AnkiConnect deve estar rodando em `http://localhost:8765`

## 📝 Como Usar

### Modo 1: Processar lista de palavras

1. Edite o arquivo `data/palavras.txt` e adicione as palavras (uma por linha):

```
nimble
take over
serendipity
eloquent
```

2. Execute o script:

```bash
python main.py
```

### Modo 2: Processar uma palavra específica

```bash
python main.py --word "serendipity"
```

### Modo 3: Resetar cache e reprocessar tudo

```bash
python main.py --reset-cache
```

## 🏗️ Estrutura do Projeto

```
anki-automation/
├── modules/
│   ├── __init__.py
│   ├── llm_provider.py       # Integração com Claude API
│   ├── image_provider.py     # Geração de imagens (Pollinations.ai)
│   ├── anki_connector.py     # Comunicação com AnkiConnect
│   └── card_formatter.py     # Formatação HTML dos cards
├── config/
│   ├── settings.json         # Configurações (API keys, deck name, etc)
│   └── prompt_template.txt   # Template do prompt para o LLM
├── data/
│   ├── palavras.txt          # Input: lista de palavras (uma por linha)
│   ├── processadas.json      # Cache de palavras já processadas
│   └── images/               # Imagens geradas
├── main.py                   # Script principal
├── requirements.txt          # Dependências Python
├── README.md                 # Este arquivo
└── .gitignore                # Arquivos ignorados pelo git
```

## 🎴 Como Funciona

Para cada palavra no arquivo `data/palavras.txt`, o sistema:

1. **Gera definições** usando Claude API (Anthropic)
   - Múltiplos significados ordenados por frequência
   - Exemplos práticos de uso
   - Pronúncia (IPA), tradução e classificação gramatical
   - Descrição de conceito visual

2. **Gera imagem conceitual** usando Pollinations.ai
   - Baseada no conceito visual descrito pelo Claude
   - **Sem texto, números ou símbolos**
   - Até 3 tentativas automáticas

3. **Cria 2 flashcards no Anki**:
   - **Card 1**: Imagem → Palavra + Definições
   - **Card 2**: Palavra → Imagem + Definições

4. **Salva no cache** para evitar reprocessamento

## ⚙️ Configurações Avançadas

### Personalizar deck e tags

Edite `config/settings.json`:

```json
{
  "deck_name": "Vocabulário Avançado",
  "default_tags": ["english", "vocabulary", "advanced"]
}
```

### Ajustar qualidade das imagens

```json
{
  "image_quality": "high"  // Opções: high, medium, low
}
```

### Modificar o prompt do LLM

Edite `config/prompt_template.txt` para personalizar como as definições são geradas.

## 🔧 Troubleshooting

### Erro: "Não foi possível conectar ao AnkiConnect"

**Solução:**
1. Verifique se o Anki está aberto
2. Verifique se o AnkiConnect está instalado: Tools → Add-ons
3. Reinicie o Anki
4. Verifique se nenhum firewall está bloqueando a porta 8765

### Erro: "API key da Anthropic não configurada"

**Solução:**
1. Abra `config/settings.json`
2. Adicione sua API key no campo `anthropic_api_key`
3. Certifique-se de que a chave está entre aspas

### Erro: "Template de prompt não encontrado"

**Solução:**
1. Verifique se o arquivo `config/prompt_template.txt` existe
2. Não renomeie ou mova este arquivo

### Imagens com texto/números

**Solução:**
- O sistema tenta automaticamente até 3 vezes
- Se persistir, o conceito visual pode precisar ser ajustado no prompt
- Edite `config/prompt_template.txt` para reforçar a regra de "zero texto"

### Palavras duplicadas

**Solução:**
- Palavras já processadas são automaticamente puladas
- Use `--reset-cache` para reprocessar tudo
- O cache fica em `data/processadas.json`

## 📊 Logs e Progresso

Durante a execução, o script exibe:

```
[1/10] 📝 Processando: nimble
🤖 Gerando conteúdo com Claude API...
  ✓ Conteúdo gerado com sucesso
🎨 Gerando imagem conceitual...
  📸 Gerando imagem (tentativa 1/3)...
  ✓ Imagem salva
🃏 Criando flashcards no Anki...
  ✓ Card 1 criado (Imagem → Palavra): ID 1234567890
  ✓ Card 2 criado (Palavra → Imagem): ID 1234567891
✅ Palavra 'nimble' processada com sucesso!
```

## 🎯 Boas Práticas

1. **Comece com poucas palavras** para testar o sistema
2. **Revise os cards gerados** no Anki antes de estudar
3. **Mantenha backup** do arquivo `data/palavras.txt`
4. **Não compartilhe** o arquivo `config/settings.json` (contém API key)
5. **Use o cache** para evitar custos desnecessários com a API

## 💰 Custos Estimados

- **Pollinations.ai**: Gratuito
- **AnkiConnect**: Gratuito
- **Claude API**: Pago (~$0.003 por palavra)*

\* Estimativa baseada no modelo Claude 3.5 Sonnet. Verifique preços atuais em https://www.anthropic.com/pricing

## 📚 Exemplos de Cards Gerados

### Exemplo 1: "nimble"

**Frente (Card 1)**: [Imagem de pessoa pulando ágilmente]

**Verso**:
> **nimble**
>
> It means quick and light in movement or action, showing agility and dexterity.
> It also means quick to understand or respond mentally, demonstrating mental agility.
>
> Ex.: The nimble dancer moved gracefully across the stage.
> Ex.: She has a nimble mind that grasps concepts quickly.
>
> Ágil, ligeiro, esperto
> Adjective
> /ˈnɪmbəl/
> Comum

### Exemplo 2: "take over"

**Frente (Card 2)**: **take over**

**Verso**:
> [Imagem conceitual de transição/controle]
>
> **take over**
>
> It means to assume control or responsibility for something...

## 🤝 Contribuindo

Sugestões de melhorias futuras:

- [ ] Suporte a outros idiomas
- [ ] Integração com outras APIs de imagem
- [ ] Interface gráfica (GUI)
- [ ] Geração de áudio com pronúncia
- [ ] Suporte a frases idiomáticas
- [ ] Exportação para CSV/JSON
- [ ] Modo batch com processamento paralelo

## 📄 Licença

Este projeto é fornecido "como está" para uso pessoal e educacional.

## 🆘 Suporte

Para problemas, dúvidas ou sugestões:
1. Verifique a seção de Troubleshooting
2. Revise a documentação das APIs utilizadas
3. Consulte a documentação do AnkiConnect: https://foosoft.net/projects/anki-connect/

---

**Desenvolvido com ❤️ para estudantes de inglês**
