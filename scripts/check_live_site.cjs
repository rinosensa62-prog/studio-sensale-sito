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
        extraBlock:!!document.querySelector("#studio-news-live"),
        injectedScript:!!document.querySelector('script[src*="studio-news-live.js"]'),
        cards:cards.length, external:external.length, wrongCategory:wrong.length,
        duplicateUrls:dupeCount,
        excludedSend:cards.some(x=>/(?:indebit.{0,60}send|send.{0,60}indebit)/i.test(x.textContent)),
        latest:external.slice(0,3).map(x=>({title:x.querySelector("h3")?.textContent,
          category:x.dataset.category,date:x.querySelector("time")?.dateTime})),
        homeFeature: document.querySelector("a.home-feature")?.querySelector("h2")?.textContent||null
      };
    },{container,category});
    if(result.extraBlock||result.injectedScript||!result.cards||result.wrongCategory||result.excludedSend||result.duplicateUrls)failures++;
    if(result.external)hasAutomaticContent=true;
    console.log(JSON.stringify({route,...result}));
  }
  await browser.close();
  if(!hasAutomaticContent)failures++;
  if(failures) {console.error("Controlli non superati: "+failures);process.exit(1);}
  console.log("OK: grafica originale, nessun blocco extra, notizie nelle griglie esistenti.");
})().catch(e=>{console.error(e.stack);process.exit(1);});
