#!/usr/bin/env python3
"""Raccoglie SOLO spunti editoriali dalle testate specialistiche.
I titoli NON alimentano automaticamente il sito pubblico: richiedono
verifica dei provvedimenti e redazione originale prima della pubblicazione.
"""
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
try:
    from fonti_web_pubbliche import collect_public_site
    from verifica_accesso_gratuito import articolo_gratuito
except ImportError:
    from scripts.fonti_web_pubbliche import collect_public_site
    from scripts.verifica_accesso_gratuito import articolo_gratuito

OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "spunti-editoriali.json"
# Feed RSS reperiti dalla pagina RSS pubblica di Fiscal Focus.
FEEDS = (
    ("Fiscal Focus", "https://www.fiscal-focus.it/rss/news24.rss", "fiscal-focus.it"),
    ("Fisco e Tasse", "https://www.fiscoetasse.com/feed", "fiscoetasse.com"),
    ("Informazione Fiscale", "https://www.informazionefiscale.it/spip.php?page=backend", "informazionefiscale.it"),
    ("IPSOA Fisco", "https://www.ipsoa.it/RSS-Feeds/Fisco.aspx", "ipsoa.it"),
    ("IPSOA Impresa", "https://www.ipsoa.it/RSS-Feeds/Impresa.aspx", "ipsoa.it"),
    ("LavoroSì", "https://www.lavorosi.it/feed/", "lavorosi.it"),
    ("Eutekne", "https://www.eutekne.info/Rss.ashx", "eutekne.info"),
)
# Fonti con RSS non utilizzabile: si controllano soltanto titoli/date/link pubblici.
HTML_SOURCES = (
    ('Euroconference News', 'https://www.ecnews.it/', 'www.ecnews.it'),
    ('Redazione Fiscale', 'https://www.redazionefiscale.it/', 'www.redazionefiscale.it'),
)
# Le altre testate sono nel monitoraggio editoriale ChatGPT.
# Non inventiamo indirizzi RSS: prima vanno verificati e testati.
OTHER_SOURCES = (
    
    
    ("IPSOA - aree ulteriori", "https://www.ipsoa.it/"),
)
EXCLUDE = re.compile(r'\b(concorso|selezione comparativa|offerta di lavoro|evento formativo|webinar|corso a pagamento)\b', re.I)
KEYWORDS = re.compile(
    r'\b(iva|irpef|ires|irap|isee|caf|730|fisco|fiscal|impost|credit|agevol|bonus|contribut|'
    r'assunzion|lavor|pension|inps|inail|band|incentiv|rottamazion|'
    r'fattur|locazion|succession|partita|dichiarazion|scadenz|tribut|forfettari|'
    r'adempiment|finanziament|detrazion|cedolar|tari|imu)\w*', re.I)


# L'argomento determina la sezione, mai la testata che pubblica la notizia.
CATEGORIES = (
    "Bandi e finanziamenti", "Aprire e gestire un’attività", "Lavoro e paghe",
    "Famiglie e CAF", "Dichiarazioni e Fisco", "Locazioni e immobili",
    "Successioni e tributi locali",
)
# Esclusione editoriale esplicita: notifiche SEND/indebiti INPS.
EXCLUDED_NEWS = re.compile(
    r'(?:indebit\w*.{0,80}(?:notific\w*|send)|(?:notific\w*|send).{0,80}indebit\w*)', re.I
)
CATEGORY_PATTERNS = (
    ("Successioni e tributi locali",
     r'\b(?:succession\w*|eredit\w*|eredi|volture ereditarie|imu|tari|tasi|'
     r'imposta provinciale di trascrizione|tributi locali)\b'),
    ("Locazioni e immobili",
     r'\b(?:locazion\w*|affitt\w*|cedolare secca|immobil\w*|catast\w*|'
     r'prima casa|ecobonus|ristrutturazion\w*|fabbricat\w*|tupini)\b'),
    ("Famiglie e CAF",
     r'\b(?:isee|dsu|730|bonus mamm\w*|assegno unico|assegno di inclusione|'
     r'ape sociale|pension\w*|pensionat\w*|invalidit\w*|disabilit\w*|'
     r'famigli\w*|sipp)\b'),
    ("Lavoro e paghe",
     r'\b(?:assunzion\w*|dipendent\w*|contributi|contributiv\w*|conged\w*|'
     r'welfare aziendale|uniemens|fringe benefit|siisl|inail|inps|'
     r'distacch\w*|retribuzion\w*|lavorator\w*|lavoro subordinato|'
     r'cu \d{4}|fondo solidariet\w*)\b'),
    ("Bandi e finanziamenti",
     r'\b(?:band\w*|incentiv\w*|fondo perduto|finanziament\w*|voucher\w*|'
     r'fotovoltaico|agevolazion\w*|credit\w* d.imposta|contributi fino|'
     r'fondo di garanzia|fond\w* PMI)\b'),
    ("Aprire e gestire un’attività",
     r'\b(?:partita iva|regime forfettario|forfettari\w*|crisi d.impresa|'
     r'liquidazione controllata|impres\w*|societ\w*|s\.n\.c\.?|'
     r'scissione societaria|professionist\w*|costituzione societ\w*)\b'),
    ("Dichiarazioni e Fisco",
     r'\b(?:fisco|fiscal\w*|iva|irpef|ires|irap|impost\w*|fattur\w*|'
     r'dichiarazion\w*|redditi|ritenut\w*|versament\w*|f24|'
     r'rottamazion\w*|tributar\w*|detrazion\w*|rimborso iva|'
     r'autotutela|compliance|crediti fiscali)\b'),
)

