from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import typer
from rich.console import Console
from rich.table import Table

from ..lib.auth.auth import get_credentials
from ..lib.core.config import config
from ..lib.core.logger import setup_logging
from ..lib.core.quota import COSTS, QuotaExceededError, QuotaLedger
from ..lib.data.history import HistoryManager
from ..lib.data.snapshot import SnapshotCache
from ..lib.video.playlist import PlaylistInfo, PlaylistManager

app = typer.Typer(help="Manage playlists.")
console = Console()

# オーファン一覧をそのまま出力する最大件数。これを超えたら件数で省略する。
ORPHAN_PREVIEW_LIMIT = 50

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

def _make_cache() -> Optional[SnapshotCache]:
    """設定に応じて SnapshotCache を作る。無効なら None。"""
    if not config.cache.enabled:
        return None
    return SnapshotCache(db_path=config.cache.path, ttl_hours=config.cache.ttl_hours)


def _today_used_units(history: HistoryManager) -> int:
    """本日すでに消費したと推定されるユニット数を返す。

    本日のアップロード件数 x 1600 を使用済みとみなす。実際の残量は
    API 側にしか無いため厳密ではないが、QuotaLedger と 403 検知で補う。

    「本日」の境界は既存の check_quota_limit (upload_manager.py) と
    揃えてローカル時間の午前0時とする。
    """
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day).timestamp()
    records = history.get_all_records(limit=0)
    today_uploads = [
        r for r in records
        # timestamp が NULL の行があると None >= float で TypeError になる
        if r.get("status") == "success" and (r.get("timestamp") or 0) >= today_start
    ]
    return len(today_uploads) * COSTS["upload"]


def _default_max_items(
    history: HistoryManager, unit_cost: int = COSTS["insert"]
) -> int:
    """本日の残り予算から処理可能な件数を見積もる。

    unit_cost: 1件あたりの消費ユニット。orphans は insert のみ (50) だが、
    dedupe は insert + delete (100) なので呼び出し側で変える。
    """
    used = _today_used_units(history)
    budget = max(0, config.effective_daily_quota() - config.quota.reserve - used)
    return budget // unit_cost


def _print_no_budget_message(history: HistoryManager) -> None:
    """本日の残量では1件も処理できないことを、対処法とともに知らせる。

    「リセットを待て」だけでは、毎日大量にアップロードしているユーザーには
    恒久的に壊れているように見える。実際には quota.daily_limit が
    実際の GCP 上限より小さいことが原因なので、その旨を明示する。
    """
    limit = config.effective_daily_quota()
    used = _today_used_units(history)
    console.print(
        f"[bold red]本日の推定残量では1件も処理できません"
        f"(上限 {limit:,} / 本日の推定使用 {used:,} ユニット / "
        f"予備 {config.quota.reserve:,} ユニット)。[/]"
    )
    console.print(
        "[dim]実際の GCP クォータ上限が異なる場合は、settings.yaml の "
        "quota.daily_limit を実値に設定してください。"
        "上限を引き上げていない場合は、クォータのリセット "
        "(太平洋時間の深夜 / 日本時間の16〜17時頃) 後に再実行してください。[/]"
    )


def _resolve_target_playlist(record) -> Optional[str]:
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


