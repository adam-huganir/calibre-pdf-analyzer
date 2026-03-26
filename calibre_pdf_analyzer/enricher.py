import json
import os

import anthropic

from calibre_pdf_analyzer.models import BookSuggestion


def suggest_metadata(existing: dict, text: str, api_key: str | None = None) -> BookSuggestion:
    """Use Claude to suggest improved metadata based on existing data and PDF text.

    Args:
        existing: Current Calibre metadata dict with title, authors, tags, comments
        text: Extracted text from first few pages of PDF
        api_key: Anthropic API key (falls back to ANTHROPIC_API_KEY env var)

    Returns:
        BookSuggestion with Claude's recommended metadata
    """
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("No API key provided and ANTHROPIC_API_KEY env var not set")

    client = anthropic.Anthropic(api_key=api_key)

    prompt = _build_prompt(existing, text)

    # Request structured JSON output from Claude
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    # Extract the text response and parse JSON
    response_text = message.content[0].text
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        # If Claude didn't return pure JSON, try to extract it
        # Look for JSON within code blocks or other formatting
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response_text[start:end])
        else:
            raise ValueError(f"Could not parse Claude response as JSON: {response_text}")

    return BookSuggestion(
        title=data.get("title"),
        authors=data.get("authors", []),
        tags=data.get("tags", []),
        comments=data.get("comments"),
    )


def _build_prompt(existing: dict, text: str) -> str:
    """Build the prompt for Claude with existing metadata and extracted text."""
    return f"""You are helping improve metadata for a PDF book in a Calibre library.

Current metadata:
- Title: {existing.get('title', 'Unknown')}
- Authors: {', '.join(existing.get('authors', [])) or 'Unknown'}
- Tags: {', '.join(existing.get('tags', [])) or 'None'}
- Comments: {existing.get('comments', 'None')}

First few pages of text from the PDF:
{text}

Based on the text content, please suggest improved metadata. Consider:
- Correct the title if it appears wrong or could be more accurate
- Identify the actual author(s) from the text
- Suggest relevant tags that categorize the content (genre, topics, themes)
- Write a brief 2-3 sentence description for the comments field

Return ONLY a JSON object with this exact structure (no markdown, no explanation):
{{
  "title": "suggested title or null to keep current",
  "authors": ["author1", "author2"],
  "tags": ["tag1", "tag2", "tag3"],
  "comments": "brief description or null to keep current"
}}"""
