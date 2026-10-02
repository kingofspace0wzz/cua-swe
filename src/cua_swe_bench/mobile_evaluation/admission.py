from __future__ import annotations
import fcntl
import json
from pathlib import Path
from .core import Fault, Protocol, canonical, digest, evidence, output_path, verify_ref, write_json

NORMAL = {'submitted', 'response_cap', 'time_cap'}
INVALID = {'source', 'sandbox', 'provider', 'wrong_model', 'missing_instruction', 'image_delivery', 'grader', 'runtime', 'baseline', 'configuration', 'harness'}


def classify(agent, grading, health, faults=()):
    faults = list(faults) + agent.get('faults', [])
    used = bool(agent.get('images_delivered'))
    result = {'execution_valid': False, 'software_correct': None, 'cua_used': used,
              'success_without_cua': False, 'scorable': False, 'faults': faults}
    if any(f.get('category') == 'scope' for f in faults):
        result['classification'] = 'scope_violation'; return result
    if faults:
        result['classification'] = 'infrastructure_interface_invalid'; return result
    required = {'instruction', 'source', 'shell_before', 'shell_after', 'runtime_before', 'grader_controls', 'baseline'}
    if any(health.get(k) is not True for k in required) or agent.get('responses', 0) < 1 or agent.get('termination') not in NORMAL or grading is None:
        result['classification'] = 'unscorable_missing_evidence'; return result
    if not agent.get('returned_models') or set(agent['returned_models']) != {Protocol().model}:
        result['classification'] = 'infrastructure_interface_invalid'; return result
    if type(grading.get('correct')) is not bool:
        result['classification'] = 'unscorable_missing_evidence'; return result
    result.update(execution_valid=True, scorable=True, software_correct=grading['correct'],
                  success_without_cua=grading['correct'] and not used,
                  classification='valid_success' if grading['correct'] else 'valid_model_failure')
    return result


def append_ledger(path, attempt_ref):
    if not verify_ref(attempt_ref): raise Fault('evidence', 'attempt result missing/changed')
    path = output_path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0); rows = [json.loads(x) for x in f if x.strip()]
        previous = rows[-1]['hash'] if rows else None
        if any(r['attempt'] == attempt_ref for r in rows): raise Fault('evidence', 'duplicate ledger append')
        entry = {'sequence': len(rows), 'previous': previous, 'attempt': attempt_ref}
        entry['hash'] = digest(entry)
        f.write(json.dumps(entry, sort_keys=True) + '\n'); f.flush()
        import os
        os.fsync(f.fileno())
    return entry


def ledger_attempts(path):
    attempts, previous = [], None
    for i, line in enumerate(Path(path).read_text().splitlines()):
        r = json.loads(line)
        unhashed = {k: v for k, v in r.items() if k != 'hash'}
        if r.get('sequence') != i or r.get('previous') != previous or digest(unhashed) != r.get('hash') or not verify_ref(r['attempt']):
            raise Fault('evidence', 'ledger chain or artifact mismatch')
        a = json.loads(Path(r['attempt']['path']).read_text()); a['_ref'] = r['attempt']; attempts.append(a)
        previous = r['hash']
    return attempts


