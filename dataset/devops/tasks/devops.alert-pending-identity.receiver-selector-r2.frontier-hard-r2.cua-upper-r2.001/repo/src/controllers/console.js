import {request} from '../api/client.js';
import {compileRule} from '../rules/compileRule.js';
import {store} from '../state/store.js';
import {render} from '../views/render.js';
export async function initialize(){
 store.catalog=await request('catalog');
 await request('configure',{rules:store.catalog.rules.map(compileRule)});
 store.snapshot=await request('snapshot');render(store);
 document.querySelector('#app').addEventListener('click',async event=>{
  const button=event.target.closest('button[data-action]');if(!button||store.busy)return;
  store.busy=true;
  try{
   const {action,value}=button.dataset;
   if(action==='view')store.view=value;
   else store.snapshot=await request(action,value?{id:value}:{});
   render(store);
  }finally{store.busy=false;}
 });
}
