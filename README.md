# calibre-pdf-analyzer

Analyze PDFs in Calibre and enrich metadata using Claude AI.

## Features

- Extract PDF metadata (version, page count, tags, outlines, forms, links)
- Store analysis in Calibre custom columns
- Use Claude AI to suggest improved titles, authors, tags, and descriptions

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Create custom columns (Calibre must be closed)
calibre-pdf-analyzer create-columns --library /path/to/calibre/library

# Analyze PDFs and store metadata
calibre-pdf-analyzer analyze --library /path/to/calibre/library

# Get AI-powered metadata suggestions
calibre-pdf-analyzer enrich --library /path/to/calibre/library --confirm
```

Set `ANTHROPIC_API_KEY` environment variable for AI features.