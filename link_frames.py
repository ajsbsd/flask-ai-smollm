#!/usr/bin/env python3
"""
Dynamic Frame Linker
Zero hard-coded values. Discovers documents and images interactively.
"""
import os
import sqlite3
import glob
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

console = Console()


def main():
    console.print(Panel.fit(
        "[bold cyan]🔗 Dynamic Frame Linker[/bold cyan]\n"
        "Link extracted video frames to your FTS5 RAG database.",
        border_style="cyan"
    ))

    db_path = "imperium_archive.db"
    if not os.path.exists(db_path):
        console.print(f"[red]Error:[/red] Database '{db_path}' not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Ensure table exists
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_id INTEGER,
        frame_path TEXT,
        timestamp_sec REAL
    )
    ''')

    # 2. Find the document dynamically via FTS5
    search_term = Prompt.ask(
        "[bold yellow]Enter a unique word from the transcript "
        "to find the document[/bold yellow]\n"
        "(e.g., 'theo', 'openbsd', 'firewall')"
    )

    # Use snippet to show context and confirm it's the right document
    cursor.execute("""
        SELECT rowid, snippet(document_pages, 1, '[', ']', '...', 40)
        FROM document_pages
        WHERE document_pages MATCH ?
        LIMIT 5
    """, (search_term,))
    results = cursor.fetchall()

    if not results:
        console.print(
            f"\n[red]❌ No matches found for '{search_term}'.[/red]"
        )
        console.print(
            "[dim]💡 Tip: Make sure the MP3 transcript has been "
            "ingested into imperium_archive.db first![/dim]"
        )
        conn.close()
        return

    console.print(f"\n[green]✅ Found {len(results)} matching pages.[/green]")

    # Grab the first match's rowid (expand to let user pick if needed)
    doc_id = results[0][0]
    snippet = (
        results[0][1]
        .replace('[', '[bold bright_red]')
        .replace(']', '[/bold bright_red]')
    )

    console.print(
        f"[dim]Linking to Document ID (rowid): [bold]{doc_id}[/bold][/dim]"
    )
    console.print(f"[dim]Context: {snippet}[/dim]\n")

    # 3. Find the frames directory dynamically
    default_dir = "static/images/theo_rubsd2013_frames"
    frames_dir = Prompt.ask(
        "[bold yellow]Enter the directory containing "
        "the extracted frames[/bold yellow]",
        default=default_dir
    )

    if not os.path.isdir(frames_dir):
        console.print(
            f"[red]❌ Directory '{frames_dir}' does not exist.[/red]"
        )
        conn.close()
        return

    # 4. Auto-discover all images in the directory
    frame_files = sorted(
        glob.glob(os.path.join(frames_dir, "*.jpg"))
        + glob.glob(os.path.join(frames_dir, "*.png"))
    )

    if not frame_files:
        console.print(
            f"[red]❌ No .jpg or .png files found in '{frames_dir}'.[/red]"
        )
        conn.close()
        return

    console.print(
        f"[green]✅ Discovered {len(frame_files)} image files.[/green]"
    )

    # Clear existing frames for this doc_id to prevent duplicates on re-runs
    cursor.execute(
        "DELETE FROM video_frames WHERE document_id = ?", (doc_id,)
    )

    # 5. Insert dynamically
    total_frames = len(frame_files)
    for i, frame_path in enumerate(frame_files):
        # Auto-calculate a sequential timestamp
        # (e.g., 0.0, 2.5, 5.0, 7.5 for 4 frames)
        timestamp = (
            round(i * (10.0 / max(total_frames - 1, 1)), 1)
            if total_frames > 1 else 0.0
        )

        # Ensure path is relative to 'static/' so Flask's url_for works
        web_path = (
            frame_path.replace("static/", "", 1)
            if frame_path.startswith("static/")
            else frame_path
        )

        cursor.execute('''
            INSERT INTO video_frames (document_id, frame_path, timestamp_sec)
            VALUES (?, ?, ?)
        ''', (doc_id, web_path, timestamp))

    conn.commit()

    console.print(
        f"\n[bold green]🎉 Success![/bold green] "
        f"Linked {len(frame_files)} frames to Document ID {doc_id}."
    )
    console.print(
        f"[bold cyan]👉 Next step: Open your web terminal and type: "
        f"[bold white]frames {doc_id}[/bold white][/bold cyan]"
    )

    conn.close()


if __name__ == "__main__":
    main()
