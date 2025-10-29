# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Anki Automation is a modular Python system that automates the creation of Anki flashcards for English vocabulary learning. It integrates Claude API (Anthropic) for content generation, Pollinations.ai for conceptual images, and AnkiConnect for card creation.

**Key Feature**: Creates 2 cards per word (image→word and word→image) with rich content including definitions, examples, translations, and zero-text images.

## Architecture

### Modular Design

The project follows a clean modular architecture with clear separation of concerns:

```
modules/
├── llm_provider.py       - Claude API integration and response parsing
├── image_provider.py     - Image generation via Pollinations.ai
├── anki_connector.py     - AnkiConnect communication and card creation
└── card_formatter.py     - HTML formatting for Anki cards
```

### Data Flow

1. **Input**: `data/palavras.txt` (word list, one per line)
2. **LLM Processing**: `llm_provider.py` generates content using Claude API
3. **Image Generation**: `image_provider.py` creates conceptual images
4. **Card Creation**: `anki_connector.py` + `card_formatter.py` create 2 Anki cards
5. **Cache**: `data/processadas.json` tracks processed words

### Key Design Decisions

- **Two-card approach**: Bidirectional learning (image→word and word→image)
- **Zero-text images**: Critical constraint enforced via prompt engineering and retry logic
- **Cache system**: Prevents reprocessing and unnecessary API costs
- **Fail-forward**: If one word fails, processing continues with others
- **Type hints**: All functions use Python type hints for clarity
- **Portuguese comments**: Code comments are in Portuguese per project convention

## Commands

### Running the Application

```bash
# Process all words in data/palavras.txt
python main.py

# Process a single word
python main.py --word "nimble"

# Reset cache and reprocess everything
python main.py --reset-cache
```

### Testing Individual Modules

```python
# Test LLM provider
from modules.llm_provider import ClaudeProvider
provider = ClaudeProvider("api_key", "config/prompt_template.txt")
result = provider.generate_flashcard_content("serendipity")

# Test image provider
from modules.image_provider import PollutionsImageProvider
image_provider = PollutionsImageProvider("data/images")
image_path = image_provider.generate_image("word", "visual concept")

# Test Anki connector
from modules.anki_connector import AnkiConnector
anki = AnkiConnector()
connected = anki.check_connection()
```

### Dependencies

Install all dependencies:
```bash
pip install -r requirements.txt
```

Individual packages:
- `anthropic` - Claude API client
- `requests` - HTTP requests for Pollinations.ai
- `beautifulsoup4` - HTML parsing (future use)
- `ankiconnect` - Anki integration (not a package, uses AnkiConnect plugin)

## Configuration Files

### `config/settings.json`
Main configuration file. **Never commit with real API keys**.

