"""Reconstruct publication inputs; keep historical provenance and approvals intact."""
from copy import deepcopy
from pathlib import Path
import json
import yaml

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT/'build/issue252'
RUN = WORK/'run'
BASE = WORK/'public/publication/issue214'


def write(path, data):
    path.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8')


def main():
    cfg = yaml.safe_load((BASE/'profiles/publication.yaml').read_bytes())
    generation = yaml.safe_load((RUN/'generation.yaml').read_bytes())
    cfg['source'] = generation['source']
    cfg['output'] = generation['output']
    cfg['paths'] = deepcopy(generation['paths'])
    cfg['paths']['style'] = str(RUN/'historical-style')
    cfg['paths']['translation_profile'] = str(RUN/'generation.yaml')
    cfg['paths']['consistency_review_config'] = str(RUN/'contract-review.yaml')
    cfg['products'] = generation['products']
    cfg['products']['file'] = str(RUN/'config/products.yaml')
    cfg['site'].update(enabled=False,intro=str(RUN/'site-intro.md'),english_catalog=str(RUN/'english.json'),
                        mermaid_dir=str(WORK/'public/docs/assets/mermaid'),translation_batch_size=8,
                        manuscript_profiles={
                            'official-cam-validation.md':str(RUN/'reader-authentication.yaml'),
                            'vendor-overview.md':str(RUN/'vendor-authentication.yaml'),
                            'request-lifecycle.md':str(RUN/'request-authentication.yaml'),
                        })
    cfg['visuals'] = generation['visuals']
    cfg['publication'] = dict(operation_id='issue252-request-depth')
    write(RUN/'request-authentication.yaml',dict(agent=generation['agent'],paths=dict(style=generation['paths']['style'])))
    write(RUN/'publication.yaml',cfg)
    review = deepcopy(cfg)
    review['agent'] = deepcopy(generation['agent'])
    review['agent']['max_input_chars'] = 180000
    write(RUN/'contract-review.yaml',review)
    vendor = yaml.safe_load((RUN/'vendor-authentication.yaml').read_bytes())
    vendor['paths']['style'] = str(RUN/'historical-style')
    write(RUN/'vendor-authentication.yaml',vendor)
    # The newest catalog includes already published UI changes after issue214.
    catalog = WORK/'public/publication/diagram-pan/english.json'
    if (RUN/'english.json').exists():
        raise ValueError('Keep existing translation work; do not reset its catalog.')
    (RUN/'english.json').write_bytes(catalog.read_bytes())
    print('Publication and independent contract profiles prepared; original approvals preserved.',flush=True)


if __name__=='__main__':
    main()
