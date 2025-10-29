"""
Módulo para integração com Claude API (Anthropic) para geração de conteúdo dos flashcards.
"""

import re
from typing import Dict, Optional
from pathlib import Path
import anthropic


class ClaudeProvider:
    """
    Provider para comunicação com Claude API e geração de conteúdo dos flashcards.
    """

    def __init__(self, api_key: str, prompt_template_path: str):
        """
        Inicializa o provider da Claude API.

        Args:
            api_key: Chave de API da Anthropic
            prompt_template_path: Caminho para o arquivo de template do prompt
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.prompt_template = self._load_prompt_template(prompt_template_path)

    def _load_prompt_template(self, template_path: str) -> str:
        """
        Carrega o template do prompt de um arquivo.

        Args:
            template_path: Caminho para o arquivo de template

        Returns:
            Conteúdo do template como string
        """
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Template de prompt não encontrado em: {template_path}")

    def generate_flashcard_content(self, word: str) -> Dict[str, str]:
        """
        Gera o conteúdo completo do flashcard para uma palavra usando Claude API.

        Args:
            word: Palavra ou expressão em inglês

        Returns:
            Dicionário com os campos extraídos do flashcard:
            - word: Palavra
            - content: Conteúdo completo formatado
            - visual_concept: Descrição do conceito visual para a imagem

        Raises:
            Exception: Se houver erro na API ou no parsing
        """
        # Monta o prompt completo
        full_prompt = f"{self.prompt_template}\n\n---\n\nPalavra: {word}"

        try:
            # Chama a API da Anthropic
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": full_prompt}
                ]
            )

            # Extrai o texto da resposta
            response_text = message.content[0].text

            # Parseia a resposta
            parsed_data = self._parse_flashcard_response(response_text, word)

            return parsed_data

        except anthropic.APIError as e:
            raise Exception(f"Erro na API da Anthropic: {str(e)}")
        except Exception as e:
            raise Exception(f"Erro ao gerar conteúdo para '{word}': {str(e)}")

    def _parse_flashcard_response(self, response: str, word: str) -> Dict[str, str]:
        """
        Faz o parsing da resposta da API para extrair os campos do flashcard.

        Args:
            response: Texto completo da resposta da API
            word: Palavra original (para fallback)

        Returns:
            Dicionário com word, content e visual_concept
        """
        # Extrai o conceito visual (última seção do prompt)
        visual_concept = self._extract_visual_concept(response)

        # Remove a seção CONCEITO VISUAL do conteúdo principal
        content = re.sub(
            r'\n*CONCEITO VISUAL[:\s]*\n.*',
            '',
            response,
            flags=re.IGNORECASE | re.DOTALL
        ).strip()

        # Remove a linha "Flashcard: palavra" completamente
        content = re.sub(r'^Flashcard:.*\n?', '', content, flags=re.MULTILINE).strip()

        # Remove markdown code blocks (```) se o LLM os incluiu
        content = content.replace('```', '').strip()

        # Remove a primeira linha (palavra duplicada)
        lines = content.split('\n')
        if lines:
            first_line = lines[0].strip()
            word_normalized = word.lower().strip()
            # Compara ignorando case e espaços, incluindo casos como "to deem"
            if first_line.lower() == word_normalized:
                lines = lines[1:]

        # Remove a última linha (familiaridade: Muito comum, Comum, etc)
        # A última linha geralmente está entre colchetes e contém palavras como "comum", "raro"
        if lines:
            last_line = lines[-1].strip()
            familiaridade_keywords = ['muito comum', 'comum', 'pouco comum', 'raro']
            if any(keyword in last_line.lower() for keyword in familiaridade_keywords):
                lines = lines[:-1]

        content = '\n'.join(lines).strip()

        return {
            'word': word,
            'content': content,
            'visual_concept': visual_concept
        }

    def _extract_visual_concept(self, response: str) -> str:
        """
        Extrai a descrição do conceito visual da resposta.

        Args:
            response: Texto completo da resposta

        Returns:
            Descrição do conceito visual ou string vazia se não encontrado
        """
        # Procura pela seção CONCEITO VISUAL
        match = re.search(
            r'CONCEITO VISUAL[:\s]*\n(.+)',
            response,
            flags=re.IGNORECASE | re.DOTALL
        )

        if match:
            concept = match.group(1).strip()
            return concept

        return ""

    def validate_response(self, response: Dict[str, str]) -> bool:
        """
        Valida se a resposta contém todos os campos necessários.

        Args:
            response: Dicionário retornado por generate_flashcard_content

        Returns:
            True se válido, False caso contrário
        """
        required_fields = ['word', 'content', 'visual_concept']

        for field in required_fields:
            if field not in response or not response[field]:
                return False

        # Valida que o conteúdo tem um tamanho mínimo razoável
        if len(response['content']) < 50:
            return False

        # Valida que o conceito visual existe
        if len(response['visual_concept']) < 20:
            return False

        return True
