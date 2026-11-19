#!/usr/bin/env python3
"""Studio Sensale: segnalazioni di fonti ufficiali, non pareri professionali."""
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

OUTPUT = Path(__file__).resolve().parent.parent / 'assets' / 'aggiornamenti-ufficiali.json'
FEEDS = [
    ('Agenzia delle Entrate', 'https://www.agenziaentrate.gov.it/portale/c/portal/rss/entrate?idrss=0753fcb1-1a42-4f8c-f40d-02793c6aefb4', 'agenziaentrate.gov.it'),
    ('INPS Notizie', 'https://www.inps.it/it/it.rss.news.xml', 'inps.it'),
    ('INPS Circolari', 'https://www.inps.it/it/it.rss.circolari.xml', 'inps.it'),
    ('INPS Messaggi', 'https://www.inps.it/it/it.rss.messaggi.xml', 'inps.it'),
    ('INAIL Notizie', 'https://www.inail.it/portale/it.rss.news.xml', 'inail.it'),
    ('INAIL Avvisi', 'https://www.inail.it/portale/it.rss.avvisi.xml', 'inail.it'),
    ('Ministero del Lavoro', 'https://lavoro.gov.it/_layouts/15/Lavoro.Web/AppPages/RSS', 'lavoro.gov.it'),
    ('MIMIT Notizie', 'https://www.mimit.gov.it/index.php/it/notizie-stampa?format=feed&type=rss', 'mimit.gov.it'),
]
CATEGORIES = [
    ('Bandi e finanziamenti', r'\b(band[oi]|finanziament[oi] agevolat|finanziament[oi] a fondo perduto|voucher|incentiv|agevolazion|fondo perduto|bonus assunzion|credito d.imposta|autoimpiego|start.up)\w*'),
    ('Successioni e tributi locali', r'\b(succession|eredit|eredi|imu|tari|tributi locali|imposta di registro|donazion)\w*'),
    ('Locazioni e immobili', r'\b(locazion|affitt|catast|immobil|cedolare secca|sister)\w*'),
    ('Famiglie e CAF', r'\b(isee|assegno unico|assegno di inclusione|bonus mamm|famigli|dsu|730|pension|naspi|conged|invalidit|disabilit)\w*'),
    ('Lavoro e paghe', r'\b(contratt[oi] di lavoro|occupazion|cedolin|lavorator|dipendent|assunzion|contributiv|contributi previdenzial|previdenz|sicurezza sul lavoro|infortun|sgrav|dimission|disoccupazion|retribuzion|unilav)\w*'),
    ('Dichiarazioni e Fisco', r'\b(fisco|fiscal|irpef|iva|fattur|imposta|dichiarazion|redditi|770|compliance|accertament|versament|f24|rottamazion|codice tributo|adempiment)\w*'),
    ('Aprire e gestire un’attività', r'\b(partita iva|professionist|impres|societ|attivit[aà] economic|commerc|costituzion|ateco|artigian)\w*')
]
REJECT = r'\b(concors[oi]|selezione del personale|visita istituzionale|conferenza stampa)\b'

def simple(tag):
    return tag.rsplit('}', 1)[-1].split(':')[-1].lower()

def child_text(node, keys):
    for child in list(node):
        if simple(child.tag) in keys and child.text and child.text.strip():
            return child.text.strip()
    return ''

def link_of(node):
    for child in node:
        if simple(child.tag) != 'link':
            continue
        href = child.attrib.get('href', '')
        if href and child.attrib.get('rel', 'alternate') in ('alternate', ''):
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return ''

def pub_date(raw):
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (ValueError, TypeError, IndexError):
        try:
            dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def official_url(raw, institution_host):
    try:
        p = urlsplit(raw.strip())
        host = (p.hostname or '').lower()
        if (p.scheme not in ('https', 'http') or p.username or p.password or
            p.port not in (None, 80, 443) or not
            (host == institution_host or host.endswith('.' + institution_host))):
            return None
        query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                           if not (k.lower().startswith('utm_') or k.lower() in ('fbclid', 'gclid'))])
        return urlunsplit(('https', p.netloc.lower(), p.path or '/', query, ''))
    except (ValueError, AttributeError):
        return None

