# kaiken-scan

中道改革連合・立憲民主党・公明党の3党合流（2026年8月28日に白紙）について、
国民民主党・榛葉賀津也幹事長と中道改革連合・小川淳也代表が
公式YouTubeの記者会見で何を語ったかを追うための資料一式。

## まずこれを読む

**[`HANDOFF.md`](HANDOFF.md)** — 引き継ぎメモ本体。両氏の発言記録（榛葉6件／小川12件）、
協議の時系列、未確認事項、出典URL。確度 A/B/C つき。

Webページ版: https://claude.ai/code/artifact/c6706d55-c370-431e-9328-8436464a8255
（ソースは `handoff.html`）

## 重要な制約

この資料を作った環境から **youtube.com と主要報道サイトの全てがネットワークポリシーで遮断**されていた。
そのため **会見動画内のタイムスタンプは1件も取得できておらず**、
引用はすべて検索エンジンのスニペット由来で一次記事を読んでいない。
`HANDOFF.md` の確度表記と「未取得」の明示は、その未確認状態を示すためのもの。

## タイムスタンプを実測する

`scripts/scan.py` が、yt-dlp で公式チャンネルの会見を列挙し、日本語字幕を走査して
キーワードのヒット箇所を **`h:mm:ss` ＋ `&t=` 付きリンク ＋ 前後2〜3分の逐語**で出力する。
YouTube にアクセスできる環境で実行すること。

```bash
pip install -r scripts/requirements.txt

# 対象動画の一覧だけ確認（字幕はダウンロードしない）
python3 scripts/scan.py --config config/shimba_kokumin.json --dry-run

# 本番
./scripts/run.sh
```

| 出力 | 中身 |
|---|---|
| `output/*/report.md` | 会見ごとのヒット箇所（タイムスタンプ・リンク・逐語） |
| `output/*/hits.json` | 同じものの機械可読版 |
| `output/*/captions/` | 取得した字幕の生データ（2回目以降のキャッシュ） |

主なオプション: `--dry-run` / `--since` `--until`（`YYYY-MM-DD`）/ `--max-videos` / `--resolve-dates`

### 仕組み

1. `yt-dlp --flat-playlist` で動画一覧を取得
2. タイトルに埋まっている日付（`2026年6月19日（金）`）で期間を絞る
   — 公式の会見動画はタイトルに必ず日付が入るので、これが一番速くて確実
3. `--write-auto-subs --sub-format json3` で日本語字幕を取得
   - `json3` の `aAppend` イベントを捨てて自動字幕のローリング重複を除去
   - `json3` が無ければ `vtt` にフォールバック（直近行との突き合わせで重複除去）
4. ヒットしたセグメントを60秒以内なら1件にまとめる
5. 前45秒〜後120秒を文脈として切り出し、`watch?v=ID&t=SEC` を付けて出力

### 走査対象

| 設定 | 対象 |
|---|---|
| `config/shimba_kokumin.json` | 国民民主党 公式ch（`UCJc_jL0yOBGychLgiTCGtPw`）＋代表・幹事長会見プレイリスト。タイトルに「榛葉/幹事長会見」を含むもの |
| `config/ogawa_chudo.json` | 中道改革連合 公式ch（`@CRAJ2026`）全動画 |
| `config/targets.json` | 上記2つを合流関連キーワードだけで一括走査 |

### 出力後に必ずやること

字幕は**自動生成**を含み、固有名詞（「中道」「立憲」「榛葉」など）は誤変換される。
`&t=` リンクを開いて**音声で確認**し、逐語を直してから `HANDOFF.md` を更新すること。
`scan.py` は「探す」ためのもので、「裏を取る」のは人間の仕事。

## ファイル

```
HANDOFF.md    引き継ぎメモ（本体）
handoff.html  同内容のWebページ版ソース
PROMPT.md     実行環境のClaude Codeに渡す指示文
config/       走査設定
scripts/      スキャナ
output/       実行結果（gitignore済み）
```
