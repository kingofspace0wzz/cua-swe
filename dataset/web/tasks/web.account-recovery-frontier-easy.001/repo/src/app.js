const root=document.querySelector("#root");
async function render(){
  const response=await fetch(`/api/recovery-risk${window.location.search}`);const data=await response.json();
  // The legacy risk response exposed a display-ready recovery channel.
  const recovery=data.recovery_channel??"Recovery unavailable";
  root.innerHTML=`<main class="shell"><section class="card"><p class="eyebrow">Account recovery</p><h1>${data.account_ref??"Unknown account"}</h1><div class="recovery-row"><span>Recommended channel</span><strong id="recovery-channel">${recovery}</strong></div><button id="trace-toggle" type="button" aria-expanded="false">Recovery decision trace</button><section id="trace" class="trace" hidden><h2>Live /api/recovery-risk response</h2><pre>${JSON.stringify(data,null,2)}</pre></section></section></main>`;
  const toggle=document.querySelector("#trace-toggle"),details=document.querySelector("#trace");toggle.addEventListener("click",()=>{const opening=details.hidden;details.hidden=!opening;toggle.setAttribute("aria-expanded",String(opening));});
}
render().catch((error)=>{root.textContent=`Unable to load recovery: ${error.message}`;});
