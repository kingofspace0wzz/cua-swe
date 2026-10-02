const root=document.querySelector("#root");
async function render(){
  const response=await fetch(`/api/delegated-action${window.location.search}`);const data=await response.json();
  // The retired authorization feed exposed a display-ready delegated action.
  const action=data.legacy_action??"Action unavailable";
  root.innerHTML=`<main class="shell"><section class="card"><p class="eyebrow">Delegated authorization</p><h1>${data.request_ref??"Unknown request"}</h1><div class="recovery-row"><span>Available action</span><strong id="delegated-action">${action}</strong></div><button id="trace-toggle" type="button" aria-expanded="false">Delegation decision trace</button><section id="trace" class="trace" hidden><h2>Live /api/delegated-action response</h2><pre>${JSON.stringify(data,null,2)}</pre></section></section></main>`;
  const toggle=document.querySelector("#trace-toggle"),details=document.querySelector("#trace");toggle.addEventListener("click",()=>{const opening=details.hidden;details.hidden=!opening;toggle.setAttribute("aria-expanded",String(opening));});
}
render().catch((error)=>{root.textContent=`Unable to load delegation: ${error.message}`;});
