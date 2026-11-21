"""Estrazione prudente dei soli metadati pubblici degli articoli (no paywall)."""
import hashlib
import html
import re
import sys
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

class PublicHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.meta = {}
        self.text = []
        self.before_h1 = ""
        self.h1 = ""
        self._anchor = None
        self._h1 = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag == "meta":
            key = attrs.get("property", attrs.get("name", "")).lower()
            if key in ("article:published_time", "datepublished", "og:title",
                       "date", "citation_publication_date"):
                self.meta[key] = attrs.get("content", "")
        if tag == "a":
            self._anchor = [attrs.get("href", ""), []]
        if tag == "h1":
            self._h1 = True
            self.before_h1 = " ".join(self.text[-60:])

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag == "a" and self._anchor:
            href, words = self._anchor
            title = " ".join(" ".join(words).split())
            if href and title:
                self.links.append((href, title))
            self._anchor = None
        if tag == "h1":
            self._h1 = False

    def handle_data(self, data):
        if self._skip or not data.strip():
            return
        value = data.strip()
        self.text.append(value)
        if self._anchor is not None:
            self._anchor[1].append(value)
        if self._h1:
            self.h1 += " " + value

def public_article_urls(html_bytes, site, classifier):
    page = PublicHtml()
    page.feed(html_bytes.decode("utf-8", "replace"))
    out = []
    seen = set()
    for href, label in page.links:
        url = urljoin("https://" + site + "/", href)
        p = urlsplit(url)
        if p.scheme != "https" or p.hostname != site or url in seen:
            continue
        path = p.path.lower()
        if site == "www.ecnews.it":
            if not (path.startswith("/fiscale/") or path.startswith("/lavoro/")):
                continue
            if len(path.strip("/").split("/")) < 4:
                continue
            if any(fragment in path for fragment in ("/category/", "/autore/", "/tag/")):
                continue
        else:
            if not path.startswith("/c/") or len(path.strip("/").split("/")) < 3:
                continue
            if any(fragment in path for fragment in ("/video/", "/statici/", "/info-video/")):
                continue
        if len(label) < 18 or not classifier(label):
            continue
        seen.add(url)
        out.append((url, label))
        if len(out) >= 12:
            break
    return out

def parse_public_article(content, url, source, now, classifier, get_date):
    page = PublicHtml()
    page.feed(content.decode("utf-8", "replace"))
    title = html.unescape(page.h1.strip() or page.meta.get("og:title", "")).strip()[:180]
    for suffix in (" - Redazione Fiscale", " - EC News - Area fiscale", " - EC News - Area lavoro"):
        if title.endswith(suffix):
            title = title[:-len(suffix)]
    published = (page.meta.get("article:published_time") or
                 page.meta.get("datepublished") or
                 page.meta.get("citation_publication_date"))
    date = get_date(published)
    if date is None and source == "Redazione Fiscale":
        nearby = page.before_h1[-250:]
        match = re.search(r"\b([0-3]?\d/[01]?\d/20\d{2})\b", nearby)
        if match:
            try:
                date = datetime.strptime(match.group(1), "%d/%m/%Y").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    category = classifier(title)
    if not title or not category or not date or not timedelta(hours=-6) <= now - date <= timedelta(days=10):
        return None
    return {"id": hashlib.sha256(url.encode()).hexdigest()[:18],
            "title": title, "url": url, "source": source,
            "published_at": date.isoformat(timespec="seconds"),
            "category": category, "status": "link_esterno_da_verificare"}

def collect_public_site(fetcher, source, homepage, domain, now, classifier, get_date):
    origin = urlsplit(homepage)
    if origin.scheme != "https" or origin.hostname != domain:
        raise ValueError("Homepage non autorizzata")
    found = []
    for url, _ in public_article_urls(fetcher(homepage), domain, classifier):
        try:
            record = parse_public_article(fetcher(url), url, source, now, classifier, get_date)
            if record:
                found.append(record)
        except (ValueError, OSError, TimeoutError) as exc:
            print(f"Articolo non disponibile {source}: {type(exc).__name__}", file=sys.stderr)
    return found
