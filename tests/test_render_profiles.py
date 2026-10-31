import pytest
import yaml
from sdd.render_profiles import for_page,inputs


def test_explicit_profile_cannot_replace_source_or_validation_contracts(tmp_cfg):
    path=tmp_cfg.root/'profile.yaml'
    path.write_text(yaml.safe_dump(dict(agent=dict(kind='cli',runner='claude',model='test-model'),
                                        paths=dict(style=str(tmp_cfg.style_dir)))),encoding='utf-8')
    tmp_cfg.raw['site']={'manuscript_profiles':{'trial.md':'profile.yaml'}}
    selected=for_page(tmp_cfg,'trial.md')
    assert selected.agent.runner=='claude'
    assert selected.source_root==tmp_cfg.source_root and selected.facts_path==tmp_cfg.facts_path
    assert selected.sdd_dir==tmp_cfg.sdd_dir and selected.sections_file==tmp_cfg.sections_file
    assert for_page(tmp_cfg,'unchanged.md') is tmp_cfg
    before=inputs(tmp_cfg)
    style=tmp_cfg.style_dir/'README.md'
    style.write_text(style.read_text(encoding='utf-8')+'\nNew editorial policy\n',encoding='utf-8')
    assert inputs(tmp_cfg)['style/trial.md/README.md']!=before['style/trial.md/README.md']
    path.write_text(path.read_text()+'source: {root: other}\n',encoding='utf-8')
    with pytest.raises(ValueError,match='changes only'):for_page(tmp_cfg,'trial.md')
    assert before['profile/trial.md']


def test_null_site_keeps_default_profile(tmp_cfg):
    tmp_cfg.raw['site']=None
    assert for_page(tmp_cfg,'trial.md') is tmp_cfg


@pytest.mark.parametrize('page',['../trial.md','/trial.md','C:\\trial.md','trial.html'])
def test_profile_paths_fail_closed(tmp_cfg,page):
    tmp_cfg.raw['site']={'manuscript_profiles':{page:'profile.yaml'}}
    with pytest.raises(ValueError,match='Invalid'):for_page(tmp_cfg,page)