def _fix_orphans(
    orphans: List[Dict[str, Any]],
    pl_manager: PlaylistManager,
    history: HistoryManager,
    ledger: QuotaLedger,
    max_items: int,
    yes: bool,
    cache: Optional[SnapshotCache] = None,
) -> Tuple[int, int]:
    """オーファンをプレイリストへ割り当てる。

    Returns: (assigned, remaining) — 成功件数と未処理件数。
    quota 枯渇・予算超過・max_items 到達のいずれかで中断する。

    cache: 成功した割り当てを増分反映するスナップショットキャッシュ。
    これを渡さないと、TTL (24時間) 内の再実行で get_all_playlists_map が
    「割り当てる前のマップ」を返し、同じオーファンが再構築されて
    50 units x N を空費する。
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

    skipped_synced = 0

    for orphan in targets:
        vid_id = orphan["id"]
        record = history.get_record_by_video_id(vid_id)
        target_playlist = _resolve_target_playlist(record)

        if not target_playlist:
            console.print(f"[dim]Skipping {orphan['title']} (no history/playlist found)[/]")
            processed += 1
            continue

        # 履歴が「追加済み (1)」と言っているものは再処理しない。
        # キャッシュを消した場合や --refresh を使った場合でも、
        # 同じ動画を何度も insert して quota を空費しないための保険。
        # 三値であることに注意: 0 (追加失敗) と None (この機能より前の
        # 既存レコード = 不明) は再試行の対象なのでスキップしてはいけない。
        if record.get("playlist_synced") == 1:
            skipped_synced += 1
            processed += 1
            continue

        # プレイリストが未作成なら playlists.insert (50 units) も発生する。
        # find_playlist_id はキャッシュを見るだけで API を叩かないため、
        # ここで先に確かめて帳簿に正しく計上する。
        # (見落とすと実消費が帳簿の最大2倍になる)
        needs_new_playlist = pl_manager.find_playlist_id(target_playlist) is None
        insert_count = 2 if needs_new_playlist else 1

        if not ledger.can_afford("insert", insert_count):
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
            ledger.charge("insert", insert_count)
            history.set_playlist_synced(vid_id, ok)

            if ok:
                assigned += 1
                # キャッシュにも即座に反映する。これが無いと TTL 内の
                # 再実行で同じオーファンが再構築されてしまう。
                if cache is not None:
                    cache.add_playlist_item(pl_id, vid_id)
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

    if skipped_synced:
        console.print(
            f"[dim]追加済みとして記録されていた {skipped_synced} 件はスキップしました。[/]"
        )

    remaining = len(orphans) - processed
    return assigned, remaining


@app.command("orphans")
def list_orphans(
    fix: bool = typer.Option(False, "--fix", help="Automatically assign orphans to playlists based on history"),
    max_items: Optional[int] = typer.Option(None, "--max-items", help="1回の実行で処理する最大件数 (既定: 本日の残り予算から算出)"),
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

    cache = None
    history = None

    try:
        # cache / history の生成自体も try に含める。
        # try の外で生成すると、片方が生成できた直後にもう片方の
        # 生成が例外を投げた場合に finally を通らず接続が漏れる。
        cache = _make_cache()
        history = HistoryManager()

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
        console.print(f"[bold]走査したプレイリスト:[/] {len(playlist_map)}")
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

        # 数千件を無条件に流すと確認プロンプトが画面外に押し出されるため、
        # 多い場合は先頭だけ出して残りは件数で示す。
        console.print("\n[bold]Orphan Videos:[/]")
        for orphan in orphans[:ORPHAN_PREVIEW_LIMIT]:
            console.print(f"- {orphan['title']} ({orphan['id']})")
        if len(orphans) > ORPHAN_PREVIEW_LIMIT:
            console.print(f"[dim]... 他 {len(orphans) - ORPHAN_PREVIEW_LIMIT} 件[/]")

        if not fix:
            console.print("\n[dim]Run with --fix to attempt automatic assignment based on local history.[/]")
            return

        # 予算は常に本日の残量 (budget_items) から決める。--max-items は
        # あくまで「予算内での上限」であり、予算そのものを拡張してはいけない
        # (--max-items に大きな値を渡すとクォータ安全弁が消える不具合を防ぐ)。
        budget_items = _default_max_items(history)
        limit = min(max_items, budget_items) if max_items is not None else budget_items
        if limit <= 0:
            _print_no_budget_message(history)
            return

        ledger = QuotaLedger(budget_items * COSTS["insert"])
        assigned, remaining = _fix_orphans(
            orphans, pl_manager, history, ledger, limit, yes, cache=cache
        )

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
        if history is not None:
            history.close()
        if cache is not None:
            cache.close()


def _merge_duplicate_group(
    canonical: PlaylistInfo,
    duplicates: List[PlaylistInfo],
    pl_manager: PlaylistManager,
    playlist_map: Dict[str, Set[str]],
    ledger: QuotaLedger,
    max_items: int,
    failed_moves: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[int, int, bool]:
    """1つの重複グループを統合する。

    canonical に動画を集約し、空になった重複プレイリストを削除する。

    Returns: (moved, deleted, interrupted) — 移動した動画数、削除した
    プレイリスト数、クォータ枯渇 (実際の API 403) で中断したかどうか。
    途中で中断した場合、中身が残るプレイリストは削除しない。

    failed_moves: 移動に失敗した (プレイリスト名, video_id) を積むリスト。
    削除済み・非公開の動画が混ざっていると毎回同じ失敗を繰り返して
    quota だけ減るため、呼び出し元がまとめて報告できるようにする。

    安全のため、以下の場合も削除しない:
    - playlist_map に重複プレイリストのIDが無い (中身を把握していない。
      スナップショットが古い/未取得のときに「空」と誤認するのを防ぐ)
    - 把握している動画数が実際の item_count より少ない (未把握の動画が
      残っている可能性がある)
    """
    canonical_videos = set(playlist_map.get(canonical.id, set()))
    moved = 0
    deleted = 0

    for dup in duplicates:
        if dup.id not in playlist_map:
            console.print(
                f"[yellow]中身が不明のため削除をスキップ: {dup.title} ({dup.id})[/]"
            )
            continue

        dup_videos = playlist_map[dup.id]
        fully_moved = True

        for video_id in sorted(dup_videos):
            if moved >= max_items:
                fully_moved = False
                break

            needs_insert = video_id not in canonical_videos
            required = ledger.cost_of("insert") if needs_insert else 0
            required += ledger.cost_of("delete")
            if ledger.remaining < required:
                fully_moved = False
                break

            try:
                if needs_insert:
                    if not pl_manager.add_video_to_playlist(canonical.id, video_id):
                        console.print(
                            f"[red]移動失敗: {video_id} -> {canonical.title}[/]"
                        )
                        fully_moved = False
                        if failed_moves is not None:
                            failed_moves.append((dup.title, video_id))
                        continue
                    ledger.charge("insert")
                    canonical_videos.add(video_id)

                if not pl_manager.remove_video_from_playlist(dup.id, video_id):
                    console.print(f"[red]削除失敗: {video_id} from {dup.id}[/]")
                    fully_moved = False
                    if failed_moves is not None:
                        failed_moves.append((dup.title, video_id))
                    continue
                ledger.charge("delete")
                moved += 1

            except QuotaExceededError:
                console.print("\n[bold red]クォータを使い切りました。中断します。[/]")
                return moved, deleted, True

        if fully_moved and len(dup_videos) < dup.item_count:
            console.print(
                f"[yellow]件数が一致しないため削除をスキップ: {dup.title} ({dup.id}) "
                f"— 把握 {len(dup_videos)} 件 / 実際 {dup.item_count} 件[/]"
            )
            continue

        if fully_moved:
            # 予算不足を ledger.charge の例外で検知すると、実際には 403 が
            # 出ていないのに「クォータを使い切りました」と誤報して
            # interrupted=True になってしまう。事前に確認して静かに打ち切る。
            if not ledger.can_afford("delete"):
                console.print(
                    f"[bold yellow]予算上限に達したため削除を見送ります: "
                    f"{dup.title} ({dup.id})[/]"
                )
                continue

            try:
                if pl_manager.delete_playlist(dup.id):
                    deleted += 1
                    ledger.charge("delete")
                    console.print(f"[green]重複プレイリストを削除: {dup.id}[/]")
            except QuotaExceededError:
                console.print("\n[bold red]クォータを使い切りました。中断します。[/]")
                return moved, deleted, True

    return moved, deleted, False


@app.command("dedupe")
def dedupe_playlists(
    fix: bool = typer.Option(
        False, "--fix", help="重複を統合する (動画を最古のプレイリストへ移動し、空になった方を削除)"
    ),
    max_items: int = typer.Option(50, "--max-items", help="1回の実行で移動する最大動画数"),
    yes: bool = typer.Option(False, "-y", "--yes", help="確認プロンプトを省略"),
):
    """
    同名の重複プレイリストを検出し、必要なら統合する。

    検出のみ (--fix なし) でも、プレイリスト一覧の取得に
    playlists.list が必要なため 0 units にはならない
    (50件/ページなので 544 個なら約 11 units)。
    """
    setup_logging(level="INFO")

    cache = _make_cache()
    history = None

    try:
        credentials = get_credentials()
        pl_manager = PlaylistManager(credentials, cache=cache)

        try:
            duplicates = pl_manager.get_duplicate_playlists()
        except QuotaExceededError:
            console.print("[bold red]クォータを使い切っているため取得できませんでした。[/]")
            raise typer.Exit(code=1)

        if not duplicates:
            console.print("[green]重複しているプレイリストはありません。[/]")
            return

        total_dups = sum(len(v) - 1 for v in duplicates.values())
        console.print(f"[bold red]重複しているタイトル:[/] {len(duplicates)}")
        console.print(f"[bold red]余剰プレイリスト:[/] {total_dups}")

        table = Table(title="Duplicate Playlists")
        table.add_column("Title", style="magenta")
        table.add_column("正 (最古)", style="green")
        table.add_column("重複", style="yellow")
        for title, items in duplicates.items():
            table.add_row(
                title, items[0].id, ", ".join(p.id for p in items[1:])
            )
        console.print(table)

        if not fix:
            console.print("\n[dim]--fix を付けると統合します。[/]")
            return

        # --fix は破壊的操作 (プレイリスト削除) なので、本日の実残量から
        # 予算を決める (orphans と同様。--max-items で予算そのものを
        # 拡張する抜け道を防ぐ)。dedupe は1本あたり insert + delete = 100
        # units 消費するため _default_max_items に unit_cost を渡す。
        history = HistoryManager()
        budget_items = _default_max_items(
            history, unit_cost=COSTS["insert"] + COSTS["delete"]
        )
        limit = min(max_items, budget_items)
        if limit <= 0:
            _print_no_budget_message(history)
            return

        try:
            # --fix は 24 時間キャッシュされたスナップショットに基づいて
            # 削除してはいけない (中身の入ったプレイリストを誤って空と
            # 判定して削除してしまう)。必ず最新を取得する。
            playlist_map = pl_manager.get_all_playlists_map(refresh=True)
        except QuotaExceededError:
            console.print("[bold red]クォータを使い切っているため統合できません。[/]")
            raise typer.Exit(code=1)

        movable = sum(
            len(playlist_map.get(p.id, set()))
            for items in duplicates.values()
            for p in items[1:]
        )
        target_count = min(movable, limit)
        estimated = (
            target_count * (COSTS["insert"] + COSTS["delete"])
            + total_dups * COSTS["delete"]
        )
        # 削除分 (total_dups * 50) は target_count と違って limit で
        # 頭打ちにならないため、estimated をそのまま予算にすると本日の
        # 残量を無視して大量に消費しうる (空の重複が200個あれば +10,000
        # units)。必ず本日の残量で上限を掛ける。
        budget_units = min(estimated, budget_items * (COSTS["insert"] + COSTS["delete"]))

        console.print(
            f"\n[bold]見積もり:[/] 最大 {target_count} 本の移動 + "
            f"{total_dups} 個の削除 = 約 {estimated:,} units "
            f"(本日の予算上限 {budget_units:,} units)"
        )

        if not yes:
            if not typer.confirm("統合を実行しますか?"):
                raise typer.Abort()

        ledger = QuotaLedger(budget_units)
        total_moved = 0
        total_deleted = 0
        interrupted = False
        stopped_by_limit = False
        processed_groups = 0
        failed_moves: List[Tuple[str, str]] = []

        for title, items in duplicates.items():
            # 削除も予算を消費するため打ち切り判定に含める。移動0件でも
            # 削除だけ進む (中身が空の重複) ケースで止まらなくなるのを防ぐ。
            if total_moved + total_deleted >= limit:
                stopped_by_limit = True
                break
            console.print(f"\n[bold]統合中: {title}[/]")
            moved, deleted, group_interrupted = _merge_duplicate_group(
                items[0], items[1:], pl_manager, playlist_map,
                ledger, limit - total_moved, failed_moves=failed_moves,
            )
            total_moved += moved
            total_deleted += deleted
            if group_interrupted:
                # 中断したグループは処理済みではない。数えてしまうと
                # 残グループ数が1件過少になる。
                interrupted = True
                break
            processed_groups += 1

        console.print(
            f"\n[bold green]完了: {total_moved} 本を移動、"
            f"{total_deleted} 個のプレイリストを削除しました[/] "
            f"(消費 約 {ledger.spent:,} units)"
        )

        if failed_moves:
            console.print(
                f"\n[bold yellow]移動できなかった動画 {len(failed_moves)} 件[/] "
                "(削除済み・非公開の可能性があります):"
            )
            for pl_title, video_id in failed_moves[:ORPHAN_PREVIEW_LIMIT]:
                console.print(f"[yellow]- {pl_title} -> {video_id}[/]")
            if len(failed_moves) > ORPHAN_PREVIEW_LIMIT:
                console.print(
                    f"[dim]... 他 {len(failed_moves) - ORPHAN_PREVIEW_LIMIT} 件[/]"
                )
            console.print(
                "[dim]これらを含むグループは、再実行しても同じ失敗を繰り返して"
                "クォータだけ消費します。YouTube 上で該当動画を確認してください。[/]"
            )

        if interrupted or stopped_by_limit:
            remaining_groups = len(duplicates) - processed_groups
            console.print(
                f"[bold yellow]残り {remaining_groups} グループ[/] — "
                "同じコマンドを再実行すると残りから再開します。"
            )

        # dedupe はプレイリストとその中身しか変えない。videos まで捨てると
        # 次回の orphans で動画一覧の再取得 (約400 units) が無駄に発生する。
        # 何も変更していないなら捨てる理由自体が無い。
        if cache is not None and (total_moved or total_deleted):
            cache.clear("playlists")
            cache.clear("playlist_items")
            console.print(
                "[dim]プレイリストのキャッシュを破棄しました "
                "(次回は最新を取得します)。[/]"
            )

    finally:
        if history is not None:
            history.close()
        if cache is not None:
            cache.close()
