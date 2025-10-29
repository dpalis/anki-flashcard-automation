"""
Módulo para comunicação com AnkiConnect e criação de cards no Anki.
"""

import json
from typing import List, Dict, Optional
import requests


class AnkiConnector:
    """
    Conector para comunicação com AnkiConnect e gerenciamento de cards.
    """

    def __init__(self, anki_url: str = "http://localhost:8765", card_model: str = "Básico"):
        """
        Inicializa o conector do Anki.

        Args:
            anki_url: URL do AnkiConnect (padrão: http://localhost:8765)
            card_model: Nome do modelo de card (padrão: "Básico")
        """
        self.anki_url = anki_url
        self.card_model = card_model
        self._field_names = None  # Cache dos nomes dos campos

    def check_connection(self) -> bool:
        """
        Verifica se o AnkiConnect está disponível.

        Returns:
            True se conectado, False caso contrário
        """
        try:
            response = self._invoke("version")
            return response is not None
        except Exception:
            return False

    def get_model_field_names(self) -> List[str]:
        """
        Obtém os nomes dos campos do modelo de card.

        Returns:
            Lista com os nomes dos campos (geralmente [campo_frente, campo_verso])
        """
        if self._field_names is None:
            try:
                self._field_names = self._invoke("modelFieldNames", modelName=self.card_model)
            except Exception:
                # Fallback para nomes padrão em português
                self._field_names = ["Frente", "Verso"]

        return self._field_names

    def create_deck_if_needed(self, deck_name: str) -> bool:
        """
        Cria um deck no Anki se ele não existir.

        Args:
            deck_name: Nome do deck

        Returns:
            True se o deck existe ou foi criado com sucesso
        """
        try:
            # Verifica se o deck existe
            decks = self._invoke("deckNames")
            if deck_name in decks:
                return True

            # Cria o deck
            self._invoke("createDeck", deck=deck_name)
            print(f"  ✓ Deck '{deck_name}' criado")
            return True

        except Exception as e:
            print(f"  ✗ Erro ao criar deck: {str(e)}")
            return False

    def add_media_file(self, file_path: str, filename: str) -> bool:
        """
        Adiciona um arquivo de mídia (imagem) ao Anki.

        Args:
            file_path: Caminho completo do arquivo
            filename: Nome do arquivo no Anki

        Returns:
            True se adicionado com sucesso
        """
        try:
            # Lê o arquivo em base64
            import base64
            with open(file_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')

            # Envia para o Anki
            self._invoke("storeMediaFile", filename=filename, data=data)
            return True

        except Exception as e:
            print(f"  ✗ Erro ao adicionar mídia: {str(e)}")
            return False

    def create_card(
        self,
        deck_name: str,
        front: str,
        back: str,
        tags: List[str]
    ) -> Optional[int]:
        """
        Cria um card no Anki.

        Args:
            deck_name: Nome do deck
            front: Conteúdo da frente do card (HTML)
            back: Conteúdo do verso do card (HTML)
            tags: Lista de tags

        Returns:
            ID do card criado ou None se falhar
        """
        try:
            # Obtém os nomes dos campos do modelo
            field_names = self.get_model_field_names()
            front_field = field_names[0] if len(field_names) > 0 else "Frente"
            back_field = field_names[1] if len(field_names) > 1 else "Verso"

            note = {
                "deckName": deck_name,
                "modelName": self.card_model,
                "fields": {
                    front_field: front,
                    back_field: back
                },
                "tags": tags,
                "options": {
                    "allowDuplicate": False
                }
            }

            note_id = self._invoke("addNote", note=note)
            return note_id

        except Exception as e:
            print(f"  ✗ Erro ao criar card: {str(e)}")
            return None

    def create_flashcards(
        self,
        word: str,
        content: str,
        image_filename: str,
        deck_name: str,
        tags: List[str]
    ) -> List[int]:
        """
        Cria os 2 flashcards (imagem→palavra e palavra→imagem) para uma palavra.

        Args:
            word: Palavra em inglês
            content: Conteúdo formatado do flashcard
            image_filename: Nome do arquivo de imagem no Anki
            deck_name: Nome do deck
            tags: Lista de tags

        Returns:
            Lista com os IDs dos cards criados
        """
        from .card_formatter import CardFormatter
        formatter = CardFormatter()

        card_ids = []

        # Card 1: Imagem → Palavra + Conteúdo
        front_image = formatter.format_front_image(image_filename)
        back_full = formatter.format_back(word, content, image_filename, include_image=False)

        card_id_1 = self.create_card(deck_name, front_image, back_full, tags)
        if card_id_1:
            card_ids.append(card_id_1)
            print(f"  ✓ Card 1 criado (Imagem → Palavra): ID {card_id_1}")

        # Card 2: Palavra → Imagem + Conteúdo
        front_word = formatter.format_front_word(word)
        back_with_image = formatter.format_back(word, content, image_filename, include_image=True)

        card_id_2 = self.create_card(deck_name, front_word, back_with_image, tags)
        if card_id_2:
            card_ids.append(card_id_2)
            print(f"  ✓ Card 2 criado (Palavra → Imagem): ID {card_id_2}")

        return card_ids

    def _invoke(self, action: str, **params) -> any:
        """
        Invoca uma ação no AnkiConnect.

        Args:
            action: Nome da ação
            **params: Parâmetros da ação

        Returns:
            Resultado da ação

        Raises:
            Exception: Se houver erro na comunicação
        """
        payload = {
            "action": action,
            "version": 6,
            "params": params
        }

        try:
            response = requests.post(self.anki_url, json=payload, timeout=10)
            response.raise_for_status()

            result = response.json()

            if len(result) != 2:
                raise Exception(f"Resposta inválida do AnkiConnect")

            if result.get("error") is not None:
                raise Exception(result["error"])

            return result.get("result")

        except requests.exceptions.ConnectionError:
            raise Exception(
                "Não foi possível conectar ao AnkiConnect. "
                "Certifique-se de que o Anki está aberto e o AnkiConnect está instalado."
            )
        except requests.exceptions.Timeout:
            raise Exception("Timeout ao comunicar com AnkiConnect")
        except Exception as e:
            raise Exception(f"Erro ao invocar AnkiConnect: {str(e)}")
