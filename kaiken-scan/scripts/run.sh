#!/usr/bin/env bash
# 榛葉幹事長ぶんと小川代表ぶんを別々に走査して output/ 以下に出す
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m pip install -q -r scripts/requirements.txt

python3 scripts/scan.py --config config/shimba_kokumin.json --outdir output/shimba
python3 scripts/scan.py --config config/ogawa_chudo.json    --outdir output/ogawa

echo
echo "できたもの:"
echo "  output/shimba/report.md  output/shimba/hits.json"
echo "  output/ogawa/report.md   output/ogawa/hits.json"
