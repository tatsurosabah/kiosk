# Kiosk

宇野常寛さんの note、PLANETS、Slow Times など、定期的に確認したい書き手の新着を
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

## ファイル

| | |
|---|---|
| `sources.json` | 購読先。ここを編集して push すれば次回から反映される |
| `fetch.py` | 収集本体。標準ライブラリだけで動く |
| `articles.json` | 収集結果。Actions が上書きする |
| `inbox.json` | アプリの「URLから追加」が書き込む受信箱。Actions が処理して空にする |
| `index.html` | アプリ本体（1枚） |
| `make_icon.py` | アイコン生成。外部ライブラリなしで PNG を書く |

## 使い方

### 購読先を足す

`sources.json` の `sources` に足して push するのが確実。アプリの「＋ → URLから」でも
足せる（下記のトークンが要る）。

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
