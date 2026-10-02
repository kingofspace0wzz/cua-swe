import hashlib,json,re

def render(template,labels,value,route):
 number=str(value) if not isinstance(value,float) or not value.is_integer() else str(int(value))
 text=re.sub(r'{{\s*\$value\s*}}',lambda _:number,str(template))
 text=re.sub(r'{{\s*\$labels\.(\w+)\s*}}',lambda m:str(labels.get(m[1],'')),text)
 return re.sub(r'{{\s*\$route\.(\w+)\s*}}',lambda m:str(route.get(m[1],'')),text)

def generation_at(scenario,index):
 restart=(scenario or {}).get('restartAt')
 return 2 if restart is not None and index>=restart else 1

def epoch_context(profile,scenario,index):
 epoch=(profile.get('routing') or {}).get('epoch') or {}
 context={}
 for scope,spec in epoch.items():
  pairs=(spec or {}).get('pairs') or []
  if not pairs:
   context[scope]={};continue
  if (spec or {}).get('mode')=='evaluation':at=min(index,len(pairs)-1)
  else:at=min(generation_at(scenario,index)-1,len(pairs)-1)
  context[scope]=dict(pairs[at])
 return context

def scope_by_key(profile):
 mapping={}
 for scope,spec in ((profile.get('routing') or {}).get('epoch') or {}).items():
  for pair in (spec or {}).get('pairs') or []:
   for key in pair:mapping[key]=scope
 return mapping

def identity_template(template,profile,rule):
 if re.search(r'\$value\b',str(template)):return False
 routing=profile.get('routing') or {}
 epoch=routing.get('epoch') or {}
 runbook=routing.get('runbook') or {}
 mapping=scope_by_key(profile)
 for key in re.findall(r'\$route\.(\w+)',str(template)):
  policy=(epoch.get(mapping.get(key)) or {}).get('policy')
  if runbook.get(policy)!='identity':return False
 return True

def expected_routes(profile,scenario,index):
 context=epoch_context(profile,scenario,index)
 routes=[]
 for receiver in profile.get('receivers') or []:
  if receiver.get('matchScope'):match=dict(context.get(receiver['matchScope']) or {})
  else:match=dict(receiver.get('match') or {})
  routes.append({'name':receiver['name'],'family':receiver['family'],'match':match})
 return routes

def expected_deliveries(routes,history):
 counts=[0]*len(routes);unrouted=0
 for rows in history.values():
  last=rows[-1]
  if last['state']!='firing':continue
  for index,route in enumerate(routes):
   if all(last['labels'].get(k)==v for k,v in route['match'].items()):
    counts[index]+=1;break
  else:unrouted+=1
 return counts,unrouted

def expected(profile,scenario,cursor):
 rule=profile['rules'][0];result={}
 for target in scenario['targets']:
  rows=[];started=None
  for i,value in enumerate(target['values'][:cursor+1]):
   t=i*profile['interval']
   context=epoch_context(profile,scenario,i);route={k:v for pairs in context.values() for k,v in pairs.items()}
   if scenario.get('restartAt')==i:started=None
   condition=value is not None and value>rule['query']['threshold']
   if not condition:started=None
   elif started is None:started=t
   labels={**target['labels'],'alertname':rule['name']};annotations={k:render(v,target['labels'],value,route) for k,v in rule['annotations'].items()}
   labels.update({k:render(v,target['labels'],value,route) for k,v in rule['labels'].items()})
   for field in rule['enrichments']:
    destination=labels if identity_template(field['template'],profile,rule) else annotations
    destination[field['name']]=render(field['template'],target['labels'],value,route)
   fp=hashlib.sha256(json.dumps(dict(sorted(labels.items())),separators=(',',':')).encode()).hexdigest()[:10] if condition else None
   rows.append({'t':t,'value':value,'condition':condition,'state':'inactive' if not condition else 'firing' if t-started>=rule['forSeconds'] else 'pending','activeAt':started,'fingerprint':fp,'labels':labels if condition else {},'annotations':annotations if condition else {}})
  result[target['id']]=rows
 return result
