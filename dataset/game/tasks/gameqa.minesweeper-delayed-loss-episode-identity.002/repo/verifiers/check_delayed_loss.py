#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, time
from pathlib import Path
from playwright.sync_api import sync_playwright
SEEDS=(42,160,1337)
EXPECTED_DELAY_MS=1600

def state(page): return page.evaluate("window.gameAPI.getState()")
def game_expr(): return "(window.__minesweeperMineTarget || (Array.isArray(window.minesweeperGames) ? window.minesweeperGames[0] : window.minesweeperGames[Object.keys(window.minesweeperGames)[0]]))"
def reset_api(page,seed):
    result=page.evaluate("s => window.gameAPI.reset({seed:s})",seed); assert result["ok"],result; page.wait_for_timeout(80)
def face_reset(page):
    face=page.locator('.minesweeper-game span').nth(2); face.click(); page.wait_for_timeout(80)
def mine_positions(page): return page.evaluate(game_expr()+".__minePositions")
def all_unknown(s): return all(cell=="⬜" for row in s["game_state"]["environment"] for cell in row)
def trigger_direct(page,seed):
    reset_api(page,seed); page.locator('td').nth(40).click(); page.wait_for_timeout(50); mine=mine_positions(page)[0]; page.locator('td').nth(mine[0]*9+mine[1]).click(); return {"mine":mine}
def trigger_chord(page,seed):
    reset_api(page,seed); page.locator('td').nth(40).click(); page.wait_for_timeout(50)
    data=page.evaluate("""() => { const g="""+game_expr()+"""; const board=window.gameAPI.getState().game_state.environment; const mines=g.__minePositions||[]; const ms=new Set(mines.map(x=>x.join(','))); for(let r=0;r<9;r++)for(let c=0;c<9;c++){ if(!/^[1-8]/.test(board[r][c]))continue; const n=parseInt(board[r][c],10),adj=[]; for(let dr=-1;dr<=1;dr++)for(let dc=-1;dc<=1;dc++){if(!dr&&!dc)continue;const rr=r+dr,cc=c+dc;if(rr>=0&&cc>=0&&rr<9&&cc<9)adj.push([rr,cc]);} const actual=adj.filter(x=>ms.has(x.join(','))), safe=adj.filter(x=>!ms.has(x.join(','))&&board[x[0]][x[1]]==='⬜'); if(actual.length===n&&safe.length>=n)return {cell:[r,c],actual,wrong:safe.slice(0,n)};} return null; }""")
    assert data,"no chord fixture"
    for r,c in data["wrong"]: page.locator('td').nth(r*9+c).click(button='right')
    r,c=data["cell"]; page.locator('td').nth(r*9+c).dblclick(); return data
def check_delay(page,trigger,label,evidence,failures):
    trigger_data=trigger(); t0=time.monotonic(); page.wait_for_timeout(150); early=state(page); page.wait_for_timeout(1100); middle=state(page); page.wait_for_timeout(650); late=state(page); elapsed=int((time.monotonic()-t0)*1000)
    evidence[label]={"trigger":trigger_data,"early":early,"middle":middle,"late":late,"elapsed_ms":elapsed}
    if early["debug"]["engine_state"]!="started" or "💥" not in [c for row in early["game_state"]["environment"] for c in row]: failures.append(label+": loss did not enter visible pending state")
    if middle["debug"]["engine_state"]!="started": failures.append(label+": loss committed before protected handoff window")
    if late["debug"]["engine_state"]!="lost" or not late["terminal"]["isTerminal"]: failures.append(label+": loss did not commit near protected handoff")
def check_restart(page,trigger,resetter,label,evidence,failures):
    trigger_data=trigger(); page.wait_for_timeout(180); resetter(); fresh=state(page); page.wait_for_timeout(3500); settled=state(page); evidence[label]={"trigger":trigger_data,"fresh":fresh,"settled":settled}
    if not all_unknown(fresh) or fresh["debug"]["engine_state"]!="not_started": failures.append(label+": reset did not create fresh board")
    if not all_unknown(settled) or settled["debug"]["engine_state"]!="not_started" or settled["terminal"]["isTerminal"]: failures.append(label+": fresh board inherited prior loss")
def main():
    p=argparse.ArgumentParser(); p.add_argument('--url',default='http://127.0.0.1:4394/'); p.add_argument('--evidence-dir',type=Path,default=Path('verifier-artifacts')); a=p.parse_args(); a.evidence_dir.mkdir(parents=True,exist_ok=True)
    failures=[]; evidence={"expected_delay_ms":EXPECTED_DELAY_MS,"failures":failures,"checks":{}}
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True); page=browser.new_page(viewport={"width":1280,"height":720}); page.goto(a.url,wait_until='load'); page.wait_for_function('window.gameAPI && window.gameAPI.getState().debug.game_ready')
        for seed in SEEDS:
            reset_api(page,seed); page.locator('td').nth(40).click(); page.wait_for_timeout(40); s=state(page); evidence["checks"][f"first-click-{seed}"]=s
            if s["debug"]["engine_state"]=="lost" or s["terminal"]["isTerminal"]: failures.append(f"seed {seed}: first click was unsafe")
        reset_api(page,42); before=state(page); page.locator('td').nth(0).click(button='right'); marked=state(page); page.locator('td').nth(0).click(button='right'); question=state(page); page.locator('td').nth(0).click(button='right'); restored=state(page); evidence["checks"]["marker-cycle"]={"before":before,"marked":marked,"question":question,"restored":restored}
        if [before["metrics"]["remaining_mines"],marked["metrics"]["remaining_mines"],question["metrics"]["remaining_mines"],restored["metrics"]["remaining_mines"]] != [10,9,10,10]: failures.append("flag/question counter cycle changed")
        check_delay(page,lambda:trigger_direct(page,42),"direct-delay",evidence["checks"],failures)
        check_delay(page,lambda:trigger_chord(page,42),"chord-delay",evidence["checks"],failures)
        check_restart(page,lambda:trigger_direct(page,160),lambda:reset_api(page,160),"direct-api-reset",evidence["checks"],failures)
        check_restart(page,lambda:trigger_direct(page,1337),lambda:face_reset(page),"direct-face-reset",evidence["checks"],failures)
        check_restart(page,lambda:trigger_chord(page,42),lambda:reset_api(page,42),"chord-api-reset",evidence["checks"],failures)
        check_restart(page,lambda:trigger_chord(page,160),lambda:face_reset(page),"chord-face-reset",evidence["checks"],failures)
        page.screenshot(path=str(a.evidence_dir/'final.png'),full_page=True); browser.close()
    (a.evidence_dir/'delayed-loss-state.json').write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+"\n")
    if failures: raise AssertionError('; '.join(failures))
    print(json.dumps({"status":"pass","checks":len(evidence["checks"])},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
