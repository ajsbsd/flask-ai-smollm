# anne.py — BM25 Archive Search

A lightweight command-line tool for full-text search over a PDF using SQLite FTS5 and BM25 ranking.

## Requirements

```
pymupdf
```

Install with:

```bash
pip install pymupdf
```

No other third-party dependencies. Uses Python's built-in `sqlite3` and `os`.

## Usage

Place `anne_applebaum_article.pdf` in the same directory as `anne.py`, then run:

```bash
python anne.py
```

On first run the script extracts the PDF text and builds a local SQLite index (`applebaum_archive.db`). Subsequent runs skip indexing and load the existing database directly.

Once loaded, you get an interactive prompt:

```
Search query > democracy
```

Results are ranked by BM25 score and capped at 5 matches. Each result shows the page number, score, and a keyword-in-context excerpt.

To exit, type `exit`, `quit`, or `q`, or press `Ctrl+C`.

## Files

| File | Description |
|---|---|
| `anne.py` | Main script |
| `anne_applebaum_article.pdf` | Source PDF (required on first run) |
| `applebaum_archive.db` | SQLite FTS5 index (auto-generated) |

## Search syntax

The search input is passed directly to SQLite FTS5, so standard operators work:

| Example | Behaviour |
|---|---|
| `democracy` | Match pages containing the word |
| `democracy autocracy` | Match pages containing both words |
| `democracy OR autocracy` | Match either word |
| `"liberal democracy"` | Exact phrase match |
| `democracy NOT russia` | Exclude pages containing a word |

## Notes

- The PDF must contain extractable text. Scanned PDFs without OCR will index as empty and return no results.
- Delete `applebaum_archive.db` to force a full re-index on next run.
