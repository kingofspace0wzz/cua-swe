from pathlib import Path
import hashlib,json,os,subprocess,sys
W=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
V=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent).resolve()
def violations():
 spec=json.loads((V/'build_integrity.json').read_text());bad=[]
 for rel,digest in spec['source'].items():
  p=W/rel
  if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:bad.append('protected source: '+rel)
 for p in W.rglob('*'):
  if '.git' in p.parts or 'node_modules' in p.parts:continue
  if p.is_symlink():bad.append('source symlink: '+str(p.relative_to(W)))
 if (W/'verifiers').exists():
  for rel,digest in spec['verifiers'].items():
   p=W/'verifiers'/rel
   if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:bad.append('protected verifier: '+rel)
 return bad
if __name__=='__main__':
 bad=violations()
 if bad:print(json.dumps({'passed':False,'integrity_violations':bad}));sys.exit(1)
 sys.exit(subprocess.run(['node','build.mjs'],cwd=W,timeout=20).returncode)