def validate_evidence(attempt):
    """Verify primary content, not merely a plausible summary or process exit."""
    import base64
    import hashlib
    from .core import Task
    refs = attempt.get('artifacts', [])
    if not refs or not all(verify_ref(x) for x in refs): return False
    grouped = {}
    for r in refs: grouped.setdefault(Path(r['path']).name, []).append(r)
    required = {'protocol.json', 'task.json', 'harness.json', 'agent.json', 'baseline.json', 'patch.json', 'grade.json', 'controls.json', 'prompt.json'}
    if not required <= set(grouped): return False
    def load(name):
        # Prefer the attempt root record rather than an inner runtime/baseline artifact.
        r = min(grouped[name], key=lambda r: len(Path(r['path']).parts))
        return json.loads(Path(r['path']).read_text())
    try:
        protocol, task, code = load('protocol.json'), Task(load('task.json')), load('harness.json')
        if attempt.get('purpose', 'candidate') != task.c.get('purpose', 'candidate'):
            return False
        identity = {**task.identity, 'protocol_digest': digest(protocol), 'harness_digest': digest(code),
                    'controls_digest': digest(task.c.get('controls', {}))}
        if identity != attempt.get('identity') or protocol != attempt.get('protocol'): return False
        agent = load('agent.json')
        if agent != attempt.get('agent') or load('grade.json') != attempt.get('grade'): return False
        if load('controls.json').get('passed') is not True or load('prompt.json').get('instruction_sha256') != task.c['instruction']['sha256']: return False
        if load('patch.json').get('baseline_digest') != digest(load('baseline.json')): return False
        receipts = agent.get('requests', [])
        if not receipts or len(receipts) != agent.get('responses'): return False
        seen = set()
        for receipt in receipts:
            if not verify_ref(receipt['request']) or not verify_ref(receipt['response']): return False
            req = json.loads(Path(receipt['request']['path']).read_text())
            res = json.loads(Path(receipt['response']['path']).read_text())
            if req.get('model') != protocol['model'] or req.get('reasoning') != {'effort': protocol['reasoning']} or req.get('max_output_tokens') != protocol['max_output_tokens'] or req.get('transport_attempts') != 1: return False
            if res.get('model') != protocol['model'] or res.get('id') != receipt.get('response_id') or res.get('id') in seen or res.get('status') not in ('completed', 'incomplete') or res.get('error'): return False
            seen.add(res['id'])
        for delivery in agent.get('images_delivered', []):
            if not all(verify_ref(delivery[k]) for k in ('image', 'request', 'response')): return False
            if not any(delivery['request'] == r['request'] and delivery['response'] == r['response'] and delivery['response_id'] == r['response_id'] for r in receipts): return False
            req = json.loads(Path(delivery['request']['path']).read_text())
            images = [c.get('image_url', '') for i in req['input'] for c in i.get('content', []) if c.get('type') == 'input_image']
            if not any(url.startswith('data:image/png;base64,') and hashlib.sha256(base64.b64decode(url.split(',', 1)[1], validate=True)).hexdigest() == delivery['image']['sha256'] for url in images): return False
        if attempt.get('condition') == 'code-only' and (agent.get('images_delivered') or any(t.get('name') == 'browser' for t in req.get('tools', []))): return False
        return True
    except (OSError, KeyError, ValueError, TypeError, Fault):
        return False


