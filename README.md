# Studio Sensale – segnalazioni istituzionali quotidiane

Questo repository pubblico contiene l'automazione delle **notizie da fonti ufficiali** per il sito [studiosensale.it](https://studiosensale.it). Non contiene dati di clienti, password o configurazioni della posta Aruba.

## Aggiornamento programmato

Il workflow [Aggiornamento quotidiano notizie istituzionali](.github/workflows/aggiornamento-fonti.yml) è pianificato ogni giorno alle **07:20 UTC** (08:20 a Roma in inverno, 09:20 in estate).

Il programma:
- legge feed RSS/Atom di Agenzia delle Entrate, INPS, INAIL, Ministero del Lavoro e MIMIT;
- sceglie titoli pertinenti a fisco, lavoro, CAF, imprese, bandi, immobili e successioni pubblicati negli ultimi 14 giorni;
- pubblica solo titoli, date, categoria e link alle pagine originali dell'ente;
- non scrive o interpreta pareri professionali;
- non sovrascrive dati esistenti se meno di due feed possono essere letti;
- aggiunge le nuove segnalazioni all'archivio cumulativo [assets/aggiornamenti-ufficiali.json](assets/aggiornamenti-ufficiali.json), senza eliminare quelle storiche; l'ordine è dalla più recente alla meno recente;
- conserva le categorie che alimentano le sette sezioni tematiche del sito e aggiorna il file soltanto quando cambiano i contenuti.

## Integrazione con Netlify

L'aggiornamento del JSON avviene tramite GitHub Actions, **senza deploy giornaliero Netlify**.

Una sola volta, il sito attuale deve integrare le sezioni frontend e configurare un proxy Netlify su:
`https://raw.githubusercontent.com/rinosensa62-prog/studio-sensale-sito/main/assets/aggiornamenti-ufficiali.json`.

Il pacchetto completo da caricare **una sola volta** sul progetto Netlify esistente viene fornito separatamente. Non cambiare DNS, nameserver, MX o posta Aruba.

## Prova

Aprire la scheda Actions di GitHub, scegliere il workflow e fare **Run workflow**. Verificare lo stato verde e aprire il JSON aggiornato. In Settings > Actions > General > Workflow permissions, se necessario consentire la scrittura del repository per GitHub Actions.

Se un feed ufficiale smette di rispondere o cambia formato, il workflow può fallire e il sito conserva le segnalazioni precedenti. Le fonti si devono controllare periodicamente.

## Avvertenza

Questi sono **collegamenti automatici non revisionati caso per caso dal titolare**. Titoli e date derivano dalla fonte originale. Verificare sempre atti, validità delle disposizioni, requisiti, modifiche e rettifiche prima di consigliare un cliente.