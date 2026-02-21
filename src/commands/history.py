import csv
import json
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..lib.data.history import HistoryManager

app = typer.Typer(help="Manage upload history.")
console = Console()

@app.command("history")
def history(
    limit: int = typer.Option(0, help="Number of records to show (0 for all)"),
    status: str = typer.Option(
        None, help="Filter by status (success/failed)"
    ),
):
    """
    Show upload history.
    """
    # setup_logging() # Optional, maybe not needed for just reading DB
    history_manager = HistoryManager()
    # Always fetch all to filter manually
    all_records = history_manager.get_all_records(limit=0)
    
    # Calculate stats
    total = len(all_records)
    failed = len([r for r in all_records if r.get("status") == "failed"])
    success = len([r for r in all_records if r.get("status", "success") == "success"])
    
    console.print(
        Panel(
            f"[bold]Total: {total}[/] | [green]Success: {success}[/] | [red]Failed: {failed}[/]",
            title="Summary",
            expand=False
        )
    )

    records = all_records
    if status:
        records = [r for r in records if r.get("status", "success") == status]

    if limit > 0:
        records = records[:limit]

    if not records:
        console.print("[yellow]No upload history found (matching filter).[/]")
        return

    table = Table(title="Upload History")
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Title", style="magenta")
    table.add_column("Video ID / Error", style="green")
    table.add_column("File", style="dim")

    for r in records:
        ts = r.get("timestamp")
        date_str = (
            datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M") if ts else "N/A"
        )
        status = r.get("status", "success")
        full_path = r.get("file_path", "")
        file_name = Path(full_path).name if full_path else "N/A"
        
        # Create clickable link for file path
        if full_path:
            # rich link syntax: [link=uri]text[/link]
            # Must convert to absolute URI for file:// to work reliably
            uri = Path(full_path).resolve().as_uri()
            path_display = f"[link={uri}]{file_name}[/link]"
        else:
            path_display = "N/A"
        
        if status == "failed":
            status_str = "[red]Failed[/]"
            title = file_name
            vid = r.get("error", "Unknown Error")
            # Truncate long error messages
            if len(vid) > 40:
                vid = vid[:37] + "..."
            vid_col = f"[red]{vid}[/]"
        else:
            status_str = "[green]Success[/]"
            vid = r.get("video_id", "N/A")
            vid_col = f"[link=https://youtu.be/{vid}]{vid}[/link]" if vid != "N/A" else "N/A"
            title = r.get("metadata", {}).get("title", "N/A")

        table.add_row(date_str, status_str, title, vid_col, path_display)

    console.print(table)


@app.command("delete")
def delete(
    path: Path = typer.Option(None, "--path", "-p", help="Delete history by file path"),
    hash_val: str = typer.Option(None, "--hash", "-h", help="Delete history by file hash"),
    video_id: str = typer.Option(
        None, "--video-id", "-v", help="Delete history by Video ID"
    ),
):
    """
    Delete upload history by path, hash, or video ID.
    Exact match is required.
    """
    history_manager = HistoryManager()

    if path:
        # Resolve to absolute path for consistency if stored that way
        abs_path = path.resolve()
        if history_manager.delete_record_by_path(str(abs_path)):
            console.print(f"[green]Deleted history for path: {abs_path}[/]")
        else:
            # Try raw input string just in case
            if history_manager.delete_record_by_path(str(path)):
                 console.print(f"[green]Deleted history for path: {path}[/]")
            else:
                 console.print(f"[red]No record found for path: {path}[/]")

    if hash_val:
        if history_manager.delete_record(hash_val):
            console.print(f"[green]Deleted history for hash: {hash_val}[/]")
        else:
            console.print(f"[red]No record found for hash: {hash_val}[/]")
    
    if video_id:
        if history_manager.delete_record_by_video_id(video_id):
            console.print(f"[green]Deleted history for Video ID: {video_id}[/]")
        else:
            console.print(f"[red]No record found for Video ID: {video_id}[/]")

    if not path and not hash_val and not video_id:
        console.print("[yellow]Please specify --path, --hash, or --video-id to delete.[/]")


@app.command("export")
def export(
    format: str = typer.Option("json", "--format", "-f", help="Export format (json/csv)"),
    output: str = typer.Option(None, "--output", "-o", help="Output file path (default: stdout)"),
):
    """
    アップロード履歴をCSVまたはJSON形式でエクスポートする。
    """
    if format not in ("json", "csv"):
        console.print("[red]--format には 'json' または 'csv' を指定してください。[/]")
        raise typer.Exit(code=1)

    history_manager = HistoryManager()
    content = history_manager.export_records(format=format, output_path=output)

    if output:
        console.print(f"[green]Exported to {output}[/]")
    else:
        console.print(content)


@app.command("import")
def import_history(
    file: Path = typer.Argument(..., help="Import file path (JSON or CSV)"),
):
    """
    CSVまたはJSONファイルからアップロード履歴をインポートする。
    既に存在するレコード（file_hash が一致）はスキップされる。
    """
    if not file.exists():
        console.print(f"[red]File not found: {file}[/]")
        raise typer.Exit(code=1)

    # ファイル拡張子から形式を自動判別
    suffix = file.suffix.lower()

    try:
        with open(file, "r", encoding="utf-8") as f:
            raw = f.read()

        if suffix == ".csv":
            reader = csv.DictReader(raw.splitlines())
            records = []
            for row in reader:
                # CSVから読み込んだ数値型を変換
                if row.get("timestamp"):
                    try:
                        row["timestamp"] = float(row["timestamp"])
                    except (ValueError, TypeError):
                        pass
                if row.get("file_size"):
                    try:
                        row["file_size"] = int(row["file_size"])
                    except (ValueError, TypeError):
                        row["file_size"] = 0
                records.append(row)
        else:
            # JSON形式として読み込み
            records = json.loads(raw)
            if not isinstance(records, list):
                console.print("[red]JSON file must contain a list of records.[/]")
                raise typer.Exit(code=1)

    except (json.JSONDecodeError, csv.Error) as e:
        console.print(f"[red]Failed to parse file: {e}[/]")
        raise typer.Exit(code=1)

    history_manager = HistoryManager()
    imported, skipped = history_manager.import_records(records)

    console.print(
        f"[green]Import complete:[/] {imported} imported, {skipped} skipped (duplicates)"
    )
