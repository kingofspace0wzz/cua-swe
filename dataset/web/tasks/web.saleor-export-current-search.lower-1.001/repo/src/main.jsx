import React, {useEffect, useMemo, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {buildExportRequest} from './exportRequest.js';
import './styles.css';

function App(){
  const [workspace,setWorkspace]=useState(null); const [open,setOpen]=useState(false); const [preview,setPreview]=useState(null);
  const filters=useMemo(()=>[{label:'Category',value:'Shoes'},{label:'Status',value:'Published'}],[]);
  useEffect(()=>{fetch('/api/workspace').then(r=>r.json()).then(setWorkspace)},[]);
  async function runPreview(){const body=buildExportRequest('CURRENT_SEARCH',filters,workspace.export);const r=await fetch('/api/export-preview',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});setPreview(await r.json())}
  return <main><nav><strong>Northstar Commerce</strong><span>Catalog</span><span>Orders</span><span>Channels</span></nav><section className="page"><div className="heading"><div><p className="eyebrow">Products</p><h1>All products</h1></div><button onClick={()=>setOpen(true)}>Export</button></div><div className="filters"><button>Category: Shoes ×</button><button>Status: Published ×</button><span>3 results</span></div><table><thead><tr><th>Product</th><th>SKU</th><th>Status</th><th>Channel</th></tr></thead><tbody>{[['Trail runner','TR-18'],['Court classic','CC-02'],['City boot','CB-77']].map(([n,s])=><tr key={s}><td>{n}</td><td>{s}</td><td><span className="live">Published</span></td><td>Online</td></tr>)}</tbody></table></section>{open&&<div className="scrim"><section className="modal" role="dialog"><button className="close" onClick={()=>setOpen(false)}>×</button><p className="eyebrow">Export products</p><h2>Choose export scope</h2><label className="choice"><input type="radio" defaultChecked/> Current search <small>Use the filters currently visible in the product list.</small></label><details><summary>Workspace export guide</summary><p>{workspace?.export.guide}</p></details><button onClick={runPreview}>Preview export</button>{preview&&<div className={preview.ok?'result ok':'result error'}>{preview.ok?`${preview.count} products ready`:preview.message}</div>}</section></div>}</main>}
createRoot(document.getElementById('root')).render(<App/>);
