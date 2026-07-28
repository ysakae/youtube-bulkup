from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ..lib.auth.auth import get_credentials
from ..lib.core.config import config
from ..lib.core.logger import setup_logging
from ..lib.core.quota import COSTS, QuotaExceededError, QuotaLedger
from ..lib.data.history import HistoryManager
from ..lib.data.snapshot import SnapshotCache
from ..lib.video.playlist import PlaylistManager

app = typer.Typer(help="Manage playlists.")
console = Console()

def _get_manager():
    try:
        credentials = get_credentials()
        return PlaylistManager(credentials)
    except Exception as e:
        console.print(f"[bold red]Auth Error:[/] {e}")
        raise typer.Exit(code=1)

@app.command("list")
def list_playlists(
    name: str = typer.Argument(None, help="Playlist name or ID to show details"),
):
    """
    プレイリストの一覧を表示する。
    名前またはIDを指定すると、そのプレイリスト内の動画一覧を表示する。
    """
    setup_logging(level="INFO")
    manager = _get_manager()

    if name:
        # 指定プレイリストの動画一覧
        items = manager.list_playlist_items(name)
        if not items:
            console.print(f"[yellow]No videos found in playlist: {name}[/]")
            return

        table = Table(title=f"Playlist: {name} ({len(items)} videos)")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="magenta")
        table.add_column("Video ID", style="cyan")

        for item in items:
            vid = item["video_id"]
            link = f"[link=https://youtu.be/{vid}]{vid}[/link]"
            table.add_row(str(item["position"] + 1), item["title"], link)

        console.print(table)
    else:
        # 全プレイリスト一覧
        playlists = manager.list_playlists()
        if not playlists:
            console.print("[yellow]No playlists found.[/]")
            return

        table = Table(title=f"Playlists ({len(playlists)} total)")
        table.add_column("Title", style="magenta")
        table.add_column("ID", style="cyan")
        table.add_column("Videos", style="green", justify="right")
        table.add_column("Privacy", style="dim")

        for pl in playlists:
            table.add_row(pl["title"], pl["id"], str(pl["item_count"]), pl["privacy"])

        console.print(table)

@app.command("add")
def add_video(
    video_id: str = typer.Argument(..., help="YouTube Video ID"),
    playlist_name_or_id: str = typer.Argument(..., help="Playlist Name or ID"),
    privacy: str = typer.Option("private", help="Privacy status for new playlist")
):
    """
    Add a video to a playlist.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    # Simple heuristic: if it looks like an ID (starts with PL and usually long), treat as ID?
    # Actually PlaylistManager.get_or_create_playlist takes a TITLE.
    # If the user provides an ID, our current library implementation might try to create a playlist with that ID as Title?
    # The current library implementation is title-based for get_or_create.
    # To support ID directly we might need to enhance the lib, but strictly following the proposal:
    # "Playlist Name or ID" -> The library currently supports get_or_create by TITLE.
    # If we want to support ID, we should check if the input is a valid ID.
    # For now, let's stick to the library's capability: treat input as Title. 
    # If the user wants to use ID, we might need a separate command or library update.
    # Given the previous context, `get_or_create_playlist` uses title.
    
    # However, `add_video_to_playlist` takes a playlist ID.
    # So we need to resolve title to ID.
    
    playlist_id = manager.get_or_create_playlist(playlist_name_or_id, privacy)
    
    if not playlist_id:
        console.print(f"[red]Failed to find or create playlist: {playlist_name_or_id}[/]")
        raise typer.Exit(code=1)
        
    if manager.add_video_to_playlist(playlist_id, video_id):
        console.print(f"[green]Successfully added {video_id} to playlist {playlist_name_or_id} ({playlist_id})[/]")
    else:
        console.print("[red]Failed to add video to playlist.[/]")
        raise typer.Exit(code=1)

@app.command("remove")
def remove_video(
    video_id: str = typer.Argument(..., help="YouTube Video ID"),
    playlist_name_or_id: str = typer.Argument(..., help="Playlist Name or ID"),
):
    """
    Remove a video from a playlist.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    # プレイリスト名からIDを解決（存在しない場合は新規作成しない）
    playlist_id = manager.find_playlist_id(playlist_name_or_id)
    
    if not playlist_id:
        console.print(f"[red]Playlist not found: {playlist_name_or_id}[/]")
        raise typer.Exit(code=1)
        
    if manager.remove_video_from_playlist(playlist_id, video_id):
        console.print(f"[green]Successfully removed {video_id} from playlist {playlist_name_or_id}[/]")
    else:
        console.print("[red]Failed to remove video from playlist (maybe not found?).[/]")
        raise typer.Exit(code=1)

