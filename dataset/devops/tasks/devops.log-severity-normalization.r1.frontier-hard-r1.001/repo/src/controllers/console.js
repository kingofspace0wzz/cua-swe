import {api} from '../api/client.js';
import {createIngestor} from '../pipeline/ingest.js';
import {render} from '../views/console.js';
export async function start(root) {
 const catalog=await api('catalog');
 const state={catalog,receiverId:null,filter:'all',tab:'logs',selected:null,snapshot:null};let ingestor;
 async function show(){state.snapshot=await api('snapshot');render(root,state);root.dataset.ready='yes';}
 async function ingest(snapshot) {
  ingestor=createIngestor(snapshot.receivers);
  for(const batch of snapshot.batches)ingestor.accept(batch);
  await api('ingest',{generation:snapshot.generation,...ingestor.snapshot()});
  state.receiverId=snapshot.receivers[0].id;state.selected=null;state.filter='all';await show();
 }
 root.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try {
   root.dataset.ready='no';
   if(button.dataset.scenario)await ingest(await api('scenario',{id:button.dataset.scenario}));
   else if(button.dataset.tab){state.tab=button.dataset.tab;await show();}
   else if(button.dataset.record){state.selected=button.dataset.record;await show();}
   else if(button.dataset.action==='reset'){state.tab='logs';await ingest(await api('restart',{}));}
   else if(button.dataset.action==='retry'){
    const batch=await api('replay',{});ingestor.accept(batch);
    await api('ingest',{generation:state.snapshot.generation,...ingestor.snapshot()});await show();
   }
  }catch(error){root.dataset.error=String(error);root.dataset.ready='yes';}
 });
 root.addEventListener('change',async event=>{
  if(event.target.dataset.test==='receiver'){state.receiverId=event.target.value;state.selected=null;}
  if(event.target.dataset.test==='filter'){state.filter=event.target.value;state.selected=null;}
  await show();
 });
 await ingest(await api('snapshot'));
}
