"""
Módulo para formatação HTML dos flashcards do Anki.
"""


class CardFormatter:
    """
    Formatador de conteúdo HTML para os cards do Anki.
    """

    def format_front_image(self, image_filename: str) -> str:
        """
        Formata a frente do card com apenas a imagem.

        Args:
            image_filename: Nome do arquivo de imagem

        Returns:
            HTML formatado para a frente do card
        """
        return f'<img src="{image_filename}" style="max-width: 100%; height: auto;">'

    def format_front_word(self, word: str) -> str:
        """
        Formata a frente do card com apenas a palavra.

        Args:
            word: Palavra em inglês

        Returns:
            HTML formatado para a frente do card
        """
        return f'<span style="color: #0000FF; font-weight: bold; font-size: 20px;">{word}</span>'

    def format_back(
        self,
        word: str,
        content: str,
        image_filename: str,
        include_image: bool = False
    ) -> str:
        """
        Formata o verso do card com palavra, conteúdo e opcionalmente imagem.

        Args:
            word: Palavra em inglês
            content: Conteúdo completo do flashcard
            image_filename: Nome do arquivo de imagem
            include_image: Se True, inclui a imagem no verso (Card 2: Palavra na frente)
                          Se False, não inclui imagem (Card 1: Imagem na frente)

        Returns:
            HTML formatado para o verso do card
        """
        # Formata a palavra em azul, bold, 20px
        word_html = f'<span style="color: #0000FF; font-weight: bold; font-size: 20px;">{word}</span>'

        # Converte quebras de linha do conteúdo para HTML
        content_html = self._format_content(content)

        # Monta o verso baseado no tipo de card
        back_parts = []

        if include_image:
            # Card 2: Palavra na frente → Verso tem: Imagem + Quebra simples + Conteúdo
            back_parts.append(f'<img src="{image_filename}" style="max-width: 100%; height: auto;">')
            back_parts.append('<br>')  # Uma quebra simples (não linha em branco)
            back_parts.append(content_html)
        else:
            # Card 1: Imagem na frente → Verso tem: Palavra + Linha em branco + Conteúdo
            back_parts.append(word_html)
            back_parts.append('<br><br>')  # Linha em branco após palavra (2 <br> = linha vazia)
            back_parts.append(content_html)

        return ''.join(back_parts)

    def _format_content(self, content: str) -> str:
        """
        Formata o conteúdo do flashcard, preservando quebras de linha e linhas em branco.

        Args:
            content: Conteúdo em texto plano

        Returns:
            HTML formatado
        """
        # Divide o conteúdo em linhas
        lines = content.split('\n')

        # Remove linhas vazias no início e fim
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        # Agrupa o conteúdo em blocos (separados por linhas vazias)
        blocks = []
        current_block = []

        for line in lines:
            line = line.strip()
            if line:
                # Linha com conteúdo
                escaped_line = self._escape_html(line)
                current_block.append(escaped_line)
            else:
                # Linha vazia → termina o bloco atual
                if current_block:
                    blocks.append('<br>'.join(current_block))
                    current_block = []

        # Adiciona o último bloco se houver
        if current_block:
            blocks.append('<br>'.join(current_block))

        # Junta blocos com linha em branco (<br><br>) entre eles
        return '<br><br>'.join(blocks)

    def _escape_html(self, text: str) -> str:
        """
        Escapa caracteres HTML especiais (mas mantém alguns símbolos úteis).

        Args:
            text: Texto para escapar

        Returns:
            Texto com caracteres escapados
        """
        # Não precisa escapar muito agressivamente, pois o Claude não gera HTML
        # Apenas protege contra < > que poderiam quebrar a formatação
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')

        return text

    def format_complete_card(
        self,
        word: str,
        content: str,
        image_filename: str,
        card_type: str = "image_to_word"
    ) -> tuple[str, str]:
        """
        Formata um card completo (frente e verso).

        Args:
            word: Palavra em inglês
            content: Conteúdo do flashcard
            image_filename: Nome do arquivo de imagem
            card_type: Tipo do card ("image_to_word" ou "word_to_image")

        Returns:
            Tupla (front_html, back_html)
        """
        if card_type == "image_to_word":
            # Card 1: Imagem → Palavra + Conteúdo
            front = self.format_front_image(image_filename)
            back = self.format_back(word, content, image_filename, include_image=False)
        else:
            # Card 2: Palavra → Imagem + Conteúdo
            front = self.format_front_word(word)
            back = self.format_back(word, content, image_filename, include_image=True)

        return front, back
