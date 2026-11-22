/* Studio Sensale - notizie live nelle sette categorie editoriali */
(() => {
  "use strict";
  const raw = "https://raw.githubusercontent.com/rinosensa62-prog/studio-sensale-sito/main/assets/";
  const categories = {
    "bandi-finanziamenti":"Bandi e finanziamenti",
    "imprese-partita-iva":"Aprire e gestire un’attività",
    "lavoro-paghe":"Lavoro e paghe",
    "caf-famiglie":"Famiglie e CAF",
    "fisco-dichiarazioni":"Dichiarazioni e Fisco",
    "locazioni-immobili":"Locazioni e immobili",
    "successioni-tributi-locali":"Successioni e tributi locali"
  };
  const path = location.pathname.replace(/\/?$/, "/");
  const slug = path.startsWith("/argomenti/") ? path.split("/")[2] : "";
  const category = categories[slug];
  const home = path === "/", archive = path === "/notizie/";
  if (!category && !home && !archive) return;
  const trusted = ["agenziaentrate.gov.it","fiscooggi.it","inps.it","inail.it",
    "lavoro.gov.it","mimit.gov.it","invitalia.it","mef.gov.it",
    "gazzettaufficiale.it","fiscoetasse.com","fiscal-focus.it",
    "informazionefiscale.it","ecnews.it","eutekne.info","ipsoa.it",
    "redazionefiscale.it","lavorosi.it"];
  const ignored = /(?:indebit.{0,80}(?:send|notific)|(?:send|notific).{0,80}indebit)/i;
  function normalized(s){ return String(s||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"")
    .toLowerCase().replace(/[^a-z0-9]/g,"").slice(0,150); }
  function valid(x) {
    if (!x || !x.title || !x.url || !x.published_at ||
        !Object.values(categories).includes(x.category) || ignored.test(x.title)) return false;
    try { const u = new URL(x.url);
      return u.protocol === "https:" &&
        trusted.some(host=>u.hostname===host || u.hostname.endsWith("."+host));
    } catch(e){ return false; }
  }
  function filtered(list) {
    const urls=new Set(),titles=new Set();
    return list.filter(valid)
      .sort((a,b)=>new Date(b.published_at)-new Date(a.published_at))
      .filter(x=>{const title=normalized(x.title),url=x.url.split("?")[0];
        if(urls.has(url)||titles.has(title))return false;
        urls.add(url);titles.add(title);return true;});
  }
  const el=(tag,cls,txt)=>{const e=document.createElement(tag);if(cls)e.className=cls;
    if(txt!==undefined)e.textContent=txt;return e;};
  function where() {
    const headings=[...document.querySelectorAll("main h1,main h2,main h3")];
    const needle=archive ? /notizie che contano|notizie/i :
      home ? /notizie e aggiornamenti selezionati/i : /notizie e approfondimenti/i;
    const h=headings.find(x=>needle.test(x.textContent)) || headings[0];
    return h && (h.closest(".section-heading,.section-header") || h);
  }
  function addStyle(){
    if(document.getElementById("studio-news-style"))return;
    const s=el("style");s.id="studio-news-style";
    s.textContent=".studio-news-live{margin:1.2rem 0 2rem;clear:both;width:100%}" +
      ".studio-news-live h2{font-size:1.18rem;color:#113b37;margin:0 0 .4rem}" +
      ".studio-news-live>p{font-size:.88rem;color:#405d60;line-height:1.5;margin:0 0 1.1rem}" +
      ".studio-news-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,270px),1fr));gap:1rem}" +
      ".studio-news-item{background:#fff;border:1px solid #cedbd8;border-radius:12px;padding:1.2rem;" +
        "box-shadow:0 2px 7px rgba(10,36,32,.05);display:flex;flex-direction:column;gap:.6rem}" +
      ".studio-news-item h3{font-size:1.04rem;line-height:1.4;color:#142f2d;margin:0}" +
      ".studio-news-item a{color:#0b665c;text-decoration:underline;text-underline-offset:3px}" +
      ".studio-news-meta,.studio-news-note{font-size:.78rem;color:#485f61;line-height:1.45}" +
      ".studio-news-note{margin-top:auto}" +
      "@media(max-width:650px){.studio-news-grid{grid-template-columns:1fr}}";
    document.head.appendChild(s);
  }
  function formatDate(dt) {
    try{return new Intl.DateTimeFormat("it-IT",{day:"2-digit",month:"2-digit",year:"numeric"})
      .format(new Date(dt));}catch(e){return "";}
  }
  function paint(items) {
    const anchor=where();if(!anchor)return;
    const matching=items.filter(x=>!category||x.category===category)
      .slice(0,home?8:archive?40:20);
    if(!matching.length)return;
    addStyle();
    document.getElementById("studio-news-live")?.remove();
    const section=el("section","studio-news-live");section.id="studio-news-live";
    section.setAttribute("aria-label","Notizie aggiornate dalle fonti");
    section.appendChild(el("h2","", "Notizie e aggiornamenti recenti"));
    section.appendChild(el("p","",
      "Segnalazioni in ordine di pubblicazione, organizzate per argomento. " +
      "Le fonti specialistiche sono spunti esterni da verificare; non sostituiscono consulenza o normativa."));
    const grid=el("div","studio-news-grid");
    for(const x of matching){
      const card=el("article","studio-news-item");
      card.appendChild(el("span","studio-news-meta",formatDate(x.published_at)+" · "+x.source));
      const h=el("h3"),a=el("a","",x.title);
      a.href=x.url;a.target="_blank";a.rel="noopener noreferrer";
      h.appendChild(a);card.appendChild(h);
      card.appendChild(el("span","studio-news-note",
        x.status==="link_esterno_da_verificare"
        ?"Testata specialistica · verifica normativa necessaria"
        :"Fonte istituzionale · verifica requisiti e decorrenza"));
      grid.appendChild(card);
    }
    section.appendChild(grid);anchor.insertAdjacentElement("afterend",section);
  }
  async function run(){
    const token=Math.floor(Date.now()/60000);
    const results=await Promise.allSettled(
      ["aggiornamenti-ufficiali.json","spunti-editoriali.json"]
       .map(async name=>{const response=await fetch(raw+name+"?t="+token,{cache:"no-store"});
         if(!response.ok)throw new Error(name);
         const json=await response.json();
         return Array.isArray(json.items)?json.items:[];}));
    const items=filtered(results.filter(x=>x.status==="fulfilled").flatMap(x=>x.value));
    if(items.length)paint(items);
  }
  if(document.readyState==="loading")
    document.addEventListener("DOMContentLoaded",()=>run().catch(console.warn));
  else run().catch(console.warn);
})();
