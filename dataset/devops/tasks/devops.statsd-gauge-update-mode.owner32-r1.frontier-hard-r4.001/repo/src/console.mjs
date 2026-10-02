import {render} from './views.mjs';
let selected=null,tab='capture',snapshot=null;
async function api(path,post=false){const response=await fetch('/api/'+path,post?{method:'POST'}:{});if(!response.ok)throw new Error('Console request '+response.status);return response.json();}
async function refresh(){snapshot=await api('snapshot');selected??=snapshot.identities[0]??null;render(snapshot,selected,tab);}
let pending=false;
document.addEventListener('click',async event=>{
 const button=event.target.closest('button[data-action]');if(!button||pending)return;
 pending=true;
 try{const action=button.dataset.action;
  if(action==='select')selected=button.dataset.identity;
  if(action==='history')tab='history';if(action==='capture')tab='capture';
  if(action==='run'||action==='reset'){await api(action,true);tab='capture';}
  await refresh();
 }catch(e){document.getElementById('app').textContent=e.message;}finally{pending=false;}
});
await api('seed',true);await refresh();
setInterval(()=>{if(!pending)refresh().catch(()=>{});},100);
