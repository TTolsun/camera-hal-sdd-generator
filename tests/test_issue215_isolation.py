"""Synthetic run directories exercise preservation; no model is executed."""
import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import uuid

import pytest
import yaml

from sdd.config import load
from sdd.facts.model import KnowledgeModel

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT/'examples/libcamera/validation/issue215'


def remove_fixture(home):
    resolved = home.resolve()
    assert resolved.parent == (ROOT/'build').resolve()
    assert resolved.name.startswith('issue215-isolation-fixture-')
    def clear_readonly(function, path, error):
        assert Path(path).resolve().is_relative_to(resolved)
        os.chmod(path,stat.S_IREAD | stat.S_IWRITE)
        function(path)
    shutil.rmtree(resolved,onerror=clear_readonly)


@pytest.fixture
def run_layout():
    home = ROOT/'build'/('issue215-isolation-fixture-'+uuid.uuid4().hex)
    home.mkdir(parents=True)
    source, base = home/'source', home/'base'
    source.mkdir()
    hooks = home/'empty-hooks'
    hooks.mkdir()
    git = ['git','-c','core.hooksPath='+str(hooks),'-c','commit.gpgsign=false']
    for args in [['init','-q'],['config','user.name','Synthetic fixture'],
                 ['config','user.email','fixture@example.invalid']]:
        subprocess.run(git+args,cwd=source,check=True,capture_output=True)
    (source/'driver.cpp').write_text('class Driver {};\nvoid Driver::stop() {}\n',encoding='utf-8')
    subprocess.run(git+['add','driver.cpp'],cwd=source,check=True,capture_output=True)
    subprocess.run(git+['commit','-qm','Synthetic source'],cwd=source,check=True,capture_output=True)
    commit = subprocess.check_output(git+['rev-parse','HEAD'],cwd=source,text=True).strip()
    for name in ['config','templates','run/manuscripts','run/facts']:
        (base/name).mkdir(parents=True,exist_ok=True)
    (base/'config/sections.yaml').write_text(yaml.safe_dump(dict(sections=[dict(
        id='driver',title='Synthetic driver',kind='prose',output='driver.md',show_evidence=True,
        design_topics=[dict(id='lifecycle',title='Lifecycle',question='What does the source declare?',
            sources=[dict(id='decl',file='driver.cpp',start='class Driver',end='{};')])])])),encoding='utf-8')
    (base/'config/scenarios.yaml').write_text('scenarios: []\n',encoding='utf-8')
    (base/'config/visuals.yaml').write_text('sections: {}\n',encoding='utf-8')
    (base/'run/manuscripts/driver.md').write_text('# Synthetic fixture\n',encoding='utf-8')
    KnowledgeModel(meta=dict(source_commit=commit)).save(base/'run/facts/facts.json')
    config = dict(source=dict(root=str(source)),
        output=dict(facts_dir=str(base/'run/facts'),sdd_dir=str(base/'run/manuscripts'),
                    diagrams_dir=str(base/'run/manuscripts/diagrams')),
        paths=dict(sections_file=str(base/'config/sections.yaml')),
        publication=dict(operation_id='synthetic-fixture'),visuals=dict(file='config/visuals.yaml'))
    (base/'generation.yaml').write_text(yaml.safe_dump(config),encoding='utf-8')
    plans = home/'plans.yaml'
    plans.write_text('driver: []\n',encoding='utf-8')
    additions = home/'additions.yaml'
    additions.write_text(yaml.safe_dump(dict(driver=dict(lifecycle=dict(sources=[dict(
        id='stop',file='driver.cpp',start='void Driver::stop()',end='{}')])))),encoding='utf-8')
    try:
        yield home,source,base,plans,additions
    finally:
        remove_fixture(home)


def run(tool, args):
    env = dict(os.environ,PYTHONPATH=str(ROOT/'src'),PYTHONIOENCODING='utf-8')
    return subprocess.run([sys.executable,str(TOOLS/tool),*map(str,args)],cwd=ROOT,env=env,
                          capture_output=True,text=True,encoding='utf-8')


def test_absolute_base_outputs_are_rebased_without_changing_previous_facts(run_layout):
    home,source,base,plans,additions = run_layout
    original = (base/'run/facts/facts.json').read_bytes()
    work = home/'work'
    result = run('prepare_followup.py',['--base',base,'--work',work,'--plans',plans,
                                       '--source-additions',additions])
    assert result.returncode == 0, result.stderr
    cfg = load(work/'generation.yaml')
    assert cfg.facts_path.resolve() == work/'run/facts/facts.json'
    assert cfg.sdd_dir.resolve() == work/'run/manuscripts'
    assert cfg.sections_file.resolve() == work/'config/sections.yaml'
    assert (base/'run/facts/facts.json').read_bytes() == original
    assert KnowledgeModel.load(cfg.facts_path).evidence['driver/lifecycle/stop']['status'] == 'available'


@pytest.mark.parametrize('tool',['prepare_followup.py','incremental_generate.py'])
def test_nested_work_is_rejected_before_mutating_the_previous_run(run_layout, tool):
    _,_,base,plans,_ = run_layout
    before = {p.relative_to(base):hashlib.sha256(p.read_bytes()).hexdigest() for p in base.rglob('*') if p.is_file()}
    nested = base/'run/manuscripts/new-output'
    result = run(tool,['--base',base,'--work',nested,'--plans',plans])
    assert result.returncode != 0
    assert not nested.exists()
    assert before == {p.relative_to(base):hashlib.sha256(p.read_bytes()).hexdigest() for p in base.rglob('*') if p.is_file()}