Required fields:
- `anthropic_api_key` - Claude API key (user must provide)
- `deck_name` - Target Anki deck (default: "Inglês")
- `default_tags` - Tags for cards (default: ["english"])
- `anki_url` - AnkiConnect URL (default: http://localhost:8765)
- `max_retries_image` - Max attempts for image generation (default: 3)
- `image_quality` - high/medium/low (affects image dimensions)

### `config/prompt_template.txt`
LLM prompt template. Highly engineered prompt with:
- Strict ordering by frequency of meaning
- Zero-text image policy enforcement
- Specific formatting rules for parsing
- Visual concept generation instructions

**Critical**: If modifying prompt, ensure it still produces parseable output with:
- "CONCEITO VISUAL" section at end
- "Flashcard:" prefix
- Consistent formatting for `_parse_flashcard_response()`

## Module Details

### `llm_provider.py`
**Purpose**: Generate flashcard content using Claude API

**Key Methods**:
- `generate_flashcard_content(word)` - Main entry point, returns dict with word, content, visual_concept
- `_parse_flashcard_response(response, word)` - Extracts structured data from LLM response
- `_extract_visual_concept(response)` - Extracts image description from response
- `validate_response(response)` - Validates required fields and minimum content length

**Important**: Uses `claude-3-5-sonnet-20241022` model. Update model ID if newer versions available.

### `image_provider.py`
**Purpose**: Generate and cache conceptual images

**Key Methods**:
- `generate_image(word, visual_concept)` - Downloads image from Pollinations.ai, returns path
- `_enhance_concept_for_no_text(concept)` - Prepends anti-text instructions to concept
- `_build_image_url(concept)` - Constructs Pollinations.ai URL with URL encoding

**Image URL Pattern**: `https://image.pollinations.ai/prompt/{encoded_concept}?width=1024&height=1024&nologo=true`

**Retry Logic**: Attempts up to `max_retries_image` times with 2-second delays.

### `anki_connector.py`
**Purpose**: Communicate with AnkiConnect and create cards

**Key Methods**:
- `check_connection()` - Verifies AnkiConnect is running
- `create_deck_if_needed(deck_name)` - Ensures deck exists
- `add_media_file(file_path, filename)` - Uploads image to Anki (base64 encoded)
- `create_flashcards(word, content, image_filename, deck_name, tags)` - Creates both cards

**AnkiConnect Protocol**: All communication via POST to `http://localhost:8765` with JSON payload:
```json
{
  "action": "actionName",
  "version": 6,
  "params": {...}
}
```

**Card Model**: Uses "Basic" model (standard Anki model with Front/Back fields).

### `card_formatter.py`
**Purpose**: Generate HTML for card fronts and backs

**Formatting Rules**:
- Word styling: `color: #0000FF; font-weight: bold; font-size: 20px;`
- Images: `max-width: 100%; height: auto;`
- Line breaks preserved from LLM output using `<br>` tags
- HTML escaping applied to prevent injection

**Two Card Types**:
1. **Image→Word**: Front=image, Back=word+content
2. **Word→Image**: Front=word, Back=image+word+content

## Cache System

File: `data/processadas.json`

Format:
```json
{
  "word_lowercase": {
    "timestamp": "2024-01-15T10:30:00",
    "card_ids": [1234567890, 1234567891]
  }
}
```

**Behavior**:
- Words are cached after successful processing
- Cache prevents duplicate API calls and duplicate cards
- `--reset-cache` flag clears cache and reprocesses all words
- Cache is case-insensitive (stored as lowercase)

## Error Handling

The system implements fail-forward behavior:
- Individual word failures don't stop batch processing
- Detailed error messages with context (word, module, action)
- Final summary shows success/skip/fail counts
- Exit code 1 if any failures occurred

Common errors and handling:
- **AnkiConnect unavailable**: Check at startup, clear error message
- **Invalid API key**: Caught at config load time
- **Image generation failure**: Retry up to 3 times, then fail word
- **Parsing errors**: Fail word with detailed error message

## Development Conventions

1. **Language**: Code comments in Portuguese, documentation in English or Portuguese
2. **Type Hints**: All functions must have type hints
3. **Docstrings**: Google-style docstrings for all public methods
4. **Error Messages**: User-friendly, actionable error messages
5. **Logging**: Use print with emoji prefixes (🤖, 🎨, 🃏, etc.) for visual clarity
6. **Modularity**: Each module handles one concern, minimal coupling

## Common Development Tasks

### Adding a New Image Provider

1. Create new class in `image_provider.py` (e.g., `DalleImageProvider`)
2. Implement same interface: `generate_image(word, visual_concept) -> Optional[str]`
3. Update `settings.json` to select provider
4. Update `main.py` to instantiate correct provider based on config

### Modifying Flashcard Format

1. Edit HTML generation in `card_formatter.py`
2. Update `format_back()` and/or `format_front_*()` methods
3. Test with small word list before batch processing

### Changing LLM Model

1. Update model ID in `llm_provider.py`, line ~55: `model="claude-3-5-sonnet-20241022"`
2. Test prompt compatibility with new model
3. May need to adjust `max_tokens` parameter if model has different limits

### Adding New CLI Options

1. Add argument to parser in `main.py`, function `main()`
2. Implement handling logic after argument parsing
3. Update README.md usage section

## Testing Checklist

Before committing changes:

1. **AnkiConnect Test**: Ensure Anki is open and AnkiConnect responds
2. **Single Word Test**: `python main.py --word "test"` succeeds
3. **Cache Test**: Second run of same word is skipped
4. **Reset Test**: `--reset-cache` reprocesses cached words
5. **Error Test**: Invalid API key shows clear error message
6. **Batch Test**: Process 3-5 words, verify both cards created per word

## Prerequisites for Development

- Python 3.8+
- Anki desktop app with AnkiConnect plugin (code: 2055492159)
- Valid Anthropic API key
- Internet connection (for LLM API and image generation)

## File Safety

**Never commit**:
- `config/settings.json` (contains API key)
- `data/processadas.json` (cache, user-specific)
- `data/images/*.jpg` (generated images, large files)

**Safe to commit**:
- `config/prompt_template.txt` (no secrets)
- `data/palavras.txt` (sample word list)
- All `.py` files
- `requirements.txt`
- `.gitignore`

## Future Enhancement Ideas

- Parallel processing for multiple words
- Alternative image providers (DALL-E, Stable Diffusion)
- Audio pronunciation generation
- Support for phrases and idioms
- Web interface for easier configuration
- Batch statistics and reporting
- Custom card templates per deck
- Multi-language support (not just English)
