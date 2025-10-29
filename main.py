#!/usr/bin/env python3
"""
Script principal para automação de criação de flashcards no Anki.

Uso:
    python main.py                    # Processa palavras.txt
    python main.py --word "nimble"    # Processa uma palavra específica
    python main.py --reset-cache      # Limpa cache e reprocessa tudo
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from modules.llm_provider import ClaudeProvider
from modules.image_provider import PollutionsImageProvider
from modules.anki_connector import AnkiConnector
from modules.card_formatter import CardFormatter


# Caminhos dos arquivos
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
PROMPT_TEMPLATE_FILE = CONFIG_DIR / "prompt_template.txt"
WORDS_FILE = DATA_DIR / "palavras.txt"
CACHE_FILE = DATA_DIR / "processadas.json"
IMAGES_DIR = DATA_DIR / "images"


def load_settings() -> Dict:
    """
    Carrega as configurações do arquivo settings.json.

    Returns:
        Dicionário com as configurações

    Raises:
        Exception: Se o arquivo não existir ou for inválido
    """
    if not SETTINGS_FILE.exists():
        raise Exception(f"Arquivo de configurações não encontrado: {SETTINGS_FILE}")

    with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
        settings = json.load(f)

    # Valida API key
    if not settings.get('anthropic_api_key'):
        raise Exception(
            "API key da Anthropic não configurada. "
            f"Por favor, configure 'anthropic_api_key' em {SETTINGS_FILE}"
        )

    return settings


def load_cache() -> Dict:
    """
    Carrega o cache de palavras processadas.

    Returns:
        Dicionário com palavras processadas
    """
    if not CACHE_FILE.exists():
        return {}

    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache: Dict) -> None:
    """
    Salva o cache de palavras processadas.

    Args:
        cache: Dicionário com palavras processadas
    """
    # Garante que o diretório existe
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def is_processed(word: str, cache: Dict) -> bool:
    """
    Verifica se uma palavra já foi processada.

    Args:
        word: Palavra a verificar
        cache: Cache de palavras processadas

    Returns:
        True se já foi processada
    """
    return word.lower() in cache


def process_word(
    word: str,
    llm_provider: ClaudeProvider,
    image_provider: PollutionsImageProvider,
    anki_connector: AnkiConnector,
    deck_name: str,
    tags: List[str],
    cache: Dict
) -> bool:
    """
    Processa uma palavra: gera conteúdo, imagem e cria cards no Anki.

    Args:
        word: Palavra a processar
        llm_provider: Provider do LLM
        image_provider: Provider de imagens
        anki_connector: Conector do Anki
        deck_name: Nome do deck
        tags: Tags para os cards
        cache: Cache de palavras processadas

    Returns:
        True se processado com sucesso
    """
    print(f"\n{'='*60}")
    print(f"📝 Processando: {word}")
    print(f"{'='*60}")

    try:
        # 1. Gera conteúdo usando Claude API
        print("🤖 Gerando conteúdo com Claude API...")
        flashcard_data = llm_provider.generate_flashcard_content(word)

        if not llm_provider.validate_response(flashcard_data):
            print("  ✗ Resposta inválida do LLM")
            return False

        print("  ✓ Conteúdo gerado com sucesso")

        # 2. Gera imagem
        print("🎨 Gerando imagem conceitual...")
        image_path = image_provider.generate_image(
            word,
            flashcard_data['visual_concept']
        )

        if not image_path:
            print("  ✗ Falha ao gerar imagem")
            return False

        # 3. Adiciona imagem ao Anki
        print("📤 Enviando imagem para o Anki...")
        image_filename = os.path.basename(image_path)
        if not anki_connector.add_media_file(image_path, image_filename):
            print("  ✗ Falha ao adicionar imagem ao Anki")
            return False

        print("  ✓ Imagem adicionada ao Anki")

        # 4. Cria os 2 cards no Anki
        print("🃏 Criando flashcards no Anki...")
        card_ids = anki_connector.create_flashcards(
            word,
            flashcard_data['content'],
            image_filename,
            deck_name,
            tags
        )

        if len(card_ids) != 2:
            print("  ⚠ Nem todos os cards foram criados")
            return False

        # 5. Atualiza o cache
        cache[word.lower()] = {
            "timestamp": datetime.now().isoformat(),
            "card_ids": card_ids
        }
        save_cache(cache)

        print(f"\n✅ Palavra '{word}' processada com sucesso!")
        return True

    except Exception as e:
        print(f"\n❌ Erro ao processar '{word}': {str(e)}")
        return False


def load_words_from_file() -> List[str]:
    """
    Carrega a lista de palavras do arquivo palavras.txt.

    Returns:
        Lista de palavras

    Raises:
        Exception: Se o arquivo não existir
    """
    if not WORDS_FILE.exists():
        raise Exception(f"Arquivo de palavras não encontrado: {WORDS_FILE}")

    with open(WORDS_FILE, 'r', encoding='utf-8') as f:
        words = [line.strip() for line in f if line.strip()]

    return words


def remove_word_from_file(word: str) -> None:
    """
    Remove uma palavra do arquivo palavras.txt após processamento bem-sucedido.

    Args:
        word: Palavra a ser removida
    """
    try:
        # Lê todas as palavras atuais
        if not WORDS_FILE.exists():
            return

        with open(WORDS_FILE, 'r', encoding='utf-8') as f:
            words = [line.strip() for line in f if line.strip()]

        # Remove a palavra processada (case-insensitive)
        words_updated = [w for w in words if w.lower() != word.lower()]

        # Reescreve o arquivo com as palavras restantes
        with open(WORDS_FILE, 'w', encoding='utf-8') as f:
            for w in words_updated:
                f.write(f"{w}\n")

        print(f"  ✓ Palavra '{word}' removida de {WORDS_FILE.name}")

    except Exception as e:
        print(f"  ⚠ Erro ao remover palavra do arquivo: {str(e)}")
        # Não falhamos o processo se isso der erro - apenas avisa


def main():
    """
    Função principal do script.
    """
    # Parser de argumentos
    parser = argparse.ArgumentParser(
        description="Automatiza a criação de flashcards no Anki com vocabulário em inglês"
    )
    parser.add_argument(
        '--word',
        type=str,
        help='Processa uma palavra específica'
    )
    parser.add_argument(
        '--reset-cache',
        action='store_true',
        help='Limpa o cache e reprocessa todas as palavras'
    )

    args = parser.parse_args()

    print("╔══════════════════════════════════════════════════════════╗")
    print("║          ANKI AUTOMATION - Gerador de Flashcards        ║")
    print("╚══════════════════════════════════════════════════════════╝")

    try:
        # 1. Carrega configurações
        print("\n📋 Carregando configurações...")
        settings = load_settings()
        print("  ✓ Configurações carregadas")

        # 2. Verifica conexão com Anki
        print("\n🔗 Verificando conexão com AnkiConnect...")
        anki_connector = AnkiConnector(
            settings['anki_url'],
            settings.get('card_model', 'Básico')
        )

        if not anki_connector.check_connection():
            raise Exception(
                "Não foi possível conectar ao AnkiConnect. "
                "Certifique-se de que o Anki está aberto com o plugin AnkiConnect instalado."
            )

        print("  ✓ Conectado ao Anki")

        # 3. Cria deck se necessário
        deck_name = settings['deck_name']
        print(f"\n📚 Verificando deck '{deck_name}'...")
        anki_connector.create_deck_if_needed(deck_name)

        # 4. Inicializa providers
        print("\n⚙️  Inicializando providers...")
        llm_provider = ClaudeProvider(
            settings['anthropic_api_key'],
            str(PROMPT_TEMPLATE_FILE)
        )

        image_provider = PollutionsImageProvider(
            str(IMAGES_DIR),
            settings['max_retries_image'],
            settings['image_quality']
        )

        print("  ✓ Providers inicializados")

        # 5. Carrega ou reseta cache
        if args.reset_cache:
            print("\n🗑️  Resetando cache...")
            cache = {}
            save_cache(cache)
        else:
            cache = load_cache()
            if cache:
                print(f"\n📦 Cache carregado: {len(cache)} palavra(s) já processada(s)")

        # 6. Define palavras a processar
        if args.word:
            # Processa palavra específica
            words = [args.word]
        else:
            # Processa arquivo
            words = load_words_from_file()

        print(f"\n📝 Total de palavras a processar: {len(words)}")

        # 7. Processa cada palavra
        success_count = 0
        skip_count = 0
        fail_count = 0

        for i, word in enumerate(words, 1):
            # Verifica se já foi processada
            if is_processed(word, cache) and not args.reset_cache:
                print(f"\n[{i}/{len(words)}] ⏭️  '{word}' já foi processada (pulando)")
                skip_count += 1
                continue

            # Processa a palavra
            print(f"\n[{i}/{len(words)}]")
            if process_word(
                word,
                llm_provider,
                image_provider,
                anki_connector,
                deck_name,
                settings['default_tags'],
                cache
            ):
                success_count += 1

                # Remove do arquivo palavras.txt se foi processada do arquivo (não --word)
                if not args.word:
                    remove_word_from_file(word)
            else:
                fail_count += 1

        # 8. Resume final
        print("\n" + "="*60)
        print("📊 RESUMO FINAL")
        print("="*60)
        print(f"✅ Processadas com sucesso: {success_count}")
        print(f"⏭️  Puladas (já existentes): {skip_count}")
        print(f"❌ Falharam: {fail_count}")
        print(f"📝 Total: {len(words)}")
        print("="*60)

        if fail_count > 0:
            print("\n⚠️  Algumas palavras falharam. Revise os erros acima.")
            sys.exit(1)
        else:
            print("\n🎉 Processamento concluído com sucesso!")
            sys.exit(0)

    except KeyboardInterrupt:
        print("\n\n⚠️  Processamento interrompido pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERRO FATAL: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
