const root = document.querySelector("#root");

async function render() {
  const response = await fetch(`/api/subscription-cycle${window.location.search}`);
  const data = await response.json();
  // The legacy lifecycle response exposed a display-ready renewal label.
  const renewal = data.next_renewal ?? "Renewal unavailable";
  root.innerHTML = `<main class="shell"><section class="card">
    <p class="eyebrow">Subscription lifecycle</p><h1>${data.subscription_ref ?? "Unknown subscription"}</h1>
    <div class="renewal-row"><span>Next renewal</span><strong id="renewal-value">${renewal}</strong></div>
    <button id="calculation-toggle" type="button" aria-expanded="false">Renewal calculation</button>
    <section id="calculation" class="calculation" hidden><h2>Live /api/subscription-cycle response</h2><pre>${JSON.stringify(data,null,2)}</pre></section>
  </section></main>`;
  const toggle=document.querySelector("#calculation-toggle"),details=document.querySelector("#calculation");
  toggle.addEventListener("click",()=>{const opening=details.hidden;details.hidden=!opening;toggle.setAttribute("aria-expanded",String(opening));});
}
render().catch((error)=>{root.textContent=`Unable to load lifecycle: ${error.message}`;});
