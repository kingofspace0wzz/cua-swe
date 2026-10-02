// Parse the supported Prometheus text exposition subset; commit only whole payloads.
export function parseMetrics(body){
 const samples=[];
 for(const line of body.split(/\r?\n/)){
  if(!line.trim()||line.startsWith('#'))continue;
  const m=line.match(/^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+(-?(?:\d+(?:\.\d+)?|\.\d+))$/);
  if(!m)throw new Error('invalid_metrics_payload');
  const labels={};let rest=m[2]||'';
  while(rest){const l=rest.match(/^([a-zA-Z_][a-zA-Z0-9_]*)="([^"\\]*)"(?:,|$)/);if(!l)throw new Error('invalid_metric_labels');if(l[1] in labels)throw new Error('duplicate_metric_label');labels[l[1]]=l[2];rest=rest.slice(l[0].length);}
  samples.push({name:m[1],labels,value:Number(m[3])});
 }
 if(!samples.length)throw new Error('empty_metrics_payload');return samples;
}
