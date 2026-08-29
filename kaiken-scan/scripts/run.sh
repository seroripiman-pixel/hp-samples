#!/usr/bin/env bash
# 榛葉幹事長ぶんと小川代表ぶんを別々に走査して output/ 以下に出す
set -euo pipefail
cd "$(dirname "$0")/.."

# yt-dlp は brew 版があればそれを使う。無ければ入れ方を出して止まる。
if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "yt-dlp が見つかりません。どちらかで入れてください:" >&2
  echo "  brew install yt-dlp                                   # macOS 推奨" >&2
  echo "  python3 -m pip install --user -r scripts/requirements.txt" >&2
  exit 1
fi
echo "yt-dlp: $(command -v yt-dlp) ($(yt-dlp --version 2>/dev/null))"

# 期間を絞りたいときは SINCE / UNTIL を渡す:
#   SINCE=2026-06-01 ./scripts/run.sh
RANGE=()
[ -n "${SINCE:-}" ] && RANGE+=(--since "$SINCE")
[ -n "${UNTIL:-}" ] && RANGE+=(--until "$UNTIL")

python3 scripts/scan.py --config config/shimba_kokumin.json --outdir output/shimba "${RANGE[@]}"
python3 scripts/scan.py --config config/ogawa_chudo.json    --outdir output/ogawa  "${RANGE[@]}"

echo
echo "できたもの:"
echo "  output/shimba/report.md  output/shimba/hits.json"
echo "  output/ogawa/report.md   output/ogawa/hits.json"
echo
echo "次: report.md の &t= リンクを開いて音声で確認し、HANDOFF.md を更新する"
