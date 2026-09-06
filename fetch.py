#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kiosk — 購読しているメディアの新着を1つの articles.json にまとめる。

  python3 fetch.py            収集して articles.json を更新
  python3 fetch.py --inbox    inbox.json のURLだけ処理して終わる
  python3 fetch.py --dry      書き込まずに結果を表示

保存するのは「公開されているフィードに載っている範囲」だけ。有料記事の本文は
フィードに入っていないので、そもそも取れないし取りにいかない。
"""

import json
import os
import re
import ssl
import sys
import time
import hashlib
import gzip
import io
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.join(HERE, "sources.json")
ARTICLES = os.path.join(HERE, "articles.json")
INBOX = os.path.join(HERE, "inbox.json")

JST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# python.org 版 Python は証明書ストアを別に持つので、ローカル実行で
# こけたときだけ KIOSK_INSECURE_SSL=1 で回避できるようにしておく
_SSL = ssl._create_unverified_context() if os.environ.get("KIOSK_INSECURE_SSL") else None


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

def http_get(url, timeout=30):
    req = Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5",
        "Accept-Language": "ja,en;q=0.8",
        "Accept-Encoding": "gzip",
    })
    with urlopen(req, timeout=timeout, context=_SSL) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        charset = None
        ctype = r.headers.get("Content-Type", "")
        m = re.search(r"charset=([\w-]+)", ctype, re.I)
        if m:
            charset = m.group(1)
        final_url = r.geturl()
    if not charset:
        m = re.search(rb'encoding=["\']([\w-]+)["\']', raw[:200])
        if m:
            charset = m.group(1).decode("ascii", "ignore")
    if not charset:
        m = re.search(rb'charset=["\']?([\w-]+)', raw[:2000], re.I)
        if m:
            charset = m.group(1).decode("ascii", "ignore")
    text = raw.decode(charset or "utf-8", "replace")
    return text, final_url


# --------------------------------------------------------------------------
# HTML → 段落
# --------------------------------------------------------------------------

_BLOCK = re.compile(r"</?(p|div|br|h[1-6]|li|tr|blockquote|figcaption|section)\b[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")


def html_to_paragraphs(html):
    """記事HTMLを段落の配列にする。タグは全部落とすのでそのまま表示して安全。"""
    if not html:
        return []
    s = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html)
    # Substack のシェアボタンは読むのに邪魔。note の「続きをみる」は
    # 「ここから先はサイトで」の印なので残し、_CUTOFF に拾わせる
    s = re.sub(r"(?is)<[^>]*class=\"[^\"]*button-wrapper[^\"]*\"[^>]*>.*?</[^>]+>", " ", s)
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub("", s)
    s = unescape(s)
    s = s.replace(" ", " ")
    out = []
    for line in s.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            continue
        # Substack の定型フッターや購読ボタンの残骸を落とす
        if re.fullmatch(r"(シェア|Share|Leave a comment|コメント|購読|Subscribe now?)", line, re.I):
            continue
        out.append(line)
    return out


def unescape(s):
    import html as _h
    return _h.unescape(s)


# 無料で読めるのはここまで、を示す末尾の文言
_CUTOFF = re.compile(r"^(Read more|続きをみる|続きを読む|この続きをみるには|Continue reading.*)$", re.I)


def clip_paragraphs(paras, limit):
    """合計文字数が limit を超えないところまで段落を採る。"""
    out, total = [], 0
    for p in paras:
        if out and total + len(p) > limit:
            return out, True
        out.append(p)
        total += len(p)
        if total >= limit:
            return out, len(out) < len(paras)
    return out, False


def first_img(html):
    if not html:
        return ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------
# フィードの解析
# --------------------------------------------------------------------------

def localname(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def child(el, name):
    for c in el:
        if localname(c.tag) == name:
            return c
    return None


def children(el, name):
    return [c for c in el if localname(c.tag) == name]


def text_of(el, name):
    c = child(el, name)
    if c is None:
        return ""
    return "".join(c.itertext()).strip()


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def parse_feed(xml_text, feed_url):
    """RSS 2.0 / Atom を共通の dict の配列にする。"""
    xml_text = xml_text.lstrip("﻿ \t\r\n")
    root = ET.fromstring(xml_text)
    tag = localname(root.tag)

    if tag == "rss":
        ch = child(root, "channel")
        if ch is None:
            return "", []
        feed_title = text_of(ch, "title")
        entries = children(ch, "item")
        kind = "rss"
    elif tag == "feed":
        feed_title = text_of(root, "title")
        entries = children(root, "entry")
        kind = "atom"
    else:
        ch = child(root, "channel")            # RSS 1.0 (RDF)
        feed_title = text_of(ch, "title") if ch is not None else ""
        entries = children(root, "item")
        kind = "rss"

    items = []
    for e in entries:
        title = text_of(e, "title")

        if kind == "atom":
            link = ""
            for ln in children(e, "link"):
                rel = ln.get("rel") or "alternate"
                if rel == "alternate":
                    link = ln.get("href") or ""
                    break
            if not link:
                link = text_of(e, "id")
            date_raw = text_of(e, "published") or text_of(e, "updated")
            summary_html = text_of(e, "summary")
            content_html = text_of(e, "content")
        else:
            link = text_of(e, "link") or text_of(e, "guid")
            date_raw = text_of(e, "pubDate") or text_of(e, "date")
            summary_html = text_of(e, "description")
            content_html = text_of(e, "encoded")   # content:encoded

        # media:thumbnail は note のように「URLを要素の中身に書く」流儀もある
        image = ""
        for name, attr in (("thumbnail", "url"), ("content", "url"),
                           ("enclosure", "url"), ("image", "href")):
            c = child(e, name)
            if c is None:
                continue
            if name == "enclosure" and not (c.get("type") or "").startswith("image"):
                continue
            if name == "content" and not (c.get("type") or "image").startswith("image"):
                continue
            val = c.get(attr) or ("".join(c.itertext()).strip())
            if val.startswith("http"):
                image = val
                break
        if not image:
            image = first_img(content_html) or first_img(summary_html)

        author = text_of(e, "creatorName") or text_of(e, "creator") or ""
        if not author:
            a = child(e, "author")
            if a is not None:
                author = text_of(a, "name") or ("".join(a.itertext()).strip())

        dt = parse_date(date_raw)
        items.append({
            "title": unescape(title).strip(),
            "url": urljoin(feed_url, link.strip()) if link else "",
            "date": dt.astimezone(timezone.utc).isoformat() if dt else "",
            "image": image,
            "author": unescape(author).strip(),
            "_summary_html": summary_html,
            "_content_html": content_html,
        })
    return feed_title, items


def make_id(url, title=""):
    return hashlib.sha1((url or title).encode("utf-8")).hexdigest()[:12]


def build_article(raw, source_id, limit):
    body_html = raw["_content_html"] if len(raw["_content_html"]) > len(raw["_summary_html"]) \
        else raw["_summary_html"]
    paras = html_to_paragraphs(body_html)
    paywalled = bool(paras) and bool(_CUTOFF.match(paras[-1]))
    if paywalled:
        paras = paras[:-1]
    body, truncated = clip_paragraphs(paras, limit)
    truncated = truncated or paywalled
    lead = raw["_summary_html"]
    if len(html_to_paragraphs(lead)) == 1 and len(html_to_paragraphs(lead)[0]) < 200:
        subtitle = html_to_paragraphs(lead)[0]
    else:
        subtitle = ""
    if subtitle and body and body[0].startswith(subtitle[:20]):
        subtitle = ""
    return {
        "id": make_id(raw["url"], raw["title"]),
        "source": source_id,
        "title": raw["title"],
        "url": raw["url"],
        "date": raw["date"],
        "image": raw["image"],
        "author": raw["author"],
        "subtitle": subtitle,
        "body": body,
        "truncated": truncated,
    }


# --------------------------------------------------------------------------
# URL からフィードを見つける（アプリの「追加」用）
# --------------------------------------------------------------------------

FEED_LINK = re.compile(
    r'<link[^>]+(?:rel=["\']alternate["\'][^>]*type=["\'](?:application/(?:rss|atom)\+xml)["\']'
    r'|type=["\'](?:application/(?:rss|atom)\+xml)["\'][^>]*rel=["\']alternate["\'])[^>]*>',
    re.I)


def guess_feed_urls(url):
    """よく使うサービスは HTML を読まずに直接あてる。"""
    p = urlparse(url)
    host, path = p.netloc.lower(), p.path
    out = []
    if host.endswith("note.com"):
        m = re.match(r"^/([^/]+)", path)
        if m and m.group(1) not in ("api", "search", "hashtag"):
            out.append(f"https://note.com/{m.group(1)}/rss")
    if host.endswith("substack.com"):
        out.append(f"{p.scheme}://{host}/feed")
    if host.endswith("hatenablog.com") or host.endswith("hatenadiary.jp"):
        out.append(f"{p.scheme}://{host}/rss")
    if host.endswith("medium.com"):
        m = re.match(r"^/(@[^/]+)", path)
        if m:
            out.append(f"https://medium.com/feed/{m.group(1)}")
    return out


def discover_feed(url):
    """URL から購読できるフィードを探す。見つからなければ ('', html, final_url)。"""
    for cand in guess_feed_urls(url):
        try:
            txt, final = http_get(cand, timeout=20)
            parse_feed(txt, final)
            return cand, "", final
        except Exception:
            pass
    try:
        txt, final = http_get(url, timeout=25)
    except Exception as e:
        return "", "", "!" + str(e)
    head = txt[:200].lstrip()
    if head.startswith("<?xml") or "<rss" in txt[:1000] or "<feed" in txt[:1000]:
        try:
            parse_feed(txt, final)
            return final, "", final
        except Exception:
            pass
    for tag in FEED_LINK.findall(txt):
        m = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
        if not m:
            continue
        cand = urljoin(final, unescape(m.group(1)))
        try:
            ftxt, ffinal = http_get(cand, timeout=20)
            parse_feed(ftxt, ffinal)
            return cand, "", ffinal
        except Exception:
            continue
    return "", txt, final


def meta_of(html, *names):
    for n in names:
        m = re.search(
            r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']*)["\']' % re.escape(n),
            html, re.I)
        if not m:
            m = re.search(
                r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']%s["\']' % re.escape(n),
                html, re.I)
        if m and m.group(1).strip():
            return unescape(m.group(1)).strip()
    return ""


def article_from_html(html, url, limit):
    title = meta_of(html, "og:title", "twitter:title")
    if not title:
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        title = unescape(m.group(1)).strip() if m else url
    image = meta_of(html, "og:image", "twitter:image")
    desc = meta_of(html, "og:description", "description")
    site = meta_of(html, "og:site_name")
    if site:
        title = re.sub(r"\s*[|｜\-–—]\s*" + re.escape(site) + r"\s*$", "", title)
    published = meta_of(html, "article:published_time", "og:updated_time")

    body = []
    m = re.search(r"(?is)<article\b[^>]*>(.*?)</article>", html)
    if m:
        body = html_to_paragraphs(m.group(1))
    body = [p for p in body if len(p) > 20]
    if not body and desc:
        body = [desc]
    body, truncated = clip_paragraphs(body, limit)

    dt = parse_date(published)
    return {
        "id": make_id(url, title),
        "source": "inbox",
        "title": title,
        "url": url,
        "date": dt.astimezone(timezone.utc).isoformat() if dt else
                datetime.now(timezone.utc).isoformat(),
        "image": image,
        "author": site,
        "subtitle": desc if desc and (not body or not body[0].startswith(desc[:20])) else "",
        "body": body,
        "truncated": truncated,
    }


# --------------------------------------------------------------------------
# 読み書き
# --------------------------------------------------------------------------

def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def slug(name, taken):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:20] or "src"
    base, i = s, 2
    while s in taken:
        s, i = f"{base}-{i}", i + 1
    return s


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def process_inbox(cfg, articles, limit_default):
    """アプリから投げ込まれたURLを、購読ソースか単発記事にする。"""
    inbox = load(INBOX, {"queue": []})
    queue = inbox.get("queue") or []
    if not queue:
        return False, []

    taken = {s["id"] for s in cfg["sources"]}
    known_feeds = {s["url"] for s in cfg["sources"]}
    known_urls = {a["url"] for a in articles}
    notes, changed = [], False

    for entry in queue:
        url = (entry.get("url") or "").strip()
        if not url:
            continue
        if not url.startswith("http"):
            url = "https://" + url
        want = entry.get("as") or "auto"     # "auto" | "feed" | "article"
        print(f"  inbox: {url} ({want})")

        try:
            if want == "article":
                html, final = http_get(url, timeout=25)
                feed = ""
            else:
                feed, html, final = discover_feed(url)
        except Exception as e:
            notes.append({"url": url, "ok": False, "message": f"取得できませんでした: {e}"})
            continue

        if feed and want != "article":
            if feed in known_feeds:
                notes.append({"url": url, "ok": True, "message": "すでに購読しています"})
                continue
            try:
                txt, ffinal = http_get(feed, timeout=25)
                name, items = parse_feed(txt, ffinal)
            except Exception as e:
                notes.append({"url": url, "ok": False, "message": f"フィードを読めませんでした: {e}"})
                continue
            sid = slug(name or urlparse(feed).netloc, taken)
            taken.add(sid)
            known_feeds.add(feed)
            cfg["sources"].append({
                "id": sid,
                "name": (name or urlparse(feed).netloc)[:40],
                "url": feed,
                "site": feed[:-4] if feed.endswith("/rss") else
                        (feed[:-5] if feed.endswith("/feed") else
                         f"{urlparse(final or url).scheme}://{urlparse(final or url).netloc}"),
                "hue": (abs(hash(sid)) % 36) * 10,
                "enabled": True,
            })
            changed = True
            notes.append({"url": url, "ok": True,
                          "message": f"「{name or sid}」を購読に追加しました（{len(items)}件）"})
            continue

        # フィードが無い → 単発の記事として取り込む
        if not html:
            why = final[1:] if isinstance(final, str) and final.startswith("!") else ""
            notes.append({"url": url, "ok": False,
                          "message": ("ページを開けませんでした（%s）" % why) if why else
                                     "フィードも本文も取れませんでした。本文を貼り付けてください"})
            continue
        art = article_from_html(html, final or url, limit_default)
        if art["url"] in known_urls:
            notes.append({"url": url, "ok": True, "message": "すでに取り込み済みです"})
            continue
        if not art["body"]:
            notes.append({"url": url, "ok": False,
                          "message": "本文を読めませんでした（ログインが要る記事かもしれません）"})
            continue
        articles.append(art)
        known_urls.add(art["url"])
        changed = True
        notes.append({"url": url, "ok": True, "message": f"記事「{art['title'][:24]}」を追加しました"})

    inbox["queue"] = []
    inbox["last_result"] = notes
    inbox["processed_at"] = datetime.now(timezone.utc).isoformat()
    save(INBOX, inbox)
    return changed, notes


def main():
    dry = "--dry" in sys.argv
    inbox_only = "--inbox" in sys.argv

    cfg = load(SOURCES, {"sources": []})
    limit_default = int(cfg.get("excerpt_chars_default", 1500))
    keep = int(cfg.get("keep_per_source", 60))

    store = load(ARTICLES, {"articles": []})
    articles = store.get("articles", [])
    by_id = {a["id"]: a for a in articles}

    cfg_changed, notes = process_inbox(cfg, articles, limit_default)
    if notes:
        by_id = {a["id"]: a for a in articles}
    if cfg_changed and not dry:
        save(SOURCES, cfg)

    if not inbox_only:
        for s in cfg["sources"]:
            if s.get("enabled") is False:
                continue
            limit = int(s.get("excerpt_chars", limit_default))
            try:
                txt, final = http_get(s["url"])
                _, items = parse_feed(txt, final)
            except (URLError, HTTPError, ET.ParseError, Exception) as e:
                print(f"  ! {s['name']}: {e}")
                continue
            fresh = 0
            for raw in items:
                if not raw["url"] or not raw["title"]:
                    continue
                art = build_article(raw, s["id"], limit)
                if art["id"] in by_id:
                    old = by_id[art["id"]]
                    old.update({k: v for k, v in art.items() if v or k in ("truncated",)})
                else:
                    articles.append(art)
                    by_id[art["id"]] = art
                    fresh += 1
            print(f"  {s['name']}: {len(items)}件（新着 {fresh}）")
            time.sleep(0.6)

    # 日付の新しい順、ソースごとに keep 件まで
    articles.sort(key=lambda a: a.get("date") or "", reverse=True)
    counts, kept = {}, []
    for a in articles:
        n = counts.get(a["source"], 0)
        if a["source"] != "inbox" and n >= keep:
            continue
        counts[a["source"]] = n + 1
        kept.append(a)

    out = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "sources": [{k: v for k, v in s.items() if k != "url"} for s in cfg["sources"]],
        "articles": kept,
    }
    print(f"合計 {len(kept)} 件 / ソース {len(cfg['sources'])}")
    if dry:
        for a in kept[:8]:
            print(f"  [{a['source']}] {a['date'][:10]} {a['title'][:50]}")
        return
    save(ARTICLES, out)


if __name__ == "__main__":
    main()