def aggregate(attempts, review):
    """All same-revision history (development included), not a selectable six-result subset."""
    reasons = []
    def reject(text):
        if text not in reasons: reasons.append(text)
    if not attempts: reject('missing_attempts')
    identities = {digest(a.get('identity', {})) for a in attempts}
    if len(identities) != 1: reject('mixed_revisions_protocols_or_runtimes')
    ids, sessions = [a.get('attempt_id') for a in attempts], [a.get('session_id') for a in attempts]
    if None in ids or len(set(ids)) != len(ids) or None in sessions or len(set(sessions)) != len(sessions): reject('duplicate_attempt_or_session')
    if not all(validate_evidence(a) if a.get('classification', {}).get('scorable') else
               bool(a.get('artifacts')) and all(verify_ref(r) for r in a['artifacts']) for a in attempts): reject('missing_or_changed_evidence')
    if any(a.get('synthetic') is not False for a in attempts): reject('synthetic_not_admission')
    if any(a.get('purpose', 'candidate') != 'candidate' for a in attempts):
        reject('usability_control_not_admission')
    if any(a.get('protocol') != Protocol().record() or
           (a.get('classification', {}).get('scorable') and set(a.get('agent', {}).get('returned_models', [])) != {Protocol().model})
           for a in attempts): reject('wrong_protocol_or_model')
    for a in attempts:
        recomputed = classify(a.get('agent', {}), a.get('grade'), a.get('health', {}), a.get('classification', {}).get('faults', []))
        for key in ('execution_valid', 'software_correct', 'cua_used', 'success_without_cua', 'scorable', 'classification'):
            if recomputed.get(key) != a.get('classification', {}).get(key): reject('inconsistent_classification')
    # A single healthy nonvisual solve in ANY phase/condition disqualifies dependence.
    if any(a.get('classification', {}).get('success_without_cua') for a in attempts): reject('success_without_visual_observation')
    if any(a.get('classification', {}).get('classification') == 'scope_violation' for a in attempts): reject('scope_violation_not_difficulty')
    slots = {}
    for a in attempts:
        key = (a.get('phase'), a.get('condition'), a.get('slot'))
        slots.setdefault(key, []).append(a)
        if key[0] == 'development' and key[2] != 1: reject('extra_development_trials')
        if key[0] not in ('development', 'confirmation') or key[1] not in ('code-only', 'cua') or key[2] not in (1, 2, 3): reject('invalid_trial_slot')
    selected = []
    for key, rows in slots.items():
        valid = [a for a in rows if a.get('classification', {}).get('scorable') is True]
        if len(valid) != 1: reject('invalid_or_duplicate_trials')
        if len(rows) > 3: reject('too_many_infrastructure_replacements')
        for i, a in enumerate(rows):
            if i and rows[i-1].get('classification', {}).get('scorable'): reject('valid_trial_retried')
            if not a.get('classification', {}).get('scorable'):
                r = a.get('replacement_review') or review.get('replacements', {}).get(a.get('attempt_id'))
                if not r or not verify_ref(r): reject('undiagnosed_invalid_trial')
                else:
                    rr = json.loads(Path(r['path']).read_text())
                    if rr.get('attempt_id') != a.get('attempt_id') or rr.get('repaired') is not True or not rr.get('diagnosis') or not rr.get('compatibility_decision'):
                        reject('invalid_replacement_review')
        if key[0] == 'confirmation': selected.extend(valid)
    for condition in ('code-only', 'cua'):
        if {(a['slot']) for a in selected if a['condition'] == condition} != {1, 2, 3} or len([a for a in selected if a['condition'] == condition]) != 3:
            reject('need_three_valid_trials_per_condition')
    if not all(('development', c, 1) in slots for c in ('code-only', 'cua')): reject('missing_development_pair')
    codes = [a for a in selected if a['condition'] == 'code-only']
    cuas = [a for a in selected if a['condition'] == 'cua']
    code_successes = sum(a['classification']['software_correct'] is True for a in codes)
    cua_successes = sum(a['classification']['software_correct'] is True for a in cuas)
    if code_successes: reject('code_only_success')
    gates = {'deterministic_controls', 'provenance', 'custody', 'source_context_complete', 'pixel_only_isolation',
             'harness_controls', 'independent_classification_review', 'complete_revision_history', 'task_soundness',
             'diagnostic_evidence_accessible', 'gold_stability', 'verifier_fairness', 'budget_opportunity', 'instruction_complete'}
    if not review or review.get('identity') != (attempts[0].get('identity') if attempts else None) or not gates <= set(review.get('gates', {})) or any(review['gates'].get(k) is not True for k in gates): reject('missing_review_gates')
    if not review.get('evidence') or not all(verify_ref(r) for r in review.get('evidence', [])): reject('missing_review_primary_evidence')
    by_id = review.get('attempts', {})
    for a in attempts:
        if not a.get('classification', {}).get('scorable'): continue
        r = by_id.get(a['attempt_id'], {})
        if r.get('result') != a.get('_ref') or not verify_ref(r.get('result', {})) or r.get('classification_validated') is not True or r.get('scope_clean') is not True or not r.get('evidence') or not all(verify_ref(x) for x in r.get('evidence', [])):
            reject('missing_independent_attempt_review')
        if a['classification']['software_correct'] and a['classification']['cua_used'] and r.get('grounded_cua_repair') is not True:
            reject('ungrounded_cua_success')
    return {'admitted': not reasons, 'reasons': reasons, 'code_only_successes': code_successes,
            'cua_successes': cua_successes, 'cua_band': f'{cua_successes}/3' if len(cuas) == 3 else None,
            'role': ('upper_anchor' if cua_successes == 0 else 'lower_anchor') if not reasons else None,
            'success_without_cua_attempts': [a['attempt_id'] for a in attempts if a.get('classification', {}).get('success_without_cua')],
            'all_attempts': [a.get('_ref') for a in attempts]}
