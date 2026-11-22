#!/usr/bin/env python3
"""Prepara un aggiornamento Netlify preservando le pagine del sito pubblico.

Non esegue un deploy; produce una cartella e uno ZIP da caricare sul sito Netlify
esistente. Scarica solo URL appartenenti a studiosensale.it e controllati.
"""
from __future__ import annotations

import html.parser
import json
import os
from pathlib import Path
from urllib.parse import urljoin, urlsplit, unquote
from urllib.request import Request, urlopen
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = "https://studiosensale.it/"
HOST = "studiosensale.it"
BASE = Path(__file__).resolve().parent.parent
OUTPUT = BASE / "dist-studio-sensale"
ZIPFILE = BASE / "studio-sensale-notizie-live.zip"
JS = BASE / "frontend" / "studio-news-live.js"
HOOK = '<script src="/assets/studio-news-live.js" defer></script>'
MAX_FILE = 6_000_000

class Assets(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "img", "source"):
            src = a.get("src") or a.get("srcset")
            if src:
                self.links.append(src.split(" ")[0].split(",")[0])
        if tag == "link" and a.get("href"):
            self.links.append(a["href"])

def request(url):
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; StudioSensaleMirror/1.0)",
        "Accept": "*/*"
    })
    with urlopen(req, timeout=35) as resp:
        if urlsplit(resp.url).hostname != HOST:
            raise ValueError("Redirect esterno inatteso: " + url)
        content = resp.read(MAX_FILE + 1)
        if len(content) > MAX_FILE:
            raise ValueError("File troppo grande: " + url)
        return content

def safe_path(url):
    full = urlsplit(urljoin(ROOT, url))
    if full.scheme != "https" or full.hostname != HOST:
        return None
    path = unquote(full.path)
    if "\\" in path or ".." in path.split("/") or "\x00" in path:
        raise ValueError("Path non sicuro: " + path)
    rel = path.lstrip("/")
    if not rel or rel.endswith("/"):
        rel += "index.html"
    return rel

def write(url, content, *, inject=False):
    rel = safe_path(url)
    if not rel:
        return
    dest = OUTPUT / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if inject:
        markup = content.decode("utf-8")
        if HOOK not in markup:
            if "</body>" not in markup.lower():
                raise ValueError("HTML senza body: " + url)
            markup = re.sub(r"</body>", HOOK + "\n</body>", markup, count=1, flags=re.I)
        content = markup.encode("utf-8")
    dest.write_bytes(content)
    return dest

def run():
    if not JS.exists():
        raise FileNotFoundError(JS)
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    sitemap = request(ROOT + "sitemap.xml")
    root = ET.fromstring(sitemap)
    urls = sorted({e.text.strip() for e in root.iter()
                   if e.tag.endswith("loc") and e.text
                   and safe_path(e.text)})
    if len(urls) < 45:
        raise RuntimeError("Sitemap incompleta: interrompo per evitare deploy distruttivo")
    urls = sorted(set(urls) | {ROOT, ROOT + "notizie/"})
    extras = set()
    page_failures = []
    for url in urls:
        try:
            page = request(url)
            write(url, page, inject=True)
            parser = Assets()
            parser.feed(page.decode("utf-8", "replace"))
            extras.update(urljoin(url, x) for x in parser.links)
        except Exception as exc:
            page_failures.append((url, str(exc)))
    if page_failures:
        raise RuntimeError("Alcune pagine del sito non sono state scaricate: " + json.dumps(page_failures[:6]))
    asset_count = 0
    for url in sorted(extras):
        path = safe_path(url)
        if not path or path.endswith("/index.html") or not re.search(
            r"\.(?:css|js|png|jpe?g|webp|gif|svg|ico|woff2?|ttf|otf|avif|json)$", path, re.I):
            continue
        if (OUTPUT / path).exists():
            continue
        try:
            write(url, request(url))
            asset_count += 1
        except Exception as exc:
            # Asset essenziale non presente: non si procede con un deploy potenzialmente rotto.
            raise RuntimeError("Asset non scaricabile " + url + ": " + str(exc))
    target = OUTPUT / "assets/studio-news-live.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(JS, target)
    if len(list(OUTPUT.rglob("index.html"))) < 45:
        raise RuntimeError("Mirror incompleto, ZIP non creato")
    if not (OUTPUT / "assets/style.css").exists():
        # Il foglio di stile potrebbe avere un nome diverso: serve almeno un CSS in output.
        if not list(OUTPUT.rglob("*.css")):
            raise RuntimeError("CSS assente, ZIP non creato")
    # Non aggiungere redirect che potrebbero cambiare il routing del sito.
    # I dati restano ospitati su GitHub, quindi non serve un nuovo deploy quotidiano.
    with zipfile.ZipFile(ZIPFILE, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(OUTPUT.rglob("*")):
            if file.is_file():
                z.write(file, file.relative_to(OUTPUT).as_posix())
    print(json.dumps({
        "result": "ready_for_manual_Netlify_deploy",
        "pages": len(urls),
        "assets": asset_count,
        "zip": ZIPFILE.name,
        "bytes": ZIPFILE.stat().st_size,
        "live_news_script": "assets/studio-news-live.js",
        "site_unchanged": True
    }, indent=2))

if __name__ == "__main__":
    run()