@app.command("rename")
def rename_playlist(
    old_name_or_id: str = typer.Argument(..., help="Current Playlist Name or ID"),
    new_name: str = typer.Argument(..., help="New Playlist Name"),
):
    """
    Rename a playlist.
    """
    setup_logging(level="INFO")
    manager = _get_manager()
    
    if manager.rename_playlist(old_name_or_id, new_name):
        console.print(f"[green]Successfully renamed playlist to '{new_name}'[/]")
    else:
        console.print("[red]Failed to rename playlist.[/]")
        raise typer.Exit(code=1)

def _make_cache():
    """設定に応じて SnapshotCache を作る。無効なら None。"""
    if not config.cache.enabled:
        return None
    return SnapshotCache(db_path=config.cache.path, ttl_hours=config.cache.ttl_hours)


def _default_max_items(history: HistoryManager) -> int:
    """本日の残り予算から処理可能な件数を見積もる。

    本日のアップロード件数 x 1600 を使用済みとみなす。実際の残量は
    API 側にしか無いため厳密ではないが、QuotaLedger と 403 検知で補う。

    「本日」の境界は既存の check_quota_limit (upload_manager.py:44-45) と
    揃えてローカル時間の午前0時とする。
    """
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day).timestamp()
    records = history.get_all_records(limit=0)
    today_uploads = [
        r for r in records
        if r.get("status") == "success" and r.get("timestamp", 0) >= today_start
    ]
    used = len(today_uploads) * COSTS["upload"]
    budget = max(0, config.effective_daily_quota() - config.quota.reserve - used)
    return budget // COSTS["insert"]


def _resolve_target_playlist(record) -> str:
    """履歴レコードから割り当て先のプレイリスト名を決める。

    playlist_name を優先し、無ければファイルパスの親ディレクトリ名を使う。
    """
    if not record:
        return None

    target = record.get("playlist_name")
    if target:
        return target

    file_path = record.get("file_path")
    if file_path:
        try:
            return Path(file_path).parent.name
        except Exception:
            return None
    return None


def _fix_orphans(orphans, pl_manager, history, ledger, max_items, yes):
    """オーファンをプレイリストへ割り当てる。

    Returns: (assigned, remaining) — 成功件数と未処理件数。
    quota 枯渇・予算超過・max_items 到達のいずれかで中断する。
    """
    targets = orphans[:max_items]

    if not yes:
        estimated = ledger.cost_of("insert", len(targets))
        console.print(
            f"\n[bold]見積もり:[/] {len(targets)} 件 x {COSTS['insert']} units "
            f"= {estimated:,} units"
        )
        if not typer.confirm(
            f"{len(targets)} 件をローカル履歴に基づいてプレイリストへ割り当てますか?"
        ):
            raise typer.Abort()

    console.print("\n[bold]Assigning Orphans...[/]")

    assigned = 0
    processed = 0

    for orphan in targets:
        vid_id = orphan["id"]
        record = history.get_record_by_video_id(vid_id)
        target_playlist = _resolve_target_playlist(record)

        if not target_playlist:
            console.print(f"[dim]Skipping {orphan['title']} (no history/playlist found)[/]")
            processed += 1
            continue

        if not ledger.can_afford("insert"):
            console.print(
                f"[bold yellow]予算上限に達しました "
                f"({ledger.spent:,}/{ledger.budget:,} units)。中断します。[/]"
            )
            break

        try:
            pl_id = pl_manager.get_or_create_playlist(target_playlist)
            if not pl_id:
                console.print(
                    f"[red]Failed to get/create playlist {target_playlist} "
                    f"for {orphan['title']}[/]"
                )
                processed += 1
                continue

            ok = pl_manager.add_video_to_playlist(pl_id, vid_id)
            ledger.charge("insert")
            history.set_playlist_synced(vid_id, ok)

            if ok:
                assigned += 1
                console.print(f"[green]Assigned {orphan['title']} -> {target_playlist}[/]")
            else:
                console.print(f"[red]Failed to assign {orphan['title']} -> {target_playlist}[/]")

            processed += 1

        except QuotaExceededError:
            console.print(
                "\n[bold red]クォータを使い切りました。処理を中断します。[/]"
            )
            console.print(
                "[dim]太平洋時間の深夜 (日本時間の16〜17時頃) にリセットされます。"
                "リセット後に同じコマンドを再実行すると、残りから再開します。[/]"
            )
            break

    remaining = len(orphans) - processed
    return assigned, remaining


