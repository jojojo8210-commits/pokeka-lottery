# 収集器(レーン1)の導入と運用

公式のお知らせページ・RSSを1日2回巡回し、**変化があったときだけ**AIで構造化して、`data/lotteries.json` の更新案を **PR** にします。
**PRをマージすると公開されます(= 承認)。**

```
取得(robots.txt遵守) → 本文抽出 → ハッシュ比較 → 変化なしなら終了(AI費用ゼロ)
  → AI抽出(根拠の引用つき) → 根拠が原文にあるか照合 → スキーマ検証 → PR
```

## 1. 追加するファイル
| パス | 内容 |
|---|---|
| `scripts/collect.py` | 収集器 |
| `scripts/eval_gold.py` | ゴールドセットの採点 |
| `prompts/extractor.md` | 抽出役の指示書 |
| `config/sources.yaml` | 情報源の台帳 |
| `requirements.txt` | 必要なライブラリ |
| `.github/workflows/collect.yml` | 1日2回の自動実行 |
| `docs/COLLECTOR.md`, `docs/GOLD_SET.md`, `docs/gold_case_template.json` | この手順書など |
| `index.html`(上書き) | 「最終確認」の表示を追加(変更は `setChecked` 関数と、その呼び出し1行だけ) |

## 2. 設定(最初の1回)
1. **`.assetsignore` に追記**(公開しないため): `config` `prompts` `state` `docs` `requirements.txt` `gold` `.cache`
   さらに **`data/chains.yaml` `data/shops.yaml` `data/schema.json`** も追記してください。index.html が読むのは `data/lotteries.json` だけなので、
   これらは公開する必要がなく、特に chains.yaml の hint(競合記事の要約)が誰でもダウンロードできる状態になっています。
   ※ `data/freshness.json`(各情報源の最終確認時刻)は、サイトで「最終確認」を表示するために**公開してよい**ものです。
2. **`.gitignore` に追記**: `.cache/` `gold/` `__pycache__/`
3. **GitHub → Settings → Secrets and variables → Actions** に `ANTHROPIC_API_KEY` を登録。
4. **Settings → Actions → General → Workflow permissions**: 「Read and write permissions」を選び、「Allow GitHub Actions to create and approve pull requests」にチェック。
5. **Settings → General**: 「Automatically delete head branches」にチェック(マージ後に作業ブランチを自動削除)。
6. モデルは環境変数 `EXTRACT_MODEL` で変えられます(初期値 `claude-sonnet-5-5`)。モデルIDは公式ドキュメントで確認してください。

## 3. 情報源を1件ずつ有効にする
0. **先に `data/shops.yaml` にその店舗を追加する。** `validate.py` は `shop_id` が shops.yaml にないと失敗します(収集器も事前に確認して、なければ実行しません)。
   公式サイトを巡回する店舗は `x_handle: null` で構いません。例:
   ```yaml
   - id: aeon-style-online
     name: イオンスタイルオンライン
     x_handle: null
     store_type: chain
     chain_id: aeon          # chains.yaml の id
     prefecture: 全国
     area: オンライン
     priority: normal
     other_sources: [aeon-style-online-news]   # sources.yaml の id
     note: ""
   ```
1. `config/sources.yaml` に1件追加し、**利用規約と robots.txt を確認**してから `tos_checked`(確認日)と `robots_ok: true` を書く。
   書かないと収集器はその情報源を実行しません。
2. `shop_id` が `data/shops.yaml` に、`chain_id` が `data/chains.yaml` にあることを確認する。
3. `enabled: true` にして、Actions タブ → **collect** → **Run workflow**(`source` にIDを入れる)。
4. できた PR を確認する(下記)。問題なければ次の情報源へ。**最初は1件ずつ、3件まで。**

## 4. PRを承認するときのチェックリスト
PRの説明に、抽選ごとの「根拠(AIが示した原文の抜粋)」と「要確認の理由」が出ます。
- [ ] 受付・発表・購入期間の**日付と時刻**が原文どおりか(特に応募期間と購入期間を取り違えていないか)
- [ ] 応募条件(会員・カード・本人確認・購入履歴)が抜けていないか
- [ ] 支払い制限(自社カードのみなど)と、排他(1店舗のみ)が正しいか
- [ ] 「時刻が未記載のため仮置き」は、告知で時刻を確認して直す(直したら `review_needed` を `false` に)
- [ ] 出典URLが公式ページか

直せない・自信がないものは、`review_needed: true` のままマージしても構いません(サイトで確認待ちとして扱う前提)。

## 5. 承認の段階(自動化は精度が証明されてから)
| 段階 | 内容 | 進む条件 |
|---|---|---|
| L0 | すべてのPRを人が承認 | 最初の1か月 |
| L1 | 状態(受付中→終了)の更新だけ自動マージ | ゴールドセットで日付系99%以上 |
| L2 | 検証を通り、公式ドメインで、日付・条件の変更が軽微なものだけ自動マージ | L1で誤りゼロが続く |

## 6. 運用メモ
- **手で直した抽選を守る**: `lotteries.json` のその抽選に `"locked": true` を足すと、収集器は上書きしません(差分は報告されます)。
- **PRを閉じた(却下した)とき**: 状態が保存されないので、次の実行で再度提案されます。再提案が不要なら、`sources.yaml` の `selector` を調整するか、情報源を無効にします。
- **費用**: `MAX_EXTRACTIONS_PER_RUN`(初期値20)で、1回の実行のAI呼び出し数に上限がかかります。同じ内容はキャッシュされます(キャッシュが消えると再抽出されるだけです)。
- **取得失敗**: 3回連続で失敗すると、Issue「収集失敗」が自動で立ちます。
- **鮮度**: 実行のたびに `data/freshness.json` が更新されます(変更なしでも「確認した時刻」が残る)。サイト側でこれを読んで「最終確認」を表示すると、鮮度の訴求になります。
- **ステータス**: 受付中・終了などは、index.html が日時から計算して表示するので、収集器は抽出時に1回つけるだけです(PRのノイズを避けるため)。

## 7. 既存データについての注意
- **サンプル4件(`sample-*`)**: 本番データを入れる前に `lotteries.json` から削除してください。サイトに「動作確認用のサンプル」の注意が出続けます。
- **`chains.yaml` の `hint` と `win_rate_ref: 約16.9%`**: 競合記事や提供画像の要約・数値です。「競合のデータを取り込まない」という方針と食い違うので、
  公開リポジトリからは外し(公式で確認できたものだけ残す)、`lotteries.json` のサンプル4件の `win_rate_ref` も削除してください。
- 収集器は `hint` を抽出に使いません(未検証の情報で抽出が偏るのを避けるため)。
- 受付期間が固定されない形式(Amazonの招待リクエストなど)は、`validate.py` の規則で `review_needed: true` になります。index.html では「状態が不明」と表示されます(`entry_end` がないため)。

## 8. 既知の制約
- **JavaScriptで描画されるページ・ログイン必須のページは取得できません**(例: ポケモンセンターオンラインの抽選一覧)。レーン2(手動投入)で対応する予定です。
- 画像だけの告知は、この収集器では自動処理しません(抽出関数は画像に対応済み。投入の仕組みは次の作業)。
- GitHub の定期実行は、公開リポジトリで60日間活動がないと自動停止します。PRのマージなどの活動があれば続きます。
- 定期実行は数分〜数十分遅れることがあります。
- `GITHUB_TOKEN` で作った PR では、他のワークフロー(validate.yml)が自動起動しません。そのため collect.yml の中で `scripts/validate.py` を実行しています。
