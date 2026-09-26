# Kiosk

宇野常寛さんの note、Slow Times など、定期的に確認したい書き手の新着を
1つの画面にまとめて読むための PWA。iPhone のホーム画面に置いて使う。

- 公開URL: https://tatsurosabah.github.io/kiosk/
- 収集: GitHub Actions が1日4回（日本時間 7:00 / 12:00 / 18:00 / 22:00）
  `fetch.py` を回して `articles.json` を更新する

## 何を保存するか（先に決めたこと）

**公開フィードに載っている範囲だけ**を `articles.json` に置く。見出し・サムネイル・日付・
冒頭の抜粋（既定1500字まで）と、原文へのリンク。有料記事の本文はそもそもフィードに
入っていないので取りにいかない。

GitHub Pages は無料プランだとリポジトリを private にできない（private にすると
サイトが 404 になる）。だから「公開されているものを並べ直しているだけ」の状態を保つ。

**貼り付けた本文は端末の中（localStorage）だけ**に置き、GitHub には送らない。
まぐまぐなどメールで届く有料メルマガをここに残さないための線引き。
既読・あとで読む も同じく端末内。設定画面から書き出し／読み込みができる。
書き出すバックアップには GitHub トークンを含めないため、新しい端末では再設定する。

## ファイル

| | |
|---|---|
| `sources.json` | 購読先。ここを編集して push すれば次回から反映される |
| | 読む: 宇野常寛 / Slow Times / 尾原和啓 / 中島聡 |
| | 観る: ガイアの夜明け / カンブリア宮殿 / ブレイクスルー / 橋本幸治の理系通信 / 西口さん、マーケティングって本当に必要ですか？ / 週刊ジョーホー / WEEKLY OCHIAI / CROSS DIG DOCUMENT / NIKKEI Film＆ドキュメント / 伊藤貫の真剣な雑談 |
| `fetch.py` | 収集本体。標準ライブラリだけで動く |
| `articles.json` | 収集結果。Actions が上書きする |
| `inbox.json` | アプリの「URLから追加」が書き込む受信箱。Actions が処理して空にする |
| `index.html` | アプリ本体（1枚） |
| `make_icon.py` | アイコン生成。外部ライブラリなしで PNG を書く |

## 使い方

### 購読先を足す

`sources.json` の `sources` に足して push するのが確実。アプリの設定画面から追加・解除も
できる（下記のトークンが要る）。追加するURLは公開リポジトリの履歴に残りうるため、
公開URLだけを使う。

### アプリからURLで足す

アプリは GitHub の Contents API で `inbox.json` に URL を追記する。そのために
**fine-grained personal access token** をこの端末に保存する。

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Repository access は **このリポジトリだけ**
3. Permissions は **Contents: Read and write** だけ
4. アプリの ⚙ → リポジトリ `tatsurosabah/kiosk` とトークンを入れて保存

`inbox.json` への push で workflow が走るので、数分で反映される。
「結果を見る」で成否が読める。

- サイトのトップやプロフィールURL → フィードを探して**購読に足す**
- 記事URL → **その1本だけ**取り込む
- 「どう扱うか」で明示的に選べる（Substack / note は記事URLでもフィードが
  見つかるので、1本だけ欲しいときは「この記事だけ」）

トークンを置きたくないときは、`inbox.json` を GitHub 上で直接編集しても同じ。

### 観る（YouTube プレイリスト）

`sources.json` に `"kind": "video"` を付けたソースは **観る** タブに入る。
フィードは **YouTube の公開RSS** `https://www.youtube.com/feeds/videos.xml?playlist_id=PL…`。
チャンネル登録せずにプレイリスト単位だけ追える（大きいチャンネルの全投稿が流れ込まない）。

- 取れるのは **各プレイリストの直近15本**。それより古い回はフィードに出てこない
- チップに**溜まっている本数**が出る
- 記事画面に **YouTube の埋め込みプレイヤー**が出る。速さは **等倍〜2倍**
  （選べる倍率は `getAvailablePlaybackRates()` が返すものそのまま。**YouTube 側の上限が2倍**）
- **「ここまで観た」**を押すと、同じプレイリストの**その回を含む古い回**をまとめて既読にする。
  最初にどこまで観たか分からないときはこれで起点を作る

> **YouTube の feeds.xml は連続で叩くと 404 / 500 を返す。** 中身が消えたわけではない。
> `fetch.py` は3回まで待って retry し、YouTube のソース間は 2.5 秒空けている。

### まとめて既読

