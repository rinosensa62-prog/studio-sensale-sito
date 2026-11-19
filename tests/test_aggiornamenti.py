import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

p = Path(__file__).resolve().parent.parent / 'scripts' / 'aggiorna_fonti.py'
s = importlib.util.spec_from_file_location('aggiorna_fonti', p)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)
NOW = datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc)
SOURCE = ('INPS Notizie', 'https://www.inps.it/it/it.rss.news.xml', 'inps.it')

def rss(title='Bonus mamme 2026: domanda', link='https://www.inps.it/info/bonus', date='Wed, 18 Nov 2026 13:00:00 +0000'):
    return f'''<rss version="2.0"><channel><item><title>{title}</title><link>{link}</link><pubDate>{date}</pubDate></item></channel></rss>'''.encode()

class ParserTests(unittest.TestCase):
    def test_legitimate_news(self):
        a = m.parse(rss(), SOURCE, NOW)
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]['category'], 'Bandi e finanziamenti')
    def test_reject_external_url(self):
        self.assertEqual(m.parse(rss(link='https://example.org/bonus'), SOURCE, NOW), [])
        self.assertIsNone(m.official_url('https://inps.it.example.com/abc', 'inps.it'))
        self.assertIsNone(m.official_url('javascript:alert(1)', 'inps.it'))
    def test_age_window(self):
        self.assertEqual(m.parse(rss(date='Tue, 10 Nov 2026 12:00:00 +0000'), SOURCE, NOW)[0]['source'], 'INPS Notizie')
        self.assertEqual(m.parse(rss(date='Tue, 01 Sep 2026 12:00:00 +0000'), SOURCE, NOW), [])
    def test_no_fabricated_news(self):
        self.assertIsNone(m.classify('Comunicato stampa di apertura della mostra'))
        self.assertEqual(m.parse(rss(title='Concorso per nuovi dipendenti'), SOURCE, NOW), [])
    def test_atom_feed(self):
        doc = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Partita IVA e obblighi fiscali</title><link rel="alternate" href="https://www.inps.it/info/partita-iva"/><updated>2026-11-18T12:00:00Z</updated></entry></feed>'
        self.assertEqual(len(m.parse(doc, SOURCE, NOW)), 1)
    def test_stop_on_unavailable_sources(self):
        def fail(_):
            raise OSError('offline')
        with self.assertRaises(RuntimeError):
            m.build(fetch=fail, now=NOW)
    def test_avoid_repeated_commit(self):
        a = m.build(fetch=lambda _:rss(), now=NOW)
        self.assertIsNotNone(a)
        self.assertIsNone(m.build(fetch=lambda _:rss(), now=NOW,previous=a))

if __name__ == '__main__':
    unittest.main()
