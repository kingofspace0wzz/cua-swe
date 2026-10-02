from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(os.environ.get('CUA_SWE_WORKSPACE') or Path.cwd()).resolve()
HERE=Path(os.environ.get('CUA_SWE_VERIFIER_ROOT') or Path(__file__).resolve().parent)
def violations():
    expected=json.loads((HERE/'build_integrity.json').read_text())
    bad=[]
    for rel,digest in expected.items():
        p=ROOT/rel
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:bad.append(rel)
    for p in [ROOT/'src', *(ROOT/'src').rglob('*')]:
        if p.is_symlink():bad.append(str(p.relative_to(ROOT)))
    for name in ('.npmrc','node_modules'):
        if (ROOT/name).exists() or (ROOT/name).is_symlink():bad.append(name)
    return bad
if __name__=='__main__':
    bad=violations()
    if bad:
        print(json.dumps({'passed':False,'integrity_violations':bad}));sys.exit(1)
    result=subprocess.run(['node','build.mjs'],cwd=ROOT,timeout=30)
    sys.exit(result.returncode)
