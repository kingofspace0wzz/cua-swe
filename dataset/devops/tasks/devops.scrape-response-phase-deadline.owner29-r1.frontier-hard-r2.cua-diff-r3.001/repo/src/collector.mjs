import {fetchMetrics} from './scrape.mjs';
import {parseMetrics} from './metrics.mjs';
export async function collectTarget(origin,target){
 const body=await fetchMetrics(new URL(target.path,origin));
 const samples=parseMetrics(body);
 const response=await fetch(new URL('/ingest',origin),{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({id:target.id,samples}),signal:AbortSignal.timeout(500)});
 if(!response.ok)throw new Error('ingestion_rejected');
 return {id:target.id,samples:samples.length};
}
