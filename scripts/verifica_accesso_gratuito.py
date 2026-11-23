"""Verifica conservativa della leggibilita integrale e gratuita di una notizia.

Solo accesso pubblico, senza cookie, account, abbonamenti o aggiramento paywall.
I contenuti non sono copiati: l'esito serve esclusivamente a decidere se linkare.
"""
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import re
import unicodedata

# Queste testate presentano spesso l'articolo come anteprima acquistabile.
# Finche non esiste una verifica positiva affidabile del singolo articolo,
# i relativi link non vengono pubblicati.
SORGENTI_NON_AMMESSE = {"Eutekne", "Redazione Fiscale"}

BLOCCO = re.compile(
    r"(?:contenut[oi]\s+riservat[oi](?:\s+agli?\s+abbonat[oi])?|"
    r"per\s+continuare\s+(?:la\s+)?lettura|"
    r"(?:abbonati|acquista)\s+per\s+(?:continuare|leggere|accedere)|"
    r"per\s+leggere\s+(?:l.articolo|il\s+contenuto)\s+completo|"
    r"continua\s+a\s+leggere\s+con\s+(?:l.abbonamento|premium)|"
    r"(?:questo|l.)\s*articolo\s+(?:e|è)\s+riservato\s+agli\s+abbonati|"
    r"solo\s+(?:per\s+)?(?:gli\s+)?abbonati\s+possono\s+leggere)",
    re.I,
)
MARKUP_PAYWALL = re.compile(
    r'["\x27]isAccessibleForFree["\x27]\s*:\s*(?:false|["\x27]false["\x27])',
    re.I,
)
NON_HTML = re.compile(r"(?:pdf|octet-stream|image/)", re.I)
HOSTS = {
    "Fiscal Focus": "fiscal-focus.it",
    "Fisco e Tasse": "fiscoetasse.com",
    "Informazione Fiscale": "informazionefiscale.it",
    "IPSOA Fisco": "ipsoa.it",
    "IPSOA Impresa": "ipsoa.it",
    "LavoroSì": "lavorosi.it",
    "Eutekne": "eutekne.info",
    "Euroconference News": "ecnews.it",
    "Redazione Fiscale": "redazionefiscale.it",
}
MIN_WORDS = {
    "Fiscal Focus": 90, # news24: notizie brevi, ma complete
    "Fisco e Tasse": 140,
    "Informazione Fiscale": 150,
    "IPSOA Fisco": 200,
    "IPSOA Impresa": 200,
    "LavoroSì": 100,
    "Euroconference News": 150,
}
class ArticleReader(HTMLParser):
    """Acquisisce testo visibile, H1 e paragrafi successivi al titolo."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.h1_depth = 0
        self.title_parts = []
        self.heading_found = False
        self.p_depth = 0
        self.text_parts = []
        self.paragraph_parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg", "template"):
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "h1":
            self.heading_found = True
            self.h1_depth += 1
        if self.heading_found and tag in ("p", "li", "blockquote"):
            self.p_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "template") and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag == "h1":
            self.h1_depth = max(0, self.h1_depth - 1)
        if tag in ("p", "li", "blockquote"):
            self.p_depth = max(0, self.p_depth - 1)

    def handle_data(self, data):
        if self.skip:
            return
        t = " ".join(data.split())
        if not t:
            return
        self.text_parts.append(t)
        if self.h1_depth:
            self.title_parts.append(t)
        if self.heading_found and self.p_depth:
            self.paragraph_parts.append(t)

def simplify(x):
    x = unicodedata.normalize("NFKD", x.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in x if not unicodedata.combining(c))).strip()

def validate_html(content, source, title, url):
    """Controllo prudente, non un attestato assoluto contro paywall JS."""
    if source in SORGENTI_NON_AMMESSE or source not in MIN_WORDS:
        return False
    if source == "Fiscal Focus" and "/news," not in urlsplit(url).path:
        return False
    markup = content.decode("utf-8", "replace") if isinstance(content, bytes) else content
    if len(markup) < 700 or MARKUP_PAYWALL.search(markup):
        return False
    doc = ArticleReader()
    doc.feed(markup)
    page_text = " ".join(doc.text_parts)
    if BLOCCO.search(page_text):
        return False
    if source.startswith("IPSOA") and not re.search(
        r"questo\s+articolo\s+(?:è|e)\s+offerto\s+gratuitamente", page_text, re.I
    ):
        return False
    page_heading = simplify(" ".join(doc.title_parts))
    expected = simplify(title)
    if not page_heading or not expected:
        return False
    expected_words = {w for w in expected.split() if len(w) > 3}
    heading_words = set(page_heading.split())
    if not expected_words or len(expected_words & heading_words) / len(expected_words) < 0.48:
        return False
    article_words = len(re.findall(r"\b[\wÀ-ÿ'-]+\b", " ".join(doc.paragraph_parts)))
    return article_words >= MIN_WORDS[source]

def articolo_gratuito(url, source, title):
    """Accetta solo pagina pubblica e HTML con testo sufficientemente esteso."""
    if source in SORGENTI_NON_AMMESSE or source not in HOSTS:
        return False
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    expected = HOSTS[source]
    if p.scheme != "https" or p.username or p.password or (
        host != expected and not host.endswith("." + expected)
    ):
        return False
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; StudioSensaleFreeNewsChecker/1.0)",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.4",
    })
    try:
        with urlopen(req, timeout=11) as resp:
            final = urlsplit(resp.geturl())
            final_host = (final.hostname or "").lower()
            if final_host != expected and not final_host.endswith("." + expected):
                return False
            if any(s in final.path.lower() for s in ("/login", "/accedi", "/abbonamenti", "/registrazione")):
                return False
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if NON_HTML.search(ctype) or "html" not in ctype:
                return False
            data = resp.read(2_000_001)
            if len(data) > 2_000_000:
                return False
        return validate_html(data, source, title, url)
    except (OSError, TimeoutError, UnicodeError, ValueError):
        return False
