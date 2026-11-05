"""Fail on real rendered inputs before translating or replacing a catalog."""
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from sdd.localization_cli import prepare_catalog
from test_export_site import prepare


@pytest.mark.parametrize('failure', ['missing', 'default', 'stale', 'anchor', 'asset'])
def test_invalid_source_fails_before_translation_and_preserves_outputs(tmp_cfg, sample_model, monkeypatch, failure):
    prepare(tmp_cfg, sample_model)
    sections = yaml.safe_load(tmp_cfg.sections_file.read_text(encoding='utf-8'))
    section = sections['sections'][0]
    footer = '다음 단계: [Details](nested/detail.md)'
    if failure == 'missing':
        section['next'] = dict(title='Missing', link='absent.md')
        footer = '다음 단계: [Missing](absent.md)'
    elif failure == 'default':
        section.pop('next')
        footer = '다음 단계: [시스템 개요](overview.md)'
    elif failure == 'stale':
        target = tmp_cfg.sdd_dir/'nested/detail.md'
        target.write_text(target.read_text(encoding='utf-8').replace('a'*40, 'b'*40), encoding='utf-8')
    tmp_cfg.sections_file.write_text(yaml.safe_dump(sections, allow_unicode=True), encoding='utf-8')
    path = tmp_cfg.sdd_dir/'device.md'
    text = path.read_text(encoding='utf-8').replace('---\n\n', 'section: device\n---\n\n', 1)
    if failure == 'anchor':
        text += '\n[Details](nested/detail.md#absent-anchor)\n'
    if failure == 'asset':
        text += '\n![Figure](absent.svg)\n'
    path.write_text(text+'\n'+footer+'\n', encoding='utf-8')
    destination = tmp_cfg.root/'english.json'
    original = b'{"review_status":"human-review-pending","strings":{"old":"retained"}}'
    destination.write_bytes(original)
    before = {p: p.read_bytes() for p in tmp_cfg.sdd_dir.rglob('*') if p.is_file()}
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid source reached a translation call')
    monkeypatch.setattr('sdd.translation.translate_missing', unexpected)
    with pytest.raises((ValueError, RuntimeError), match='missing|mismatch|Missing'):
        prepare_catalog(tmp_cfg, destination, translate=True)
    assert destination.read_bytes() == original
    assert all(p.read_bytes() == raw for p, raw in before.items())
    runs = [json.loads(p.read_bytes()) for p in (tmp_cfg.build_dir/'generation-runs').glob('*.json')]
    assert runs and all(not r['calls'] for r in runs)
    failed = [p for r in runs for p in r['phases'] if p['name']=='translation-preflight']
    assert len(failed)==1 and failed[0]['status']=='failed'


def test_module_cli_checks_the_sample_instead_of_exiting_without_work(tmp_cfg, sample_model):
    prepare(tmp_cfg, sample_model)
    path = tmp_cfg.sdd_dir/'device.md'
    path.write_text(path.read_text(encoding='utf-8')+'\n[Missing](absent.md)\n', encoding='utf-8')
    target = tmp_cfg.root/'english.json'
    target.write_bytes(b'{"strings":{}}')
    result = subprocess.run([sys.executable, '-m', 'sdd.localization_cli', '--config',
                             str(tmp_cfg.root/'sdd.yaml'), '--out', str(target), '--translate'],
                            capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0 and 'Missing local target' in result.stderr
    assert target.read_bytes() == b'{"strings":{}}'
