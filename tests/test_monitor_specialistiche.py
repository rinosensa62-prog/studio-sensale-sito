import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT=Path(__file__).resolve().parent.parent/'scripts'/'monitor_fonti_specialistiche.py'
spec=importlib.util.spec_from_file_location('monitor_fonti_specialistiche',SCRIPT)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
NOW=datetime(2026,11,21,12,0,tzinfo=timezone.utc)
FEED=m.FEEDS[0]

def sample(title="Partite IVA e agevolazioni 2026",link="https://www.fiscal-focus.it/news,190292",date="Fri, 20 Nov 2026 00:00:00 +0100"):
    return ('<rss><channel><item><title>'+title+'</title><link>'+link+
            '</link><pubDate>'+date+'</pubDate></item></channel></rss>').encode()

class EditorialTests(unittest.TestCase):
    def test_candidati_solo_editoriali(self):
        x=m.parse(sample(),FEED,NOW)
        self.assertEqual(len(x),1)
        self.assertEqual(x[0]['status'],'spunto_da_verificare')
    def test_host_esterno_rifiutato(self):
        self.assertEqual(m.parse(sample(link="https://fiscal-focus.it.example.com/news"),FEED,NOW),[])
    def test_storie_vecchie_rifiutate(self):
        self.assertEqual(m.parse(sample(date="Mon, 11 Aug 2025 00:00:00 +0200"),FEED,NOW),[])
    def test_selezione_esclusa(self):
        self.assertEqual(m.parse(sample(title="Selezione comparativa per consulenti fiscali"),FEED,NOW),[])
    def test_inaccessibilita_registrata(self):
        v=m.build(fetcher=lambda _: (_ for _ in ()).throw(OSError("offline")),now=NOW)
        self.assertEqual(len(v['feeds_failed']),len(m.FEEDS))
        self.assertEqual(v['items'],[])
        self.assertEqual(v['publication_mode'],'solo_revisione_editoriale_non_pubblicare_sul_sito')
    def test_mai_feed_specialistici_nel_sito_pubblico(self):
        self.assertIn('fiscoetasse.com', {x[2] for x in m.FEEDS})
        self.assertIn('fiscal-focus.it', {x[2] for x in m.FEEDS})
        self.assertIn('ipsoa.it', {x[2] for x in m.FEEDS})
        self.assertTrue(all(x[1].startswith('https://') for x in m.FEEDS))

if __name__=='__main__':
    unittest.main()
