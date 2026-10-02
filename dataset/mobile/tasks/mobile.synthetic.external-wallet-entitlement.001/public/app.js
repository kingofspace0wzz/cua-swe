import {admission} from './wallet.js';
import {readInbox,validate} from './provider.js';
import {element as el,documentView} from './viewer.js';
const USER='civic-gate-user';
let inbox=readInbox();
let user=JSON.parse(localStorage.getItem(USER)||'{"notes":{}}');
let route='wallet';
let notice='';
const root=document.querySelector('#app');
const save=()=>localStorage.setItem(USER,JSON.stringify(user));
function selected(){return inbox?.passes.find(p=>p.passId===user.selected)||inbox?.passes[0];}
function button(text,action,cls='secondary') {const b=el('button',text,cls);b.type='button';b.onclick=action;return b;}
function navigate(next){route=next;notice='';render();window.scrollTo(0,0);}
function heading(title){const top=el('header');top.append(el('p','CIVIC GATE','eyebrow'),el('h1',title));return top;}
function render(){
 root.replaceChildren(heading(route==='wallet'?'Your pass wallet':route==='details'?'Issuer details':route==='receipts'?'Validation receipts':'Confirm visit'));
 if(!inbox?.passes?.length){root.append(el('section','No imported passes. This standalone sandbox starts empty until an issuer inbox is imported by the prepared runtime.','card'));return;}
 const p=selected();user.selected=p.passId;save();
 if(route==='wallet'){
  const tabs=el('nav',undefined,'pass-list');tabs.setAttribute('aria-label','Passes');
  for(const pass of inbox.passes){const b=button(pass.title,()=>{user.selected=pass.passId;save();notice='';render();},pass===p?'selected':'pass-tab');b.setAttribute('aria-pressed',String(pass===p));tabs.append(b);}root.append(tabs);
  const card=el('section',undefined,'card pass-card');card.append(el('p',p.passId,'eyebrow'),el('h2',p.title),el('p',p.subtitle,'muted'));
  const a=admission(p.issuerRecord);
  card.append(el('p',`${a.visits} complete visits`,'availability'),el('p',`Status: ${a.state}`,'status'));
  const action=button('Validate one visit',()=>navigate('confirm'),'primary');action.disabled=!a.enabled;card.append(action);
  if(!a.enabled)card.append(el('p','Validation unavailable. Inspect issuer details for the current terms.','muted'));
  const links=el('div',undefined,'actions');links.append(button('Issuer details',()=>navigate('details')),button('Receipts',()=>navigate('receipts')));card.append(links);root.append(card);
  const notes=el('section',undefined,'card');const label=el('label','Pass note');label.htmlFor='note';const input=el('textarea');input.id='note';input.rows=2;input.value=user.notes[p.passId]||'';input.oninput=()=>{user.notes[p.passId]=input.value;save();};notes.append(label,input,el('p','Saved on this device, separately for each pass.','muted'));root.append(notes);
 }else{
  root.append(button('Back to wallet',()=>navigate('wallet')),el('h2',p.title));
  if(route==='details'){
   root.append(el('p',inbox.providerName,'muted'));
   const guide=el('section',undefined,'card');guide.append(el('h2','Issuer reading guide'));
   for(const item of inbox.contract){const d=el('details');d.append(el('summary',item.title),el('p',item.text));guide.append(d);}root.append(guide);
   const record=el('section',undefined,'card');record.append(el('h2','Imported issuer record'),documentView(p.issuerRecord));root.append(record);
  }else if(route==='receipts'){
   root.append(el('p','Newest first · supplied by the imported issuer sandbox','muted'));
   for(const receipt of p.receipts){const section=el('section',undefined,'card receipt');section.append(el('h2',receipt.result==='accepted'?'Accepted':'Refused'),documentView(receipt));root.append(section);}
  }else{
   const a=admission(p.issuerRecord);const card=el('section',undefined,'card');card.append(el('p','Validate one complete visit?'),el('p','Only Confirm validation sends a request. Cancel leaves this pass unchanged.','muted'));
   card.append(button('Confirm validation',()=>{const current=admission(p.issuerRecord);if(!current.enabled)return;validate(inbox,p,current.request);navigate('receipts');},'primary'),button('Cancel',()=>navigate('wallet')));root.append(card);
  }
 }
 root.append(el('footer','Standalone issuer sandbox · imported records persist on reload.'));
}
render();