@pytest.mark.parametrize('tool',['prepare_followup.py','incremental_generate.py'])
def test_work_inside_source_is_rejected_before_creating_files(run_layout, tool):
    _,source,base,plans,_ = run_layout
    before = sorted(p.relative_to(source).as_posix() for p in source.rglob('*'))
    nested = source/'new-output'
    result = run(tool,['--base',base,'--work',nested,'--plans',plans])
    assert result.returncode != 0 and not nested.exists()
    assert before == sorted(p.relative_to(source).as_posix() for p in source.rglob('*'))


@pytest.mark.parametrize('input_name',['site','source'])
def test_review_output_cannot_mutate_inputs_before_validation(run_layout, input_name):
    home,source,base,_,_ = run_layout
    target = source if input_name == 'source' else base
    nested = target/'new-review'
    result = run('review_inventory.py',['--inventory',home/'missing.json',
        '--site',base,'--source',source,'--profile',home/'missing.yaml',
        '--page','driver.html','--out',nested])
    assert result.returncode != 0 and not nested.exists()
    assert 'must not overlap' in result.stderr


def test_review_rejects_modified_structural_facts_before_loading_inputs(run_layout):
    home,source,base,_,_ = run_layout
    facts = base/'run/facts/facts.json'
    expected = hashlib.sha256(facts.read_bytes()).hexdigest()
    facts.write_bytes(facts.read_bytes()+b' ')
    out = home/'review'
    result = run('review_inventory.py',['--inventory',home/'missing.json',
        '--site',base,'--source',source,'--profile',home/'missing.yaml',
        '--page','driver.html','--out',out,'--facts',facts,'--facts-sha256',expected])
    assert result.returncode != 0 and not out.exists()
    assert 'independently pinned provenance digest' in result.stderr


def test_untracked_source_cannot_be_attributed_to_the_pinned_commit(run_layout):
    home,source,base,plans,additions = run_layout
    (source/'untracked.cpp').write_text('void invented() {}\n',encoding='utf-8')
    original = (base/'run/facts/facts.json').read_bytes()
    result = run('prepare_followup.py',['--base',base,'--work',home/'work',
        '--plans',plans,'--source-additions',additions])
    assert result.returncode != 0
    assert 'unchanged source checkout' in result.stderr
    assert (base/'run/facts/facts.json').read_bytes() == original


def test_dangling_preview_plan_cannot_write_into_public_inputs(run_layout):
    home,_,_,_,_ = run_layout
    work,public,out = home/'work',home/'public',home/'preview'
    work.mkdir()
    (public/'docs').mkdir(parents=True)
    target = public/'docs/new-file.json'
    try:
        (work/'preview-translation-plan.json').symlink_to(target)
    except OSError:
        pytest.skip('Symlink creation is unavailable on this runner')
    result = run('preview_pipeline.py',['--work',work,'--public',public,'--out',out])
    assert result.returncode != 0
    assert not target.exists() and not out.exists()
    assert 'Preserve the previous catalog/plan' in result.stderr


def test_raw_line_anchor_evidence_reaches_native_plan_without_html_parsing(run_layout,monkeypatch):
    import importlib.util
    import json
    from sdd.visual_audit import inspect_site,policy
    home,_,_,_,_=run_layout
    site=home/'site';(site/'en').mkdir(parents=True)
    for prefix,lang in (('','ko'),('en/','en')):
        (site/(prefix+'source.cpp')).write_text('void stop() {}\n',encoding='utf-8')
        (site/(prefix+'guide.html')).write_text(
            '<html lang="'+lang+'"><article><h2 id="question">Stop</h2>'
            '<p>One condition. <a class="citation" href="source.cpp#L1">source</a></p></article></html>',encoding='utf-8')
    report=inspect_site(site,policy(),source_commit='a'*40)
    inventory=home/'inventory.json';inventory.write_text(json.dumps(report),encoding='utf-8')
    out=home/'review'
    monkeypatch.syspath_prepend(str(TOOLS))
    spec=importlib.util.spec_from_file_location('synthetic_issue215_review',TOOLS/'review_inventory.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    # This plan-only fixture never locates or runs a CLI. CI need not install
    # Codex; an accidental model-execution path must fail this synthetic test.
    monkeypatch.setattr(helper,'command',lambda config:['synthetic-plan-only-not-executed'])
    def no_model(*args,**kwargs):
        raise AssertionError('A plan-only fixture must not create a model execution')
    monkeypatch.setattr(helper,'Agent',no_model)
    monkeypatch.setattr(helper,'Execution',no_model)
    monkeypatch.setattr(sys,'argv',['review_inventory.py','--inventory',str(inventory),'--site',str(site),
        '--profile',str(TOOLS/'independent-review-profile.yaml'),'--page','guide.html','--out',str(out),'--plan-only'])
    helper.main()
    payload=json.loads((out/'inputs.json').read_bytes())
    assert payload['source_windows']['source.cpp#L1']['text']=='void stop() {}\n'
    assert json.loads((out/'input-plan.json').read_bytes())['native_call'] is False
