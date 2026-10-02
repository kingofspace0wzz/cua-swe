"""Auditable opt-in paid dispatch guard. Not exercised by construction preflight/tests."""
import contextlib
import fcntl
import json
from pathlib import Path
from .core import CLIENT_SHA, Fault, Protocol, digest, harness_identity, output_path, verify_ref, write_json
from .admission import ledger_attempts


def load_ref_file(path):
    ref = json.loads(Path(path).read_text())
    if not verify_ref(ref): raise Fault('configuration', 'approval reference missing/changed')
    return ref, json.loads(Path(ref['path']).read_text())


def validate_phase(task, phase, slot):
    purpose = task.c.get('purpose', 'candidate')
    if purpose not in ('candidate', 'usability-control'):
        raise Fault('configuration', 'unknown task purpose')
    if phase not in ('usability', 'development', 'confirmation', 'evaluation') or slot not in (1, 2, 3):
        raise Fault('configuration', 'unknown trial phase/slot')
    if (purpose == 'usability-control') != (phase == 'usability'):
        raise Fault('configuration', 'usability controls cannot enter candidate trial phases')
    if phase in ('usability', 'development', 'evaluation') and slot != 1:
        raise Fault('configuration', 'one trial per condition in this phase')


def validate_approval(task, ref, approval):
    expected = {'task_digest': task.id, 'protocol_digest': digest(Protocol().record()), 'harness_digest': digest(harness_identity())}
    if not verify_ref(ref) or any(approval.get(k) != v for k, v in expected.items()) or approval.get('approved') is not True:
        raise Fault('configuration', 'dispatch approval identity mismatch')
    purpose = task.c.get('purpose', 'candidate')
    if purpose not in ('candidate', 'usability-control') or approval.get('purpose', 'candidate') != purpose:
        raise Fault('configuration', 'dispatch approval purpose mismatch')
    for field in ('route_control', 'harness_control', 'native_control'):
        r = approval.get(field, {})
        if not verify_ref(r): raise Fault('configuration', f'missing {field}')
        c = json.loads(Path(r['path']).read_text())
        if c.get('passed') is not True and c.get('phase') != 'passed': raise Fault('configuration', f'unhealthy {field}')
        if field == 'route_control':
            if any(c.get(k) != v for k, v in {'model': Protocol().model, 'provider': Protocol().provider, 'client_sha256': CLIENT_SHA}.items()):
                raise Fault('provider', 'route control identity mismatch')
        elif field == 'native_control':
            certification = 'native_fixture_certified' if purpose == 'usability-control' else 'native_mobile_certified'
            if (c.get(certification) is not True or
                    c.get('purpose', 'candidate') != purpose or
                    any(c.get(k) != v for k,v in expected.items())):
                raise Fault('configuration', 'native certification absent/incompatible')
        elif c.get('harness_digest') != expected['harness_digest'] or c.get('provider_called') is not False:
            raise Fault('configuration', 'harness preflight absent/incompatible')
    return expected


@contextlib.contextmanager
def dispatch_lock(ledger, task, phase, condition, slot, replacement_ref_path=None):
    # One controller at a time per revision ledger; held THROUGH result append, preventing concurrent retries.
    validate_phase(task, phase, slot)
    lock = output_path(str(ledger) + '.dispatch.lock'); lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        history = ledger_attempts(ledger) if Path(ledger).exists() else []
        if any(a['identity']['task_digest'] != task.id for a in history): raise Fault('configuration', 'ledger must contain exactly one revision')
        same = [a for a in history if a['phase'] == phase and a['condition'] == condition and a['slot'] == slot]
        if any(a['classification']['scorable'] or a['classification']['classification'] == 'scope_violation' for a in same) or len(same) >= 3:
            raise Fault('configuration', 'valid/scope retries or >2 infrastructure replacements forbidden')
        repair = None
        if same:
            if not replacement_ref_path: raise Fault('configuration', 'infrastructure replacement needs independent diagnosis/repair')
            repair_ref, repair = load_ref_file(replacement_ref_path)
            if repair.get('attempt_id') != same[-1]['attempt_id'] or repair.get('previous_attempt') != same[-1]['_ref'] or repair.get('repaired') is not True or not repair.get('diagnosis') or not repair.get('compatibility_decision'):
                raise Fault('configuration', 'replacement review invalid')
            repair = {'reference': repair_ref, 'record': repair}
        # A controller crash leaves a durable reservation, blocking silent redispatch of an unknown trial.
        reservation = Path(str(ledger) + f'.{phase}.{condition}.{slot}.{len(same)}.reserved.json')
        try:
            write_json(reservation, {'task_digest': task.id, 'phase': phase, 'condition': condition, 'slot': slot, 'replacement_index': len(same)})
        except FileExistsError as exc:
            raise Fault('configuration', 'unfinished dispatch reservation requires explicit diagnosis and invalid-attempt ledger entry') from exc
        yield repair
