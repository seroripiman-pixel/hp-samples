# kaiken-scan — 政党公式YouTube会見の発言抽出キット

**目的**：中道改革連合・立憲民主党・公明党の3党合流（2026年8月に見送り）について、

1. 国民民主党・**榛葉賀津也幹事長**が公式YouTubeの記者会見で言及した箇所
2. 中道改革連合・**小川淳也代表**が公式YouTubeで言及した箇所

を、**タイムスタンプ＋会見リンク＋前後の文脈**付きで洗い出す。

---

## 先に読んでほしいこと（重要）

この一式を作ったセッションでは、**youtube.com が組織のネットワークポリシーで遮断**されており
（`CONNECT` に 403）、動画・字幕・概要欄のいずれも取得できませんでした。
ニュースサイトも同様に遮断され、使えたのは検索エンジンのスニペットだけです。

そのため **`data/` 配下は「報道から再構成した見取り図」であり、タイムスタンプは空欄** です。
ご要望の分単位のタイムスタンプは、**YouTube にアクセスできる環境で `scripts/scan.py` を回して**
取得してください。それが本キットの主目的です。

回避策（プロキシ等）は取っていません。解決するには次のどちらかです：

- **手元のPCの Claude Code / ターミナル**でこのリポジトリを clone して実行する（最短）
- Claude Code on the web の**環境のネットワークポリシーを緩める**
  → https://code.claude.com/docs/en/claude-code-on-the-web

---

## 使い方

```bash
git clone <このリポジトリ>
cd kaiken-scan
pip install -r scripts/requirements.txt

# まず対象動画の一覧だけ確認（字幕はダウンロードしない）
python3 scripts/scan.py --config config/shimba_kokumin.json --dry-run

# 本番：榛葉幹事長ぶんと小川代表ぶんをまとめて走査
./scripts/run.sh
```

期間を絞ると速い：

```bash
python3 scripts/scan.py --config config/shimba_kokumin.json \
  --since 2026-06-01 --until 2026-09-30 --outdir output/shimba
```

### 出力

| ファイル | 中身 |
|---|---|
| `output/*/report.md` | 会見ごとに、ヒットしたタイムスタンプ・`&t=`付きリンク・前後の逐語 |
| `output/*/hits.json` | 同じものの機械可読版（`video_id` `timestamp` `deep_link` `context` …） |
| `output/*/captions/` | 取得した字幕の生データ。2回目以降はキャッシュとして再利用 |

### 主なオプション

| オプション | 説明 |
|---|---|
| `--dry-run` | 対象動画の一覧だけ出力して終了 |
| `--since` / `--until` | 対象期間（`YYYY-MM-DD`） |
| `--max-videos` | チャンネルごとの取得上限（既定 300） |
| `--resolve-dates` | タイトルに日付がない動画も1本ずつ `upload_date` を取得（遅い） |

---

## 仕組み

1. `yt-dlp --flat-playlist` でチャンネル/プレイリストの動画一覧を取得
2. 動画タイトルに埋まっている日付（`2026年6月19日（金）`）で期間を絞り込み
   （公式チャンネルの会見動画はタイトルに必ず日付が入るので、これが一番速くて確実）
3. `--write-auto-subs --sub-format json3` で日本語字幕を取得
   - `json3` の `aAppend` イベントを捨てて、自動字幕のローリング重複を除去
   - `json3` が無ければ `vtt` にフォールバック（こちらは直近行との突き合わせで重複除去）
4. キーワードにヒットしたセグメントを、60秒以内なら1件にまとめる
5. ヒット地点の前45秒〜後120秒を文脈として切り出し、
   `https://www.youtube.com/watch?v=ID&t=SEC` を付けて出力

---

## 走査対象

| 設定ファイル | 対象 |
|---|---|
| `config/shimba_kokumin.json` | 国民民主党 公式チャンネル（`UCJc_jL0yOBGychLgiTCGtPw`）＋ 代表・幹事長会見プレイリスト。タイトルに「榛葉/幹事長会見」を含むもの |
| `config/ogawa_chudo.json` | 中道改革連合 公式チャンネル（`@CRAJ2026`）全動画 |
| `config/targets.json` | 上記2つを合流関連キーワードだけで一括走査 |

キーワードや期間は JSON を直接いじってください。

---

## 手作業での検証手順（必須）

字幕は**自動生成**を含みます。政治家の固有名詞（「中道」「立憲」「榛葉」など）は
誤変換されることがあるため、次を必ずやってください。

1. `report.md` のヒット箇所の `&t=` リンクを開く
2. **音声で発言を確認**し、逐語を修正する
3. 引用として使う場合は、会見の日付・時刻と発言者を明記する

`scan.py` は「探す」ためのもので、「裏を取る」のは人間の仕事です。

---

## ディレクトリ

```
config/     走査設定（チャンネル・期間・キーワード）
data/       現時点で報道から分かっていること（タイムスタンプなし）
  timeline.md          3党合流の経緯
  findings_shimba.md   榛葉幹事長の言及
  findings_ogawa.md    小川代表の言及
  sources.md           出典URL一覧
scripts/    スキャナ本体
output/     実行結果（gitignore 済み）
PROMPT.md   Claude Code にそのまま貼れる指示文
```
