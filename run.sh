#!/bin/bash

# Script wrapper para executar o Anki Automation
# Uso: ./run.sh [argumentos do main.py]
# Exemplos:
#   ./run.sh
#   ./run.sh --word "nimble"
#   ./run.sh --reset-cache

# Define o diretório do script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cores para output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "  Anki Automation - Wrapper Script"
echo "================================================"

# 1. Verifica se o ambiente virtual existe
if [ ! -d "venv" ]; then
    echo -e "${RED}❌ Erro: Ambiente virtual não encontrado!${NC}"
    echo "Execute primeiro: python3 -m venv venv"
    exit 1
fi

# 2. Verifica se o Anki está rodando (opcional, mas útil)
if ! curl -s http://localhost:8765 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Aviso: AnkiConnect não está respondendo${NC}"
    echo "   Certifique-se de que o Anki está aberto"
    echo ""
fi

# 3. Ativa o ambiente virtual
echo -e "${GREEN}✓${NC} Ativando ambiente virtual..."
source venv/bin/activate

# 4. Verifica se as dependências estão instaladas
if ! python -c "import anthropic" 2>/dev/null; then
    echo -e "${YELLOW}⚠️  Dependências não instaladas. Instalando...${NC}"
    pip install -r requirements.txt
fi

# 5. Verifica se a API key está configurada
if grep -q '"anthropic_api_key": ""' config/settings.json 2>/dev/null; then
    echo -e "${RED}❌ Erro: API key da Anthropic não configurada!${NC}"
    echo "   Edite config/settings.json e adicione sua chave"
    exit 1
fi

# 6. Executa o main.py com todos os argumentos passados
echo -e "${GREEN}✓${NC} Executando Anki Automation..."
echo ""
python main.py "$@"

# 7. Captura o código de saída
EXIT_CODE=$?

# 8. Desativa o ambiente virtual
deactivate

# 9. Mensagem final
echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ Concluído com sucesso!${NC}"
else
    echo -e "${RED}✗ Execução falhou (código: $EXIT_CODE)${NC}"
fi

exit $EXIT_CODE
