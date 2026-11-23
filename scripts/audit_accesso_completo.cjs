/* Audit browser degli articoli effettivamente pubblicati sul sito.
 * Zero login, zero cookie preesistenti, zero bypass dei paywall.
 * Esegue una visita anonima e segnala ogni caso dubbio come NON verificato.
 * Uso: node scripts/audit_accesso_completo.cjs [--apply]
 */
const fs = require("fs");
const {chromium} = require("playwright");
const SPECIAL="assets/spunti-editoriali.json";
const OFFICIAL="assets/aggiornamenti-ufficiali.json";
const ROOT="https://studiosensale.it";
const NEWS=ROOT+"/notizie/";
const apply=process.argv.includes("--apply");

const toWords=s=>(s.match(/[\p{L}\p{N}][\p{L}\p{N}’'-]*/gu)||[]).length;
const norm=s=>String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/[^a-zA-Z0-9]+/g," ").toLowerCase().trim();
const forbidden=/contenut[oi]\s+riservat[oi]|per\s+continuare\s+(?:la\s+)?lettura|continua\s+a\s+leggere\s+(?:accedendo|con\s+(?:un\s+)?abbonamento|dopo\s+aver)|per\s+leggere\s+l.articolo\s+completo|(?:accedi|registrati|fai\s+login|effettua\s+l.accesso)\s+per\s+(?:continuare|leggere|sbloccare|visualizzare)|(?:per\s+continuare\s+a\s+leggere).{0,100}(?:login|registr|accedi)|questo\s+articolo\s+e\s+riservato|sblocca\s+l.articolo/i;
const denySources=new Set(["Eutekne","Redazione Fiscale","Euroconference News"]);
const suspiciousPages=/\/(?:login|signin|registrati|abbonamenti|subscribe|paywall)(?:\/|$)/i;
function looksLikeArticle(title,heading){
  const a=new Set(norm(title).split(" ").filter(w=>w.length>3));
  const b=new Set(norm(heading).split(" "));
  if(!a.size)return false;
  return [...a].filter(w=>b.has(w)).length/a.size>=0.45;
}
async function inspect(browser, item){
  const context=await browser.newContext({locale:"it-IT",viewport:{width:1360,height:900},
    javaScriptEnabled:true,acceptDownloads:false});
  const page=await context.newPage();
  const out={kind:item.kind,source:item.source||"Studio",title:item.title||"",url:item.url,
    status:"UNCERTAIN",reason:"not-checked",http:0,words:0};
  try{
    if(item.kind==="special" && denySources.has(item.source)){
      out.reason="blocked-source";return out;
    }
    if(item.kind==="special" && /formazione-academy|\/academy/i.test(item.url)){
      out.reason="promotional-product";return out;
    }
    let resp;
    try {resp=await page.goto(item.url,{waitUntil:"domcontentloaded",timeout:23000});}
    catch(e){
      if(item.kind==="official"&&item.url.includes("agenziaentrate.gov.it/portale/documents")&&
         String(e.message||e).includes("Download is starting")){
        const fetch=await context.request.get(item.url,{timeout:20000});
        const t=fetch.headers()["content-type"]||"";
        const b=await fetch.body();
        out.http=fetch.status();
        if(fetch.ok()&&b.length>400&&(/pdf|octet-stream/i.test(t)||b.subarray(0,5).toString()==="%PDF-")){
          out.status="PASS";out.reason="public-official-pdf";out.words=0;return out;
        }
        out.reason="official-download-not-verified";return out;
      }
      throw e;
    }
    out.http=resp?.status()||0;
    out.finalUrl=page.url();
    if(!resp||out.http>=400){out.reason="http-"+out.http;return out;}
    const typ=resp.headers()["content-type"]||"";
    if(/pdf|application\/octet-stream/.test(typ)){
      out.status=item.kind==="official"?"PASS":"UNCERTAIN";
      out.reason=item.kind==="official"?"public-document":"not-html-document";return out;
    }
    if(!/html/.test(typ)){out.reason="non-html-"+typ.slice(0,50);return out;}
    await page.waitForTimeout(1000);
    const dat=await page.evaluate(()=>{
      const body=document.body;
      const h1=document.querySelector("h1");
      const all=body?.innerText||"";
      const heading=h1?.innerText||"";
      const targeted=[
        document.querySelector("[itemprop=articleBody]"),
        document.querySelector("article .entry-content"),
        document.querySelector("article .article-body"),
        document.querySelector("main article"),
        document.querySelector("article"),
        document.querySelector("main")
      ].filter(Boolean);
      const article=targeted[0];
      const articleText=article?.innerText||"";
      const idx=heading?all.indexOf(heading):-1;
      const after=idx>=0?all.slice(idx+heading.length):all;
      const top=after.slice(0,9000);
      const dialog=[...document.querySelectorAll("[role=dialog],.modal,[class*=paywall],[class*=subscriber]")]
        .filter(el=>{let b=el.getBoundingClientRect(),st=getComputedStyle(el);
          return b.width>200&&b.height>100&&st.display!=="none"&&st.visibility!=="hidden"&&st.opacity!=="0";
        }).map(el=>(el.innerText||"").slice(0,250)).slice(0,4);
      const metas=[...document.querySelectorAll('script[type="application/ld+json"]')]
        .map(e=>e.textContent).join("").slice(0,15000);
      return {all:all.slice(0,50000),heading,articleText:articleText.slice(0,22000),
        after:top,dialogs:dialog,structured:metas,links:[...document.querySelectorAll("a")]
          .filter(a=>/accesso|abbonam|registraz/i.test(a.innerText||"")).length};
    });
    out.heading=dat.heading.slice(0,110);
    out.words=Math.max(toWords(dat.articleText),toWords(dat.after));
    out.total=toWords(dat.all);
    out.dialogs=dat.dialogs;
    if(!out.finalUrl.startsWith("https://")||suspiciousPages.test(new URL(out.finalUrl).pathname)){
      out.reason="redirect-to-gate";return out;
    }
    if(item.kind==="special"&&!looksLikeArticle(item.title,dat.heading)){
      out.reason="heading-mismatch";return out;
    }
    if(item.kind==="native"&&!looksLikeArticle(item.title,dat.heading)&&
       new URL(out.finalUrl).hostname!=="studiosensale.it"){
      out.reason="native-external-redirect";return out;
    }
    const paywallText=[dat.articleText,dat.after.slice(0,6000),...dat.dialogs].join("\n");
    if(forbidden.test(paywallText)){out.reason="visible-login-paywall";return out;}
    if(/isAccessibleForFree["']?\s*:\s*(?:false|["']false["'])/i.test(dat.structured)){
      out.reason="structured-paid";return out;
    }
    if(dat.dialogs.some(d=>/login|registr|abbon|accedi|contenuto riservato/i.test(d))){
      out.reason="blocking-dialog";return out;
    }
    // Fisco e Tasse può mostrare il login per i soli commenti: non è un paywall.
    const minWords=item.kind==="native"?100:item.kind==="official"&&item.source.startsWith("Gazzetta")?35:item.kind==="official"?60:item.kind==="special"?
      (item.source==="Fiscal Focus"?85:170):95;
    if(out.words<minWords){out.reason="insufficient-readable-text";return out;}
    out.status="PASS";out.reason="rendered-anonymous-article";
  }catch(e){out.reason="browser-error:"+String(e.message||e).slice(0,110)}
  finally{await context.close().catch(()=>{})}
  return out;
}
async function pool(items,limit,fn){
  let cursor=0;const out=new Array(items.length);
  await Promise.all(Array.from({length:limit},async()=>{
    while(cursor<items.length){const i=cursor++;out[i]=await fn(items[i]);}
  }));
  return out;
}
(async()=>{
 const spec=JSON.parse(fs.readFileSync(SPECIAL,"utf8"));
 const off=JSON.parse(fs.readFileSync(OFFICIAL,"utf8"));
 const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 const context=await browser.newContext({locale:"it-IT"});
 const site=await context.newPage();
 await site.goto(NEWS,{waitUntil:"domcontentloaded",timeout:30000});
 await site.locator("a.external-archive-card").first().waitFor({state:"attached",timeout:22000});
 const cards=await site.locator("#news-items > a.editorial-card").evaluateAll(nodes=>nodes.map(a=>({
   kind:a.classList.contains("external-archive-card")?"special":
     a.classList.contains("official-archive-card")?"official":"native",
   url:a.href,
   title:a.querySelector("h3")?.textContent?.trim()||"",
   source:a.querySelector("p")?.textContent?.split(" · ")[0]||"",
 })));
 await context.close();
 const unique=new Map();
 for(const c of cards){unique.set(c.url,c)}
 for(const c of spec.items){if(!unique.has(c.url))unique.set(c.url,{...c,kind:"special"})}
 for(const c of off.items){if(!unique.has(c.url))unique.set(c.url,{...c,kind:"official"})}
 const arr=[...unique.values()];
 console.log("AUDIT_START "+JSON.stringify({siteCards:cards.length,unique:arr.length,
  kinds:arr.reduce((o,c)=>(o[c.kind]=(o[c.kind]||0)+1,o),{})}));
 const results=await pool(arr,5,item=>inspect(browser,item));
 await browser.close();
 const failed=results.filter(r=>r.status!=="PASS");
 const counts=results.reduce((o,r)=>((o[r.kind]??={pass:0,fail:0})[r.status==="PASS"?"pass":"fail"]++,o),{});
 for(const r of results){
   console.log("AUDIT_ITEM "+JSON.stringify({kind:r.kind,source:r.source,
    status:r.status,reason:r.reason,http:r.http,words:r.words,title:r.title,
    url:r.url,finalUrl:r.finalUrl,dialogs:r.dialogs}));
 }
 console.log("AUDIT_SUMMARY "+JSON.stringify({total:results.length,counts,
    failed:failed.length,reasons:failed.reduce((o,r)=>(o[r.reason]=(o[r.reason]||0)+1,o),{})}));
 if(apply){
   const permitted=new Set(results.filter(r=>r.kind==="special"&&r.status==="PASS").map(r=>r.url));
   const old=spec.items.length;spec.items=spec.items.filter(x=>permitted.has(x.url));
   spec.updated_at=new Date().toISOString();
   // Mantieni la modalita esistente compatibile con il codice Netlify.
   fs.writeFileSync(SPECIAL,JSON.stringify(spec,null,2)+"\n");
   console.log("AUDIT_FILTER_APPLIED "+JSON.stringify({old,kept:spec.items.length,removed:old-spec.items.length}));
 }
 if(failed.some(r=>r.kind==="native"||r.kind==="official")){
   console.error("AUDIT_REQUIRES_REVIEW internal/official failures; no automatic site modifications");
 }
 if(failed.length){
   console.error("AUDIT_BLOCKED: "+failed.length+" collegamenti non verificati; intervento necessario");
   process.exitCode=1;
 }
})().catch(e=>{console.error("AUDIT_FATAL",e.stack||e);process.exit(1)});