下の **まとめて既読** は「表示中すべて」だけでなく、**3日 / 1週間 / 1か月 / 3か月より前**から
選べる。それぞれ実際の件数が出る（件数が同じになる期間は出さない）。

- **ソースのチップを1つ選んでから開くと、その媒体だけ**が対象になる
- 記事・動画それぞれの詳細画面に **「ここまで既読」/「ここまで観た」**がある。
  同じソースの、その回を含むこれより古いものをまとめて既読にする
- 既読にしても消えない。**すべて** から読み直せる。1件だけ戻すなら開いて「未読に戻す」

### 「見たい」ラベル

フィードのカード右上の **☆** を押すと「見たい」に入る（記事を開かなくてよい）。
上の **見たい** タブにそれだけが並ぶ。
カードを**右へスワイプ**しても同じフラグを付け外しできる。
カードを**左へスワイプ**すると、一覧から直接、記事は既読・動画は視聴済みにできる。

**URLで足した記事と貼り付けた記事は、自動で「見たい」に入る。**
わざわざ自分で入れたものは「特に見たい」に決まっているため。
一度自動で付けたIDは `autoseen` に覚えておくので、**外したものが復活することはない**。

### メールで届くものを足す

「＋ → 本文を貼り付け」。見出しと本文を貼れば一覧に並ぶ。**この端末の中だけ**に残る。
元のURLがあれば入れておくと原文に飛べる。

## ローカルで動かす

```
python3 -m http.server 8790 --directory Kiosk
```

`.claude/launch.json` に `kiosk`（port 8790）で登録済み。
プレビューサーバーは python.org 版の python3 を指定してある
（システム Python は macOS の TCC で `~/Documents` を読めない）。

収集をローカルで試すとき:

```
KIOSK_INSECURE_SSL=1 python3 fetch.py --dry     # 書き込まずに確認
KIOSK_INSECURE_SSL=1 python3 fetch.py           # articles.json を更新
KIOSK_INSECURE_SSL=1 python3 fetch.py --inbox   # inbox.json だけ処理
```

`KIOSK_INSECURE_SSL` は python.org 版の証明書エラー回避用。ubuntu では要らない。
ローカル実行のあとは Actions と衝突するので `git pull --rebase` してから push する。

## 直すときの注意

- **`index.html` / `sw.js` を変えたら `sw.js` の `CACHE` の版番号を必ず上げる**
- localhost では Service Worker を登録しない作りにしてある（古い版が出続けるため）
- 収集元の追加は `fetch.py` の `guess_feed_urls()` に1行足すのが早い
  （note / Substack / はてなブログ / Medium は URL の形だけでフィードに当てている）

## 判明していること

- note の RSS に本文は入っていない。見出し・サムネイル・冒頭まで。
  `<media:thumbnail>` は **URLを属性でなく要素の中身に書く**流儀なので注意
- Substack の RSS は `content:encoded` を持つが、購読者限定の号は
  末尾が `Read more` で切れる。これを見て「ここまで」を出している
- `slowinternet.jp` は WordPress だがフィードが無効。購読には足せない
  （記事URLを1本ずつ「この記事だけ」で入れることはできる）
- **Facebook の個人投稿は取れない。** RSS が無く、Graph API も他人の個人プロフィールの
  投稿は読めない（本人が Page の権限をくれる場合を除く）。尾原和啓さんは Facebook より
  note (`note.com/kazobara`) の方が更新が早いので、そちらを購読している
- 中島聡さんのメルマガ「週刊 Life is beautiful」はまぐまぐの有料配信で RSS が無い。
  ただし本人が note (`note.com/lifeisbeautiful`) に**メルマガで扱った記事の要約・解説**を
  出しているので、そちらを購読している。まぐまぐのバックナンバー一覧は
  直近の号が公開されておらず（`/archives/0001323030/2026/9` は404）使えない

## 画像まわり

- 一覧は **24件ずつの段階描画**（scroll 監視で追い読み）。note の画像は一度に
  何十枚も要求すると返ってこなくなるので、まとめて出さない
- サムネイルは 320px、記事のヒーローは 1000px に縮めて読み込む。
  note は `?width=`、Substack は `substackcdn.com/image/fetch/w_.../<encoded url>`。
  **Substack の元画像は1枚1MB超**あるので、縮めないとスクロールで数十MB落ちる
  （実測 1,167KB → 20KB）
- `loading="lazy"` は実機では効くが、検証に使ったヘッドレスブラウザでは
  ビューポート判定が働かず永久に pending になる。画像が出ないときはこれを疑う前に
  `loading` を `eager` にして切り分ける
