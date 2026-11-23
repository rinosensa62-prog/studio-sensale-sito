const {chromium}=require("playwright");
(async()=>{
 const browser=await chromium.launch({headless:true,args:["--no-sandbox"]});
 const page=await browser.newPage();
 page.on("console",m=>console.log("CONSOLE",m.type(),m.text().slice(0,500)));
 page.on("pageerror",e=>console.log("PAGEERROR",String(e).slice(0,700)));
 page.on("requestfailed",r=>console.log("REQUESTFAILED",r.url(),r.failure()?.errorText));
 page.on("response",r=>{if(/github|\.json|\.js/.test(r.url()))console.log("RESOURCE",r.status(),r.url().slice(0,230));});
 await page.goto("https://studiosensale.it/notizie/",{waitUntil:"domcontentloaded",timeout:30000});
 console.log("SCRIPTS",JSON.stringify(await page.locator("script").evaluateAll(a=>a.map(x=>({src:x.src,inline:x.textContent.slice(0,200)}))).catch(e=>String(e))).slice(0,6000));
 await page.waitForTimeout(11000);
 console.log("EXTERNAL",await page.locator("a.external-archive-card").count());
 await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1})