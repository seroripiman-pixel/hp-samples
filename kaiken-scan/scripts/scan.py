#!/usr/bin/env python3
"""
政党公式YouTubeの記者会見から、指定キーワードの発言箇所を
「タイムスタンプ付き・前後の文脈込み」で抽出するスキャナ。

やること:
  1. yt-dlp でチャンネル/プレイリストの動画一覧を取得
  2. タイトル埋め込み日付 or upload_date で対象期間に絞り込み
  3. 各動画の日本語字幕（自動生成含む）を json3 / vtt で取得
  4. キーワードにヒットした箇所を、前後 N 秒の文脈と
     https://www.youtube.com/watch?v=ID&t=SEC 形式のリンク付きで出力

出力:
  output/hits.json    機械可読な全ヒット
  output/report.md    人が読む/Claude に読ませるレポート
  output/captions/    取得した字幕の生データ（再実行時のキャッシュ）

使い方:
  pip install -r scripts/requirements.txt
  python3 scripts/scan.py --config config/targets.json
  python3 scripts/scan.py --config config/targets.json --dry-run   # 対象動画の一覧だけ
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------- utilities

# 「2026年6月19日」「2026/6/19」「2026.6.19」をタイトルから拾う
TITLE_DATE_RE = re.compile(
    r"(20\d{2})\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})\s*日?"
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def hhmmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def run_ytdlp(args: list[str], *, capture: bool = True) -> str:
    cmd = ["yt-dlp", *args]
    proc = subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        tail = detail[-3:] if detail else ["(no stderr)"]
        raise RuntimeError(f"yt-dlp failed ({proc.returncode}): " + " / ".join(tail))
    return proc.stdout if capture else ""


# ---------------------------------------------------------------- data model


@dataclass
class Video:
    video_id: str
    title: str
    source: str
    date: str | None = None  # YYYY-MM-DD

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


@dataclass
class Hit:
    video_id: str
    video_title: str
    video_date: str | None
    video_url: str
    keyword: str
    start_sec: int
    timestamp: str
    deep_link: str
    context: str


# ---------------------------------------------------------------- enumeration


def enumerate_videos(source: dict, max_videos: int) -> list[Video]:
    """チャンネル/プレイリスト/単体動画URLから動画一覧を作る。"""
    url = source["url"]
    name = source.get("name", url)

    if "/watch?v=" in url or "youtu.be/" in url:
        vid = re.sub(r"^.*(?:v=|youtu\.be/)([\w-]{11}).*$", r"\1", url)
        raw = run_ytdlp(["--skip-download", "--print", "%(id)s\t%(title)s", url])
        line = raw.strip().splitlines()[0] if raw.strip() else f"{vid}\t(unknown)"
        vid, title = line.split("\t", 1)
        return [Video(vid, title, name)]

    out = run_ytdlp(
        [
            "--flat-playlist",
            "--playlist-end",
            str(max_videos),
            "--print",
            "%(id)s\t%(title)s",
            url,
        ]
    )
    videos: list[Video] = []
    for line in out.strip().splitlines():
        if "\t" not in line:
            continue
        vid, title = line.split("\t", 1)
        videos.append(Video(vid.strip(), title.strip(), name))
    return videos


def date_from_title(title: str) -> str | None:
    m = TITLE_DATE_RE.search(title)
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def fetch_upload_date(video_id: str) -> str | None:
    try:
        raw = run_ytdlp(
            [
                "--skip-download",
                "--print",
                "%(upload_date)s",
                f"https://www.youtube.com/watch?v={video_id}",
            ]
        )
    except RuntimeError:
        return None
    raw = raw.strip()
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


def in_range(day: str | None, since: str | None, until: str | None) -> bool:
    if day is None:
        return True  # 日付不明はふるい落とさず、後段のキーワードに任せる
    if since and day < since:
        return False
    if until and day > until:
        return False
    return True


# ---------------------------------------------------------------- captions


def download_captions(video_id: str, outdir: Path, langs: str) -> Path | None:
    outdir.mkdir(parents=True, exist_ok=True)
    existing = sorted(outdir.glob(f"{video_id}.*"))
    existing = [p for p in existing if p.suffix in (".json3", ".vtt", ".json")]
    if existing:
        return existing[0]

    for sub_format in ("json3", "vtt"):
        try:
            run_ytdlp(
                [
                    "--skip-download",
                    "--write-subs",
                    "--write-auto-subs",
                    "--sub-langs",
                    langs,
                    "--sub-format",
                    sub_format,
                    "--output",
                    str(outdir / "%(id)s.%(ext)s"),
                    f"https://www.youtube.com/watch?v={video_id}",
                ]
            )
        except RuntimeError as exc:
            log(f"    字幕取得失敗 ({sub_format}): {exc}")
            continue
        got = sorted(outdir.glob(f"{video_id}.*"))
        got = [p for p in got if p.suffix in (".json3", ".vtt", ".json")]
        if got:
            # 自動生成より手動字幕を優先（ファイル名に .ja. が入る）
            got.sort(key=lambda p: (".ja-orig." in p.name, len(p.name)))
            return got[0]
    return None


def parse_json3(path: Path) -> list[tuple[float, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    segments: list[tuple[float, str]] = []
    for ev in data.get("events", []):
        # aAppend は自動字幕のローリング再掲。捨てないと全文が二重になる。
        if ev.get("aAppend"):
            continue
        segs = ev.get("segs") or []
        text = "".join(s.get("utf8", "") for s in segs)
        text = text.replace("\n", " ").strip()
        if not text:
            continue
        segments.append((ev.get("tStartMs", 0) / 1000.0, text))
    return segments


VTT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
VTT_TAG_RE = re.compile(r"<[^>]+>")


def parse_vtt(path: Path) -> list[tuple[float, str]]:
    segments: list[tuple[float, str]] = []
    recent: list[str] = []
    cur_start: float | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, cur_start
        if cur_start is None:
            buf = []
            return
        for line in buf:
            clean = VTT_TAG_RE.sub("", line).strip()
            if not clean or clean in recent:
                continue
            segments.append((cur_start, clean))
            recent.append(clean)
            del recent[:-4]  # 直近4行だけ見てローリング重複を落とす
        buf = []

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        m = VTT_TIME_RE.search(line)
        if m:
            flush()
            h, mi, s, ms = (int(x) for x in m.groups()[:4])
            cur_start = h * 3600 + mi * 60 + s + ms / 1000.0
            continue
        if not line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")):
            continue
        if line.isdigit():
            continue
        buf.append(line)
    flush()
    return segments


def load_segments(path: Path) -> list[tuple[float, str]]:
    if path.suffix in (".json3", ".json"):
        return parse_json3(path)
    return parse_vtt(path)


# ---------------------------------------------------------------- scanning


def scan_segments(
    video: Video,
    segments: list[tuple[float, str]],
    keywords: list[str],
    before_sec: float,
    after_sec: float,
    merge_gap_sec: float,
) -> list[Hit]:
    if not segments:
        return []

    patterns = [(kw, re.compile(re.escape(kw))) for kw in keywords]
    raw_hits: list[tuple[int, str]] = []  # (segment index, keyword)
    for idx, (_, text) in enumerate(segments):
        for kw, pat in patterns:
            if pat.search(text):
                raw_hits.append((idx, kw))

    if not raw_hits:
        return []

    # 近接ヒットは1件にまとめる（同じ話題を何度も出さないため）
    grouped: list[tuple[int, set[str]]] = []
    for idx, kw in raw_hits:
        if grouped and segments[idx][0] - segments[grouped[-1][0]][0] <= merge_gap_sec:
            grouped[-1][1].add(kw)
        else:
            grouped.append((idx, {kw}))

    hits: list[Hit] = []
    for idx, kws in grouped:
        center = segments[idx][0]
        lo, hi = center - before_sec, center + after_sec
        chunk = [t for (ts, t) in segments if lo <= ts <= hi]
        start = max(0, int(center - before_sec))
        hits.append(
            Hit(
                video_id=video.video_id,
                video_title=video.title,
                video_date=video.date,
                video_url=video.url,
                keyword="/".join(sorted(kws)),
                start_sec=start,
                timestamp=hhmmss(center),
                deep_link=f"{video.url}&t={start}s",
                context=" ".join(chunk).strip(),
            )
        )
    return hits


# ---------------------------------------------------------------- reporting


def write_report(hits: list[Hit], videos: list[Video], path: Path, cfg: dict) -> None:
    lines: list[str] = []
    lines.append("# 記者会見 発言抽出レポート")
    lines.append("")
    lines.append(f"- 生成日時: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"- 対象期間: {cfg.get('since', '指定なし')} 〜 {cfg.get('until', '指定なし')}")
    lines.append(f"- キーワード: {' / '.join(cfg.get('keywords', []))}")
    lines.append(f"- 走査した動画: {len(videos)} 本 / ヒット: {len(hits)} 箇所")
    lines.append("")
    lines.append("> 文字起こしは YouTube の自動生成字幕を含みます。固有名詞の誤認識があり得るため、")
    lines.append("> 引用として使う前に必ずタイムスタンプのリンク先で音声を確認してください。")
    lines.append("")

    by_video: dict[str, list[Hit]] = {}
    for h in hits:
        by_video.setdefault(h.video_id, []).append(h)

    if not hits:
        lines.append("該当なし。キーワードか対象期間を見直してください。")

    for vid, vhits in sorted(
        by_video.items(), key=lambda kv: (kv[1][0].video_date or "", kv[0])
    ):
        head = vhits[0]
        lines.append(f"## {head.video_date or '日付不明'} {head.video_title}")
        lines.append("")
        lines.append(f"会見リンク: {head.video_url}")
        lines.append("")
        for h in vhits:
            lines.append(f"### {h.timestamp}  （ヒット語: {h.keyword}）")
            lines.append("")
            lines.append(f"- 該当箇所: {h.deep_link}")
            lines.append("")
            lines.append("```text")
            lines.append(h.context)
            lines.append("```")
            lines.append("")

    lines.append("## 走査対象の全動画")
    lines.append("")
    for v in sorted(videos, key=lambda v: (v.date or "", v.video_id)):
        mark = "★" if v.video_id in by_video else "  "
        lines.append(f"- {mark} {v.date or '????-??-??'} [{v.title}]({v.url})")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/targets.json")
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--since", help="YYYY-MM-DD（configを上書き）")
    ap.add_argument("--until", help="YYYY-MM-DD（configを上書き）")
    ap.add_argument("--max-videos", type=int, default=300, help="チャンネルごとの取得上限")
    ap.add_argument("--dry-run", action="store_true", help="対象動画の一覧だけ出して終了")
    ap.add_argument("--resolve-dates", action="store_true",
                    help="タイトルに日付がない動画も1本ずつupload_dateを取りにいく（遅い）")
    args = ap.parse_args()

    if shutil.which("yt-dlp") is None:
        log("yt-dlp が見つかりません。`pip install -r scripts/requirements.txt` を実行してください。")
        return 2

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    since = args.since or cfg.get("since")
    until = args.until or cfg.get("until")
    cfg["since"], cfg["until"] = since, until
    keywords = cfg["keywords"]
    ctx = cfg.get("context", {})
    before_sec = float(ctx.get("before_sec", 45))
    after_sec = float(ctx.get("after_sec", 90))
    merge_gap = float(ctx.get("merge_gap_sec", 60))
    langs = cfg.get("sub_langs", "ja,ja-JP,ja-orig,ja.*")

    outdir = Path(args.outdir)
    capdir = outdir / "captions"
    outdir.mkdir(parents=True, exist_ok=True)

    selected: list[Video] = []
    for source in cfg["sources"]:
        log(f"[一覧取得] {source.get('name', source['url'])}")
        try:
            found = enumerate_videos(source, args.max_videos)
        except RuntimeError as exc:
            log(f"  取得失敗: {exc}")
            continue
        log(f"  {len(found)} 本")

        title_filter = source.get("title_regex")
        tf = re.compile(title_filter) if title_filter else None

        for v in found:
            if tf and not tf.search(v.title):
                continue
            v.date = date_from_title(v.title)
            if v.date is None and args.resolve_dates:
                v.date = fetch_upload_date(v.video_id)
            if not in_range(v.date, since, until):
                continue
            selected.append(v)

    # 同じ動画が複数ソースに出てきたら1本に
    uniq: dict[str, Video] = {}
    for v in selected:
        uniq.setdefault(v.video_id, v)
    videos = list(uniq.values())
    log(f"[対象] {len(videos)} 本")

    if args.dry_run:
        for v in sorted(videos, key=lambda v: (v.date or "", v.video_id)):
            print(f"{v.date or '????-??-??'}\t{v.video_id}\t{v.title}")
        return 0

    all_hits: list[Hit] = []
    for i, v in enumerate(sorted(videos, key=lambda v: (v.date or "", v.video_id)), 1):
        log(f"[{i}/{len(videos)}] {v.date or '????-??-??'} {v.title}")
        cap = download_captions(v.video_id, capdir, langs)
        if cap is None:
            log("    字幕なし。スキップ")
            continue
        segments = load_segments(cap)
        if not segments:
            log("    字幕を解析できず。スキップ")
            continue
        hits = scan_segments(v, segments, keywords, before_sec, after_sec, merge_gap)
        log(f"    セグメント {len(segments)} / ヒット {len(hits)}")
        all_hits.extend(hits)

    (outdir / "hits.json").write_text(
        json.dumps([asdict(h) for h in all_hits], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_report(all_hits, videos, outdir / "report.md", cfg)
    log(f"[完了] {len(all_hits)} 箇所 -> {outdir/'report.md'}, {outdir/'hits.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
