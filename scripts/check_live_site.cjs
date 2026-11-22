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
  const browser = await chromium.launch({ headless:true, args:["--no-sandbox"] });
  const page = await browser.newPage({viewport:{width:1440,height:900}});
  let failures = 0;
  for(const [route,category] of cases){
    const errors = [];
    const onError = e => errors.push(String(e.message || e));
    const onConsole = msg => {if(msg.type()==="error") errors.push(msg.text());};
    page.on("pageerror",onError);
    page.on("console",onConsole);
    await page.goto(BASE + route, {waitUntil:"domcontentloaded", timeout:25000});
    try { await page.locator("#studio-news-live").waitFor({state:"attached",timeout:14000}); }
    catch(e){ errors.push("Modulo news live non trovato"); failures++; }
    const cards = await page.locator("#studio-news-live article.studio-news-item").count();
    const snippets = (await page.locator("#studio-news-live article.studio-news-item h3")
       .allTextContents()).slice(0,3);
    const script = await page.locator('script[src*="studio-news-live.js"]').count();
    if(!cards) failures++;
    const text = await page.locator("#studio-news-live").allTextContents();
    if(text.join(" ").match(/indebit\w*.{0,50}(?:notific\w*|SEND)/i)){
      errors.push("Notizia esclusa SEND trovata"); failures++;
    }
    console.log(JSON.stringify({route,category,script,cards,examples:snippets,errors}));
    page.off("pageerror",onError);
    page.off("console",onConsole);
  }
  await browser.close();
  if(failures) {console.error("ERRORI TOTALI:", failures);process.exit(1);}
  console.log("OK: tutte le sezioni caricano le notizie live.");
})().catch(e=>{console.error(e.stack);process.exit(1);});
