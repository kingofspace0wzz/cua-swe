import hashlib,json,re

def render(template,labels,value):
 number=str(value) if not isinstance(value,float) or not value.is_integer() else str(int(value))
 text=re.sub(r'{{\s*\$value\s*}}',lambda _:number,str(template))
 return re.sub(r'{{\s*\$labels\.(\w+)\s*}}',lambda m:str(labels.get(m[1],'')),text)

def _key(labels):
 return hashlib.sha256(json.dumps(dict(sorted(labels.items())),separators=(',',':')).encode()).hexdigest()[:10]

def route_key(profile,target):
 rule=profile['rules'][0];route=profile['receivers'][0]
 labels={**target['labels'],'alertname':rule['name']}
 labels.update({k:render(v,target['labels'],'') for k,v in rule['labels'].items()})
 for field in rule['enrichments']:
  if field['name'] in route['match']:
   labels[field['name']]=render(field['template'],target['labels'],'')
 return _key(labels)

def expected(profile,scenario,cursor):
 rule=profile['rules'][0];route=profile['receivers'][0];result={}
 for target in scenario['targets']:
  rows=[];started=None
  for i,value in enumerate(target['values'][:cursor+1]):
   t=i*profile['interval']
   if scenario.get('restartAt')==i:started=None
   condition=value is not None and value>rule['query']['threshold']
   if not condition:started=None
   elif started is None:started=t
   labels={**target['labels'],'alertname':rule['name']};annotations={k:render(v,target['labels'],value) for k,v in rule['annotations'].items()}
   labels.update({k:render(v,target['labels'],value) for k,v in rule['labels'].items()})
   for field in rule['enrichments']:
    destination=labels if field['name'] in route['match'] else annotations
    destination[field['name']]=render(field['template'],target['labels'],value)
   fp=_key(labels) if condition else None
   rows.append({'t':t,'value':value,'condition':condition,'state':'inactive' if not condition else 'firing' if t-started>=rule['forSeconds'] else 'pending','activeAt':started,'fingerprint':fp,'labels':labels if condition else {},'annotations':annotations if condition else {}})
  result[target['id']]=rows
 return result