def classify(title):
    """Una sola delle sette categorie; un titolo ambiguo rimane fuori dal sito."""
    if not isinstance(title, str) or EXCLUDED_NEWS.search(title) or EXCLUDE.search(title):
        return None
    for category, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, title, re.I):
            return category
    return None

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
        title = re.sub(r"\s+", " ", field(item, ("title",))).strip()
        # Eutekne può racchiudere il titolo in un CDATA sfuggito come testo XML.
        if title.startswith("<![CDATA[") and title.endswith("]]>"):
            title = title[9:-3].strip()
        title = html.unescape(title)[:180]
        url = field(item, ("link",))
        date = get_date(field(item, ("pubdate", "published", "updated", "date")))
        host = (urlsplit(url).hostname or "").lower()
        if (not title or not url.startswith("https://") or
            host != source[2] and not host.endswith("." + source[2]) or
            not date or not timedelta(hours=-6) <= now-date <= timedelta(days=10) or
            not classify(title)):
            continue
        found.append({"id": hashlib.sha256(url.encode()).hexdigest()[:18],
                      "title": title, "url": url, "source": source[0],
                      "published_at": date.isoformat(timespec="seconds"),
                      "category": classify(title),
                      "status": "link_esterno_da_verificare"})
    return found

def fetch(url):
    req = Request(url, headers={"User-Agent":"Mozilla/5.0 (StudioSensaleEditorialMonitor/1.0)",
                                "Accept":"application/rss+xml,application/xml,text/xml,*/*"})
    with urlopen(req, timeout=12) as resp:
        data = resp.read(1_000_001)
    if len(data)>1_000_000:
        raise ValueError("feed troppo grande")
    return data

def build(fetcher=fetch, now=None, previous=None, verify=articolo_gratuito):
    now = now or datetime.now(timezone.utc)
    entries, ok, failed = [], [], []
    for feed in FEEDS:
        try:
            items = parse(fetcher(feed[1]), feed, now)
            entries.extend(items)
            ok.append(feed[0])
        except Exception as exc:
            failed.append(feed[0])
            print(f"RSS specializzato non disponibile {feed[0]}: {type(exc).__name__}", file=sys.stderr)

    for source, homepage, domain in HTML_SOURCES:
        try:
            selected = collect_public_site(fetcher, source, homepage, domain, now, classify, get_date)
            entries.extend(selected)
            ok.append(source)
            print(f'{source}: {len(selected)} titoli verificati con data', file=sys.stderr)
        except Exception as exc:
            failed.append(source)
            print(f'Pagine pubbliche non disponibili {source}: {type(exc).__name__}: {exc}', file=sys.stderr)

    # Archivio persistente: non cancellare notizie storiche quando scadono dal feed.
    previous = previous or {}
    allowed_sources = {feed[0]: feed[2] for feed in FEEDS + HTML_SOURCES}
    for item in previous.get("items", []):
        if not isinstance(item, dict) or item.get("source") not in allowed_sources:
            continue
        title = item.get("title")
        category = classify(title)
        url = item.get("url", "")
        date = get_date(item.get("published_at", ""))
        try:
            host = (urlsplit(url).hostname or "").lower()
        except (TypeError, ValueError):
            continue
        origin = allowed_sources[item["source"]]
        if (not category or not date or not isinstance(url, str) or
            not url.startswith("https://") or
            not (host == origin or host.endswith("." + origin))):
            continue
        record = dict(item)
        record["category"] = category
        record["status"] = "in_attesa_verifica_gratuita"
        entries.append(record)
    # Non basta che la fonte esponga un RSS: ogni link va aperto da anonimo.
    # Il filtro e' applicato anche alle notizie precedentemente archiviate.
    unique_urls = {item["url"]: item for item in entries}
    verified = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        checks = {pool.submit(verify, item["url"], item["source"], item["title"]): item
                  for item in unique_urls.values()}
        for future in as_completed(checks):
            item = checks[future]
            try:
                allowed = future.result()
            except Exception as exc:
                print(f"Controllo accessibilita' fallito: {type(exc).__name__}", file=sys.stderr)
                allowed = False
            if allowed:
                record = dict(item)
                record["status"] = "accesso_gratuito_verificato"
                verified.append(record)
    print(f"Verifica gratuiti: {len(verified)}/{len(unique_urls)}", file=sys.stderr)
    entries = verified
    entries.sort(key=lambda x: x["published_at"], reverse=True)
    archive, seen_urls, seen_titles, counts = [], set(), set(), {}
    for item in entries:
        source = item["source"]
        title_key = re.sub(r'\W+', ' ', item["title"].casefold()).strip()
        if (item["url"] in seen_urls or title_key in seen_titles or
            counts.get(source, 0) >= 35):
            continue
        archive.append(item)
        seen_urls.add(item["url"])
        seen_titles.add(title_key)
        counts[source] = counts.get(source, 0) + 1
        if len(archive) >= 150:
            break
    return {"schema_version": 2, "updated_at": now.isoformat(timespec="seconds"),
            "publication_mode": "solo_articoli_integrali_gratuiti",
            "items": archive, "feeds_ok": ok, "feeds_failed": failed,
            "other_sources": [{"name":n,"url":u,"mode":"monitoraggio_editoriale"}
                              for n,u in OTHER_SOURCES]}
if __name__ == "__main__":
    old = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    value = build(previous=old)
    if not value["feeds_ok"]:
        raise SystemExit("Nessun feed specialistico raggiungibile: preservo l'archivio precedente")
    if OUTPUT.exists():
        old=json.loads(OUTPUT.read_text(encoding="utf-8"))
        if {k:v for k,v in value.items() if k!="updated_at"} == {k:v for k,v in old.items() if k!="updated_at"}:
            print("Spunti specialistici invariati")
            raise SystemExit(0)
    OUTPUT.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Collegamenti esterni classificati: {len(value['items'])}")