def classify(title):
    if re.search(REJECT, title, re.I):
        return None
    # Agevolazioni per disabilita e ISEE sono temi CAF, non bandi impresa.
    if re.search(r'agevolazion\w* disabil|acquisto auto cointestat|\bisee\b|bonus mamm|assegno unico', title, re.I):
        return 'Famiglie e CAF'
    # Gli interpelli molto specialistici non sono automaticamente notizie
    # di interesse generale per famiglie, clienti CAF e piccole imprese.
    if re.match(r'^\s*Interpello:', title, re.I) and not re.search(
        r'agevolazion\w* disabil|regime forfettari|bonus mamm|\bisee\b|succession|\b730\b',
        title, re.I
    ):
        return None
    if re.search(r'fondazioni di origine bancaria', title, re.I):
        return None
    for label, pattern in CATEGORIES:
        if re.search(pattern, title, re.I):
            return label
    return None

def parse(xml_bytes, source, now):
    root = ET.fromstring(xml_bytes)
    nodes = [n for n in root.iter() if simple(n.tag) in ('item', 'entry')]
    if not nodes:
        raise ValueError('Feed RSS/Atom senza voci riconosciute')
    out = []
    for node in nodes[:120]:
        title = html.unescape(re.sub('<[^>]*>', ' ', child_text(node, ('title',))))
        title = re.sub(r'\s+', ' ', title).strip()[:190]
        date = pub_date(child_text(node, ('pubdate', 'published', 'updated', 'date', 'created')))
        url = official_url(link_of(node), source[2])
        group = classify(title)
        if not (title and url and date and group):
            continue
        if not timedelta(hours=-6) <= now - date <= timedelta(days=14):
            continue
        out.append({
            'id': hashlib.sha256(url.encode()).hexdigest()[:18],
            'title': title, 'url': url, 'source': source[0],
            'category': group, 'published_at': date.isoformat(timespec='seconds'),
        })
    return out

def fetch_feed(url):
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; StudioSensaleFeed/1.0; +https://studiosensale.it)',
                                'Accept': 'application/rss+xml,application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.3'})
    with urlopen(req, timeout=20) as resp:
        data = resp.read(3_000_001)
    if len(data) > 3_000_000:
        raise ValueError('Dimensione feed eccessiva')
    return data

def build(fetch=fetch_feed, now=None, previous=None):
    now = now or datetime.now(timezone.utc)
    successes, failures, items = [], [], []
    for source in FEEDS:
        try:
            found = parse(fetch(source[1]), source, now)
            successes.append(source[0])
            items.extend(found)
            print(f"{source[0]}: {len(found)} notizie pertinenti", file=sys.stderr)
        except Exception as exc:
            failures.append(source[0])
            print(f"Feed non disponibile: {source[0]} ({type(exc).__name__}: {exc})", file=sys.stderr)
    if len(successes) < 2:
        raise RuntimeError('Meno di due feed verificati: mantengo i dati precedenti')
    unique = {item['id']: item for item in items}
    # Impedisce a un solo ente di saturare l'intera sezione.
    candidates = sorted(unique.values(), key=lambda x: x['published_at'], reverse=True)
    ordered, source_counts = [], {}
    for item in candidates:
        entity = item['source'].split(' ')[0]
        if source_counts.get(entity, 0) >= 8:
            continue
        source_counts[entity] = source_counts.get(entity, 0) + 1
        ordered.append(item)
        if len(ordered) >= 16:
            break
    # Archivio cumulativo delle segnalazioni, preservato tra le esecuzioni.
    old = previous or {}
    keep = {}
    for entry in old.get('items', []):
        if not isinstance(entry, dict):
            continue
        url = entry.get('url', '')
        source = next((src for src in FEEDS if src[0] == entry.get('source')), None)
        if not source or not official_url(url, source[2]) or not pub_date(entry.get('published_at', '')):
            continue
        if not entry.get('title') or not classify(entry['title']):
            continue
        fixed = dict(entry)
        fixed['category'] = classify(entry['title'])
        keep[hashlib.sha256(url.encode()).hexdigest()[:18]] = fixed
    for entry in ordered:
        keep[entry['id']] = entry
    archive = sorted(keep.values(), key=lambda x: x['published_at'], reverse=True)
    if archive == old.get('items') and successes == old.get('feeds_ok') and failures == old.get('feeds_failed'):
        return None
    return {'schema_version': 1, 'updated_at': now.isoformat(timespec='seconds'),
            'items': archive, 'feeds_ok': successes, 'feeds_failed': failures,
            'note': 'Archivio cumulativo di titoli e link istituzionali; non costituisce un parere dello Studio.'}

if __name__ == '__main__':
    previous = json.loads(OUTPUT.read_text(encoding='utf-8')) if OUTPUT.exists() else {}
    try:
        result = build(previous=previous)
        if result is None:
            print('Nessuna variazione.')
        else:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
            print(f"Aggiornate {len(result['items'])} notizie.")
    except Exception as exc:
        print(f"Nessun aggiornamento: {exc}", file=sys.stderr)
        sys.exit(1)
