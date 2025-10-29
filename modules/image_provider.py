"""
Módulo para geração de imagens conceituais usando Pollinations.ai.
"""

import os
import time
import urllib.parse
from typing import Optional
from pathlib import Path
import requests


class PollutionsImageProvider:
    """
    Provider para geração de imagens usando a API do Pollinations.ai.
    """

    def __init__(self, output_dir: str, max_retries: int = 3, quality: str = "high"):
        """
        Inicializa o provider de imagens.

        Args:
            output_dir: Diretório onde as imagens serão salvas
            max_retries: Número máximo de tentativas para gerar imagem
            quality: Qualidade da imagem (high, medium, low)
        """
        self.output_dir = Path(output_dir)
        self.max_retries = max_retries
        self.quality = quality
        self.base_url = "https://image.pollinations.ai/prompt"

        # Cria o diretório se não existir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_image(self, word: str, visual_concept: str) -> Optional[str]:
        """
        Gera uma imagem baseada no conceito visual e salva localmente.

        Args:
            word: Palavra (usada para nomear o arquivo)
            visual_concept: Descrição do conceito visual para gerar a imagem

        Returns:
            Caminho completo da imagem salva ou None se falhar

        Raises:
            Exception: Se todas as tentativas falharem
        """
        # Limpa o nome da palavra para usar como filename
        safe_word = self._sanitize_filename(word)
        output_path = self.output_dir / f"{safe_word}.jpg"

        # Se já existe, retorna o caminho
        if output_path.exists():
            print(f"  ⚠ Imagem já existe: {output_path}")
            return str(output_path)

        # Tenta gerar a imagem com retries
        for attempt in range(1, self.max_retries + 1):
            try:
                print(f"  📸 Gerando imagem (tentativa {attempt}/{self.max_retries})...")

                # Adiciona instruções extras para evitar texto
                enhanced_concept = self._enhance_concept_for_no_text(visual_concept)

                # Gera URL da imagem
                image_url = self._build_image_url(enhanced_concept)

                # Faz o download da imagem
                response = requests.get(image_url, timeout=30)
                response.raise_for_status()

                # Salva a imagem
                with open(output_path, 'wb') as f:
                    f.write(response.content)

                print(f"  ✓ Imagem salva: {output_path}")
                return str(output_path)

            except requests.exceptions.RequestException as e:
                print(f"  ✗ Erro ao baixar imagem (tentativa {attempt}): {str(e)}")

                if attempt < self.max_retries:
                    # Aguarda antes de tentar novamente
                    time.sleep(2)
                else:
                    raise Exception(f"Falha ao gerar imagem após {self.max_retries} tentativas")

        return None

    def _build_image_url(self, concept: str) -> str:
        """
        Constrói a URL da API do Pollinations.ai.

        Args:
            concept: Conceito visual para gerar

        Returns:
            URL completa para requisição
        """
        # Faz URL encoding do conceito
        encoded_concept = urllib.parse.quote(concept)

        # Constrói a URL com parâmetros de qualidade
        url = f"{self.base_url}/{encoded_concept}"

        # Adiciona parâmetros adicionais se necessário
        if self.quality == "high":
            url += "?width=1024&height=1024&nologo=true"
        elif self.quality == "medium":
            url += "?width=768&height=768&nologo=true"
        else:
            url += "?width=512&height=512&nologo=true"

        return url

    def _enhance_concept_for_no_text(self, concept: str) -> str:
        """
        Adiciona instruções explícitas ao conceito para evitar texto nas imagens.

        Args:
            concept: Conceito visual original

        Returns:
            Conceito aprimorado com instruções anti-texto
        """
        no_text_instructions = (
            "IMPORTANT: No text, no words, no letters, no numbers, no symbols, "
            "no signs, no labels, no typography of any kind. Pure visual concept only. "
        )

        return f"{no_text_instructions}{concept}"

    def _sanitize_filename(self, word: str) -> str:
        """
        Sanitiza o nome da palavra para usar como filename.

        Args:
            word: Palavra original

        Returns:
            Nome de arquivo seguro
        """
        # Remove caracteres especiais e espaços
        safe = word.lower().strip()
        safe = safe.replace(" ", "_")
        safe = "".join(c for c in safe if c.isalnum() or c in ['_', '-'])

        return safe

    def image_exists(self, word: str) -> bool:
        """
        Verifica se a imagem para uma palavra já existe.

        Args:
            word: Palavra a verificar

        Returns:
            True se a imagem existe, False caso contrário
        """
        safe_word = self._sanitize_filename(word)
        image_path = self.output_dir / f"{safe_word}.jpg"

        return image_path.exists()

    def get_image_path(self, word: str) -> str:
        """
        Retorna o caminho completo da imagem para uma palavra.

        Args:
            word: Palavra

        Returns:
            Caminho completo da imagem
        """
        safe_word = self._sanitize_filename(word)
        return str(self.output_dir / f"{safe_word}.jpg")
