const root=document.querySelector("#root");
async function render(){
  const response=await fetch(`/api/tax-estimate${window.location.search}`);const data=await response.json();
  // The retired calculator exposed a display-ready estimate.
  const estimate=data.legacy_tax??"Tax unavailable";
  root.innerHTML=`<main class="shell"><section class="card"><p class="eyebrow">Tax estimate</p><h1>${data.cart_ref??"Unknown cart"}</h1><div class="tax-row"><span>Estimated tax</span><strong id="tax-estimate">${estimate}</strong></div><button id="trace-toggle" type="button" aria-expanded="false">Tax calculation details</button><section id="trace" class="trace" hidden><h2>Live /api/tax-estimate payload</h2><pre>${JSON.stringify(data,null,2)}</pre></section></section></main>`;
  const toggle=document.querySelector("#trace-toggle"),details=document.querySelector("#trace");toggle.addEventListener("click",()=>{const opening=details.hidden;details.hidden=!opening;toggle.setAttribute("aria-expanded",String(opening));});
}
render().catch((error)=>{root.textContent=`Unable to load tax: ${error.message}`;});
