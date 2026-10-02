// Generic imported-document viewer. No contract-specific field mapping.
export function element(tag, text, cls) {
  const node=document.createElement(tag);
  if(text !== undefined) node.textContent=String(text);
  if(cls)node.className=cls;
  return node;
}
const primitive = value => value === null || typeof value !== 'object';
function compact(value) {
  return Object.entries(value).map(([key,v]) => `${key}: ${v}`).join(' · ');
}
export function documentView(value) {
  if(primitive(value))return element('span', value ?? 'null');
  if(!Array.isArray(value) && Object.values(value).every(primitive))return element('p',compact(value),'compact');
  const box=element('div',undefined,'document');
  if(Array.isArray(value)) {
    value.forEach((item,index)=>{
      const section=element('details');
      const title=typeof item==='object' && item ? Object.entries(item).filter(([,v])=>primitive(v)).slice(0,2).map(([,v])=>v).join(' · ') : String(item);
      section.append(element('summary',title || `Item ${index+1}`),documentView(item));box.append(section);
    });
  } else {
    for(const [key,item] of Object.entries(value)) {
      const field=element('section',undefined,'field');
      field.append(element('h3',key),documentView(item));box.append(field);
    }
  }
  return box;
}