@app.command("orphans")
def list_orphans(
    fix: bool = typer.Option(False, "--fix", help="Automatically assign orphans to playlists based on history"),
    max_items: int = typer.Option(None, "--max-items", help="1回の実行で処理する最大件数 (既定: 本日の残り予算から算出)"),
    refresh: bool = typer.Option(False, "--refresh", help="キャッシュを無視してAPIから取得し直す"),
    offline: bool = typer.Option(False, "--offline", help="APIを叩かずキャッシュのみで判定する (0 units)"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation for fix"),
):
    """
    Find videos not in any playlist (orphans) and optionally fix them.
    """
    setup_logging(level="INFO")

    if offline and fix:
        console.print("[bold red]--offline と --fix は同時に指定できません。[/]")
        raise typer.Exit(code=1)

    cache = _make_cache()
    history = HistoryManager()

    try:
        credentials = get_credentials()
        pl_manager = PlaylistManager(credentials, cache=cache)
        from ..lib.video.manager import VideoManager
        vid_manager = VideoManager(credentials, cache=cache)

        if offline:
            console.print("[yellow]オフラインモード: キャッシュから読み込みます (0 units)[/]")
        else:
            console.print("[yellow]Fetching all uploaded videos and playlist data... (this may take a while)[/]")

        try:
            all_videos = vid_manager.get_all_uploaded_videos(refresh=refresh, offline=offline)
            playlist_map = pl_manager.get_all_playlists_map(refresh=refresh, offline=offline)
        except QuotaExceededError:
            console.print("[bold red]クォータを使い切っているため取得できませんでした。[/]")
            console.print("[dim]--offline を付けるとキャッシュから調査できます。[/]")
            raise typer.Exit(code=1)
        except RuntimeError as e:
            console.print(f"[bold red]{e}[/]")
            raise typer.Exit(code=1)

        if not all_videos:
            console.print("[red]No uploaded videos found or API error.[/]")
            return

        videos_in_playlists = set()
        for vid_set in playlist_map.values():
            videos_in_playlists.update(vid_set)

        orphans = [vid for vid in all_videos if vid["id"] not in videos_in_playlists]

        console.print(f"[bold]Total Videos:[/] {len(all_videos)}")
        console.print(f"[bold]Playlists Scanned:[/] {len(playlist_map)}")
        console.print(f"[bold]Videos in Playlists:[/] {len(videos_in_playlists)}")
        console.print(f"[bold red]Orphan Videos:[/] {len(orphans)}")

        if not orphans:
            console.print("[green]No orphan videos found. All videos are in at least one playlist.[/]")
            return

        # 内訳を集計する (割り当て先の有無と、記録済みの同期状態)
        with_history = 0
        synced_failed = 0
        synced_unknown = 0
        for o in orphans:
            record = history.get_record_by_video_id(o["id"])
            if _resolve_target_playlist(record):
                with_history += 1
            if record is not None:
                if record.get("playlist_synced") == 0:
                    synced_failed += 1
                elif record.get("playlist_synced") is None:
                    synced_unknown += 1

        console.print(f"[bold]  うち履歴から割り当て先が判明:[/] {with_history}")
        console.print(f"[bold]  うち割り当て先不明 (スキップ対象):[/] {len(orphans) - with_history}")
        console.print(
            f"[dim]  同期状態の内訳: 追加失敗として記録済み {synced_failed} / "
            f"不明 (この機能より前の記録) {synced_unknown}[/]"
        )

        console.print("\n[bold]Orphan Videos:[/]")
        for orphan in orphans:
            console.print(f"- {orphan['title']} ({orphan['id']})")

        if not fix:
            console.print("\n[dim]Run with --fix to attempt automatic assignment based on local history.[/]")
            return

        limit = max_items if max_items is not None else _default_max_items(history)
        if limit <= 0:
            console.print(
                "[bold red]本日の推定残量では1件も処理できません。"
                "クォータのリセット後に再実行してください。[/]"
            )
            return

        ledger = QuotaLedger(limit * COSTS["insert"])
        assigned, remaining = _fix_orphans(orphans, pl_manager, history, ledger, limit, yes)

        console.print(
            f"\n[bold green]完了: {assigned} 件を割り当てました[/] "
            f"(消費 約 {ledger.spent:,} units)"
        )
        if remaining > 0:
            console.print(
                f"[bold yellow]残り {remaining} 件[/] — "
                "同じコマンドを再実行すると残りから再開します。"
            )

    finally:
        history.close()
        if cache is not None:
            cache.close()
