from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
HERE=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent)
def violations():
    expected=json.loads((HERE/'build_integrity.json').read_text());bad=[]
    for rel,digest in expected.items():
        p=ROOT/rel
        if any(x.is_symlink() for x in [p,*list(p.parents)[:len(Path(rel).parts)-1]]) or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:bad.append(rel)
    for parent,dirs,files in os.walk(ROOT,followlinks=False):
        if Path(parent)==ROOT:dirs[:]=[d for d in dirs if d not in {'.git','node_modules','verifiers','dist'}]
        for name in dirs+files:
            p=Path(parent)/name
            if p.is_symlink():bad.append(str(p.relative_to(ROOT)))
    return sorted(set(bad))
if __name__=='__main__':
    bad=violations()
    if bad:print(json.dumps({'passed':False,'integrity_violations':bad}));sys.exit(1)
    result=subprocess.run(['node','build.mjs'],cwd=ROOT,timeout=20)
    sys.exit(result.returncode)
