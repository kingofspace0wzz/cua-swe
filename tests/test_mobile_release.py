"""Portable release checks use original source and controls, without model calls."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest
from cua_swe_bench.mobile_evaluation.release import REPO, RELEASE, MANIFEST, load, materialize, validate_release
from cua_swe_bench.mobile_evaluation.core import Task, digest, tree
from cua_swe_bench.mobile_evaluation.workspace import prepare, apply


def test_release_pins_all_twenty_inputs_and_four_hundred_cells():
    result = validate_release()
    assert result == {'valid': True, 'task_count': 20, 'frozen_files': 547,
                      'executed': 340, 'scorable': 296, 'successes': 71,
                      'behavioral_failures': 225, 'excluded': 44, 'user_deferred': 60}


@pytest.mark.parametrize('row', load(REPO / MANIFEST)['tasks'], ids=lambda r: r['task_id'])
def test_relocation_preserves_every_control_change_and_baseline(row, tmp_path, monkeypatch):
    from cua_swe_bench.mobile_evaluation import core
    monkeypatch.setattr(core, 'ROOT', tmp_path.resolve())
    spec = materialize(row, tmp_path / 'inputs')
    task = Task.load(spec)
    source = tmp_path / 'source'
    # Browser identity is exercised by Linux controls; ordinary source verification remains real here.
    monkeypatch.setattr(Task, 'validate_inputs', lambda self: None)
    baseline = prepare(task, source)
    original = load(REPO / row['task_file'])
    for name, control in task.c['controls'].items():
        patch = load(control['patch']['path'])
        frozen = load(REPO / Path(row['task_file']).parent / original['controls'][name]['patch']['path'])
        assert {**patch, 'task_digest': frozen['task_digest']} == frozen
        assert patch['task_digest'] == task.id
        assert patch['baseline_digest'] == digest(baseline)
        dst = tmp_path / name
        prepare(task, dst)
        apply(task, baseline, patch, dst)
        assert all(n in task.c['public_files'] for n in tree(dst) if n != 'TASK.md')


def test_changed_task_input_fails_before_dispatch(tmp_path):
    shutil.copytree(REPO / 'dataset/mobile', tmp_path / 'dataset/mobile')
    row = load(tmp_path / MANIFEST)['tasks'][0]
    spec = load(tmp_path / row['task_file'])
    first = next(iter(spec['public_files'].values()))
    file = tmp_path / Path(row['task_file']).parent / first['path']
    file.write_bytes(file.read_bytes() + b'\n// altered\n')
    with pytest.raises(ValueError, match='frozen task input changed'):
        validate_release(tmp_path)


def test_control_with_wrong_revision_cannot_be_rebound(tmp_path):
    row = deepcopy(load(REPO / MANIFEST)['tasks'][0])
    row['evaluated_task_digest'] = '0' * 64
    with pytest.raises(ValueError, match='control is not bound'):
        materialize(row, tmp_path / 'inputs')
