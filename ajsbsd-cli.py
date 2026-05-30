#!/usr/bin/env python3
"""
Arsen Avakov FTS5 Search REPL
Interactive, color-rich terminal interface for PDF full-text search.
"""
import os
import sqlite3
import sys

import fitz  # PyMuPDF
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.theme import Theme

# 🎨 WILD COLOR THEME
custom_theme = Theme({
    "info": "bold cyan",
    "success": "bold bright_green",
    "warning": "bold yellow3",
    "error": "bold red",
    "prompt": "bold blue",
    "header": "bold magenta",
    "dim": "dim white",
    "match": "bold bright_red",
    "page": "cyan",
    "score": "bright_yellow"
})
console = Console(theme=custom_theme)


def extract_pdf_to_pages(pdf_path):
    console.print(f"[info][*] Opening PDF:[/info] [bold]{pdf_path}[/bold]...")
    doc = fitz.open(pdf_path)
    pages_data = []
    total_chars = 0

    for page_idx, page in enumerate(doc):
        text = page.get_text("text")
        total_chars += len(text.strip())
        pages_data.append((page_idx + 1, text))

    console.print(
        f"[success][+] Extracted {len(pages_data)} pages[/success] | [dim]Total chars: {total_chars:,}[/dim]")
    if total_chars == 0:
        console.print(
            "[warning][!] Warning: Zero text extracted. PDF may be scanned/missing OCR.[/warning]")
    return pages_data


def build_index(pages_data, db_path="ArsenAvakov.db"):
    console.print(
        f"[info][*] Building FTS5 index in '[/info][bold]{db_path}[/bold][info]'...[/info]")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS search_index")
    cursor.execute("""
        CREATE VIRTUAL TABLE search_index USING fts5(
            page_num UNINDEXED,
            content
        )
    """)
    cursor.executemany(
        "INSERT INTO search_index (page_num, content) VALUES (?, ?)",
        pages_data
    )
    conn.commit()
    console.print("[success][+] Index built successfully.[/success]")
    return conn


def query_index(conn, search_term):
    if not search_term.strip():
        return
    console.print(
        f"\n[info][*] Searching for:[/info] [bold match]'{search_term}'[/bold match]...")
    cursor = conn.cursor()

    query = """
        SELECT page_num, snippet(search_index, 1, '<b>', '</b>', '...', 20) as excerpt, bm25(search_index) as rank
        FROM search_index
        WHERE content MATCH ?
        ORDER BY rank ASC
        LIMIT 5
    """

    try:
        results = cursor.execute(query, (search_term,)).fetchall()

        if not results:
            console.print(
                f"[warning][!] No matches found for: '{search_term}'[/warning]")
            console.print(
                "[dim]    Try broader terms or FTS5 operators (e.g., 'Ukraine OR Soviet')[/dim]")
            return

        console.print(
            f"\n[header]--- 🔍 Search Results ({len(results)} matches) ---[/header]")

        for idx, row in enumerate(results, 1):
            page_num, excerpt, rank = row
            # Convert FTS5 HTML highlights to Rich markup safely
            excerpt_rich = excerpt.replace(
                "<b>", "[bold bright_red]").replace(
                "</b>", "[/bold bright_red]")
            # Escape stray brackets to prevent Rich markup parsing errors
            excerpt_rich = excerpt_rich.replace(
                "[", "\\[").replace(
                "\\[bold", "[bold")
            rank_rounded = round(rank, 4)
            console.print(Panel(
                f"[page]Page {page_num}[/page] | [score]BM25: {rank_rounded}[/score]\n\n"
                f"[dim]Context:[/dim]\n{excerpt_rich}",
                title=f"[bold]Match #{idx}[/bold]",
                border_style="bright_blue",
                padding=(1, 2)
            ))
    except sqlite3.OperationalError as e:
        console.print(f"[error][!] SQLite error: {e}[/error]")


def main():
    console.print(Panel.fit(
        "[bold header]📖 Arsen Avakov FTS5 Search REPL[/bold header]\n"
        "[dim]Type 'help' for commands, 'exit' or Ctrl+C to quit.[/dim]",
        border_style="magenta",
        title="[bold]⚡ LIVE INDEX[/bold]"
    ))

    pdf_file = "ArsenAvakov.pdf"
    if not os.path.exists(pdf_file):
        console.print(
            f"[error][!] Error: '{pdf_file}' not found in current directory.[/error]")
        return

    conn = None
    try:
        data = extract_pdf_to_pages(pdf_file)
        conn = build_index(data)
        console.print(
            "\n[success][✓] Index loaded. Ready for queries![/success]\n")

        while True:
            try:
                term = Prompt.ask("[prompt]arsen-ft5>[/prompt]").strip()
                if not term:
                    continue
                if term.lower() in ("exit", "quit", "q"):
                    console.print("[warning][*] Shutting down...[/warning]")
                    break
                elif term.lower() == "help":
                    console.print(Panel(
                        "[bold]Available Commands:[/bold]\n"
                        "• [bold]help[/bold]       Show this menu\n"
                        "• [bold]exit[/bold] / [bold]q[/bold]  Quit the REPL\n"
                        "• [bold]reload[/bold]     Re-extract & rebuild index\n"
                        "• [bold]<text>[/bold]      Full-text search (supports AND/OR/NOT/\"exact\")",
                        title="[bold]📚 Help[/bold]",
                        border_style="cyan"
                    ))
                elif term.lower() == "reload":
                    console.print("[info][*] Reloading index...[/info]")
                    data = extract_pdf_to_pages(pdf_file)
                    conn = build_index(data)
                else:
                    query_index(conn, term)
            except KeyboardInterrupt:
                console.print(
                    "\n[warning][*] Interrupted. Type 'exit' to quit.[/warning]")
            except EOFError:
                break

    except Exception as e:
        console.print(f"[error][!] Fatal error: {e}[/error]")
        sys.exit(1)
    finally:
        if conn:
            conn.close()
            console.print("[dim][*] Database connection closed.[/dim]")


if __name__ == "__main__":
    main()
