const { chromium } = require("playwright");

const BASE = "https://studiosensale.it";
const cases = [
  ["/", null],
  ["/notizie/", null],
  ["/argomenti/bandi-finanziamenti/", "Bandi e finanziamenti"],
  ["/argomenti/imprese-partita-iva/", "Aprire e gestire un’attività"],
  ["/argomenti/lavoro-paghe/", "Lavoro e paghe"],
  ["/argomenti/caf-famiglie/", "Famiglie e CAF"],
  ["/argomenti/fisco-dichiarazioni/", "Dichiarazioni e Fisco"],
  ["/argomenti/locazioni-immobili/", "Locazioni e immobili"],
  ["/argomenti/successioni-tributi-locali/", "Successioni e tributi locali"],
];
(async () => {
  const browser = await chromium.launch({headless:true,args:["--no-sandbox"]});
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  let failures=0, hasAutomaticContent=false;
  let archiveTodayTitles = [], archiveRecentCount = 0;
  for (const [route, category] of cases) {
    await page.goto(BASE+route,{waitUntil:"domcontentloaded",timeout:28000});
    const container = route === "/" ? "#home-news-items" :
      route === "/notizie/" ? "#news-items" : ".editorial-grid[data-category-archive]";
    await page.locator(container).first().waitFor({state:"visible",timeout:18000});
    try {
      await page.locator(container+" a.external-archive-card").first()
        .waitFor({state:"attached",timeout:11000});
    } catch(e) {
      // Alcune categorie potrebbero non avere ancora segnalazioni pertinenti.
    }
    const result = await page.evaluate(({container,category})=>{
      const grid=document.querySelector(container);
      const cards=grid? [...grid.querySelectorAll("a.editorial-card")]:[];
      const external=cards.filter(x=>x.matches(".external-archive-card"));
      const wrong=category?external.filter(x=>x.dataset.category!==category):[];
      const duplicates= new Set();
      let dupeCount=0;
      for(const card of cards) {
        const url=card.href;
        if(duplicates.has(url))dupeCount++;else duplicates.add(url);
      }
      return {
        recentExternal: external.filter(x=>{ const t=x.querySelector("time")?.dateTime; return t && new Date(t).toDateString()===new Date().toDateString(); }).length,
        externalTitles: external.map(x=>x.querySelector("h3")?.textContent?.trim()).filter(Boolean),
        extraBlock:!!document.querySelector("#studio-news-live"),
        injectedScript:!!document.querySelector('script[src*="studio-news-live.js"]'),
        cards:cards.length, external:external.length, wrongCategory:wrong.length,
        paywallSources:external.filter(x=>/(?:eutekne\.info|redazionefiscale\.it)/i.test(x.href)).map(x=>x.href),
        duplicateUrls:dupeCount,
        excludedSend:cards.some(x=>/(?:indebit.{0,60}send|send.{0,60}indebit)/i.test(x.textContent)),
        latest:external.slice(0,3).map(x=>({title:x.querySelector("h3")?.textContent,
          category:x.dataset.category,date:x.querySelector("time")?.dateTime})),
        homeFeature: document.querySelector("a.home-feature")?.querySelector("h2")?.textContent||null
      };
    },{container,category});
    if(route === "/notizie/") {
      archiveTodayTitles = result.externalTitles;
      archiveRecentCount = result.recentExternal;
    }
    if(result.extraBlock||result.injectedScript||!result.cards||result.wrongCategory||result.excludedSend||result.duplicateUrls||result.paywallSources.length)failures++;
    if(result.external)hasAutomaticContent=true;
    console.log(JSON.stringify({route,...result}));
  }
  // Diagnostica di pubblicazione: il sito deve presentare almeno una parte delle
  // segnalazioni più recenti effettivamente presenti nell'archivio GitHub.
  const today = new Date().toISOString().slice(0,10);
  const rawUrl = "https://raw.githubusercontent.com/rinosensa62-prog/studio-sensale-sito/main/assets/spunti-editoriali.json";
  const request = await page.request.get(rawUrl+"?ts="+Date.now(),{timeout:20000});
  if(!request.ok()) {
    console.error("Archivio editoriale GitHub non accessibile:",request.status());
    failures++;
  } else {
    const data=await request.json();
    const current=(data.items||[]).filter(x=>String(x.published_at||"").startsWith(today))
      .filter(x=>!/indebit.*(?:send|notific)|(?:send|notific).*indebit/i.test(x.title||""));
    const found=current.filter(x=>archiveTodayTitles.includes(x.title));
    console.log(JSON.stringify({checked_at:new Date().toISOString(),latest_feed_date:data.updated_at,
      specialist_items_today:current.length,site_external_cards_today:archiveRecentCount,
      today_titles_also_in_site:found.length,sample_from_feed:current.slice(0,4).map(x=>x.title)}));
    if(current.length>0 && found.length===0){
      console.error("CRITICO: le segnalazioni specialistiche di oggi sono nel feed ma non appaiono nell'archivio pubblico");
      failures++;
    }
  }
  const archiveResponse = await page.request.get(
    "https://raw.githubusercontent.com/rinosensa62-prog/studio-sensale-sito/main/assets/spunti-editoriali.json?t="+Date.now()
  );
  const archiveJson = await archiveResponse.json();
  const unverified = (archiveJson.items||[]).filter(x=>x.status!=="accesso_gratuito_verificato");
  const forbidden = (archiveJson.items||[]).filter(x=>["Eutekne","Redazione Fiscale"].includes(x.source));
  console.log(JSON.stringify({audit:"free_full_text",kept:archiveJson.items.length,
    unverified:unverified.length,restricted_sources:forbidden.length,
    mode:archiveJson.publication_mode}));
  if(unverified.length||forbidden.length||
     archiveJson.publication_mode!=="solo_articoli_integrali_gratuiti")failures++;
  await browser.close();
  if(!hasAutomaticContent)failures++;
  if(failures) {console.error("Controlli non superati: "+failures);process.exit(1);}
  console.log("OK: grafica originale, nessun blocco extra, notizie nelle griglie esistenti.");
})().catch(e=>{console.error(e.stack);process.exit(1);});
