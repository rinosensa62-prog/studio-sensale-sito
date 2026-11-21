#!/usr/bin/env python3
"""Raccoglie SOLO spunti editoriali dalle testate specialistiche.
I titoli NON alimentano automaticamente il sito pubblico: richiedono
verifica dei provvedimenti e redazione originale prima della pubblicazione.
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "spunti-editoriali.json"
# Feed RSS reperiti dalla pagina RSS pubblica di Fiscal Focus.
FEEDS = (
    ("Fiscal Focus", "https://www.fiscal-focus.it/rss/news24.rss", "fiscal-focus.it"),
    ("Fisco e Tasse", "https://www.fiscoetasse.com/feed", "fiscoetasse.com"),
    ("Informazione Fiscale", "https://www.informazionefiscale.it/spip.php?page=backend", "informazionefiscale.it"),
    ("IPSOA Fisco", "https://www.ipsoa.it/RSS-Feeds/Fisco.aspx", "ipsoa.it"),
    ("IPSOA Impresa", "https://www.ipsoa.it/RSS-Feeds/Impresa.aspx", "ipsoa.it"),
)
# Le altre testate sono nel monitoraggio editoriale ChatGPT.
# Non inventiamo indirizzi RSS: prima vanno verificati e testati.
OTHER_SOURCES = (
    
    
    ("Euroconference News", "https://www.ecnews.it/"),
    ("Eutekne", "https://www.eutekne.info/"),
    ("IPSOA - aree ulteriori", "https://www.ipsoa.it/"),
    ("Redazione Fiscale", "https://www.redazionefiscale.it/"),
    ("LavoroSì", "https://www.lavorosi.it/"),
)
EXCLUDE = re.compile(r'\b(concorso|selezione comparativa|offerta di lavoro|evento formativo|webinar|corso a pagamento)\b', re.I)
KEYWORDS = re.compile(
    r'\b(iva|irpef|ires|irap|isee|caf|730|fisco|fiscal|impost|credit|agevol|bonus|contribut|'
    r'assunzion|lavor|pension|inps|inail|band|incentiv|rottamazion|'
    r'fattur|locazion|succession|partita|dichiarazion|scadenz|tribut|forfettari|'
    r'adempiment|finanziament|detrazion|cedolar|tari|imu)\w*', re.I)

def simple(tag):
    return tag.rsplit("}", 1)[-1].lower()

def field(node, names):
    for child in node:
        if simple(child.tag) in names:
            if child.text and child.text.strip():
                return child.text.strip()
            if simple(child.tag) == "link" and child.attrib.get("href"):
                return child.attrib["href"].strip()
    return ""

def get_date(raw):
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (ValueError, TypeError, IndexError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)

def parse(xml_bytes, source, now):
    root = ET.fromstring(xml_bytes)
    found = []
    for item in root.iter():
        if simple(item.tag) not in ("item", "entry"):
            continue
        title = re.sub(r"\s+", " ", field(item, ("title",)))[:180].strip()
        url = field(item, ("link",))
        date = get_date(field(item, ("pubdate", "published", "updated", "date")))
        host = (urlsplit(url).hostname or "").lower()
        if (not title or not url.startswith("https://") or
            host != source[2] and not host.endswith("." + source[2]) or
            not date or not timedelta(hours=-6) <= now-date <= timedelta(days=10) or
            EXCLUDE.search(title) or not KEYWORDS.search(title)):
            continue
        found.append({"id": hashlib.sha256(url.encode()).hexdigest()[:18],
                      "title": title, "url": url, "source": source[0],
                      "published_at": date.isoformat(timespec="seconds"),
                      "status": "spunto_da_verificare"})
    return found

def fetch(url):
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 (StudioSensaleEditorialMonitor/1.0)",
                                "Accept":"application/rss+xml,application/xml,text/xml,*/*"})
    with urlopen(req, timeout=12) as resp:
        data = resp.read(1_000_001)
    if len(data)>1_000_000:
        raise ValueError("feed troppo grande")
    return data

def build(fetcher=fetch, now=None):
    now = now or datetime.now(timezone.utc)
    entries, ok, failed = [], [], []
    for feed in FEEDS:
        try:
            items = parse(fetcher(feed[1]), feed, now)
            entries.extend(items)
            ok.append(feed[0])
        except Exception as exc:
            failed.append(feed[0])
            print(f"Spunti RSS non disponibili {feed[0]}: {type(exc).__name__}", file=sys.stderr)
    unique = {v["id"]:v for v in sorted(entries,key=lambda x:x["published_at"])}
    return {"updated_at": now.isoformat(timespec="seconds"),
            "publication_mode":"solo_revisione_editoriale_non_pubblicare_sul_sito",
            "items":sorted(unique.values(),key=lambda x:x["published_at"],reverse=True)[:40],
            "feeds_ok":ok,"feeds_failed":failed,
            "other_sources":[{"name":n,"url":u,"mode":"monitoraggio_editoriale"} for n,u in OTHER_SOURCES]}
if __name__ == "__main__":
    value = build()
    if not value["feeds_ok"]:
        raise SystemExit("Nessun feed specialistico raggiungibile: preservo l'archivio precedente")
    if OUTPUT.exists():
        old=json.loads(OUTPUT.read_text(encoding="utf-8"))
        if {k:v for k,v in value.items() if k!="updated_at"} == {k:v for k,v in old.items() if k!="updated_at"}:
            print("Spunti specialistici invariati")
            raise SystemExit(0)
    OUTPUT.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Spunti specialistici aggiornati: {len(value['items'])}")
