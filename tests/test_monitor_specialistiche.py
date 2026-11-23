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
        self.assertEqual(x[0]['status'],'link_esterno_da_verificare')
        self.assertEqual(x[0]['category'],'Bandi e finanziamenti')
    def test_host_esterno_rifiutato(self):
        self.assertEqual(m.parse(sample(link="https://fiscal-focus.it.example.com/news"),FEED,NOW),[])
    def test_storie_vecchie_rifiutate(self):
        self.assertEqual(m.parse(sample(date="Mon, 11 Aug 2025 00:00:00 +0200"),FEED,NOW),[])
    def test_selezione_esclusa(self):
        self.assertEqual(m.parse(sample(title="Selezione comparativa per consulenti fiscali"),FEED,NOW),[])
    def test_inaccessibilita_registrata(self):
        v=m.build(fetcher=lambda _: (_ for _ in ()).throw(OSError("offline")),now=NOW,verify=lambda *args: False)
        self.assertEqual(len(v['feeds_failed']),len(m.FEEDS)+len(m.HTML_SOURCES))
        self.assertEqual(v['items'],[])
        self.assertEqual(v['publication_mode'],'link_esterni_per_categoria')
    def test_esclusione_send_indebiti(self):
        self.assertIsNone(m.classify('Indebiti INPS dal 2027 notifiche online con SEND cosa cambia'))
        self.assertEqual(m.parse(sample(title='Indebiti INPS dal 2027 notifiche online con SEND cosa cambia'),FEED,NOW),[])
    def test_classificazione_tematica(self):
        self.assertEqual(m.classify('IMU 2027: pagamento PagoPA'),'Successioni e tributi locali')
        self.assertEqual(m.classify('Contratti di locazione, cedolare secca'),'Locazioni e immobili')
        self.assertEqual(m.classify('Distacchi Italia-Turchia, contributi Uniemens'),'Lavoro e paghe')
        self.assertEqual(m.classify('Fattura elettronica nuove specifiche 2027'),'Dichiarazioni e Fisco')
    def test_archivio_persistente(self):
        previous={'items':[{'title':'IMU 2027: pagamento PagoPA',
                           'source':'Informazione Fiscale',
                           'url':'https://www.informazionefiscale.it/imu-test',
                           'published_at':'2026-11-19T09:00:00+00:00'}]}
        v=m.build(fetcher=lambda _: (_ for _ in ()).throw(OSError("offline")), now=NOW,previous=previous,verify=lambda *args: True)
        self.assertEqual(len(v['items']),1)
        self.assertEqual(v['items'][0]['status'],'accesso_gratuito_verificato')
        self.assertEqual(v['items'][0]['category'],'Successioni e tributi locali')
    def test_html_redazione_fiscale(self):
        from scripts import fonti_web_pubbliche as web
        article = (b'<html><body><div>Notizie Flash 20/11/2026</div>'
                   b'<h1>Saldo IMU 2026 sulle aree fabbricabili</h1></body></html>')
        item = web.parse_public_article(article,
            'https://www.redazionefiscale.it/c/notizie-flash/52407-test',
            'Redazione Fiscale', NOW, m.classify, m.get_date)
        self.assertIsNotNone(item)
        self.assertEqual(item['category'], 'Successioni e tributi locali')
    def test_html_euroconference_data(self):
        from scripts import fonti_web_pubbliche as web
        article = (b'<html><head><meta property="article:published_time" '
                   b'content="2026-11-20T09:00:00+00:00"></head><body>'
                   b'<h1>Fattura elettronica e novita IVA</h1></body></html>')
        item = web.parse_public_article(article,
            'https://www.ecnews.it/fiscale/fisco-e-patrimonio/iva/test/',
            'Euroconference News', NOW, m.classify, m.get_date)
        self.assertIsNotNone(item)
        self.assertEqual(item['category'], 'Dichiarazioni e Fisco')
    def test_link_con_accesso_riservato_escluso(self):
        from scripts.verifica_accesso_gratuito import validate_html
        article = '<html><h1>CPB con acconti imposta variabili</h1>' + (
            '<p>Questo paragrafo mostra una descrizione preliminare delle norme applicabili.</p>'*12
        ) + '<p>CONTENUTO RISERVATO AGLI ABBONATI</p></html>'
        self.assertFalse(validate_html(article, 'Eutekne',
            'CPB con acconti imposta variabili','https://www.eutekne.info/Sezioni/Articolo.aspx?ID=123'))
        self.assertFalse(validate_html(article,'Fisco e Tasse',
            'CPB con acconti imposta variabili','https://www.fiscoetasse.com/news/123'))
        self.assertFalse(validate_html('<html><h1>Novita fiscali</h1><p>Breve anteprima</p></html>',
            'Fisco e Tasse','Novita fiscali','https://www.fiscoetasse.com/news/123'))
    def test_link_gratuito_accettato(self):
        from scripts.verifica_accesso_gratuito import validate_html
        article = '<html><h1>Fattura elettronica 2027 novita tecniche</h1>' + (
            '<p>Le specifiche tecniche prevedono adempimenti, verifiche, date di decorrenza e regole operative da applicare correttamente agli invii.</p>'*20
        ) + '</html>'
        self.assertTrue(validate_html(article,'Fisco e Tasse',
            'Fattura elettronica 2027 novita tecniche','https://www.fiscoetasse.com/new-rassegna-stampa/test.html'))
    def test_euroconference_non_pubblicabile_senza_garanzia_no_login(self):
        from scripts.verifica_accesso_gratuito import validate_html, articolo_gratuito
        url = "https://www.ecnews.it/fiscale/fisco-e-patrimonio/imposte-indirette/affitto-di-azienda-alternativita-iva-e-registro/"
        title = "Affitto di azienda: alternativita IVA e registro"
        sample = ("<html><h1>"+title+"</h1>" +
                  "<p>Testo informativo pubblico piuttosto lungo ma non garanzia di visione anonima.</p>"*35 +
                  "</html>")
        self.assertFalse(validate_html(sample, "Euroconference News", title, url))
        self.assertFalse(articolo_gratuito(url, "Euroconference News", title))
    def test_esclusi_articoli_promozionali_non_informativi(self):
        from scripts.verifica_accesso_gratuito import validate_html
        url = "https://www.informazionefiscale.it/tutte-le-novita-fiscali-legge-di-bilancio-2027-formazione-academy"
        title = "Tutte le novita fiscali della Legge di Bilancio 2027"
        sample = ("<html><h1>"+title+"</h1>" +
                  "<p>La formazione Academy contiene informazioni e corsi promozionali.</p>"*35 +
                  "</html>")
        self.assertFalse(validate_html(sample, "Informazione Fiscale", title, url))
    def test_mai_feed_specialistici_nel_sito_pubblico(self):
        self.assertIn('fiscoetasse.com', {x[2] for x in m.FEEDS})
        self.assertIn('fiscal-focus.it', {x[2] for x in m.FEEDS})
        self.assertIn('ipsoa.it', {x[2] for x in m.FEEDS})
        self.assertTrue(all(x[1].startswith('https://') for x in m.FEEDS))

if __name__=='__main__':
    unittest.main()
