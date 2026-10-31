"""Keep historical contract review identity separate from new Terra reviews."""
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[4]
work = root/'build/issue211-publication'
config = yaml.safe_load((work/'generation.yaml').read_text(encoding='utf-8'))
config['site']['enabled'] = True
# Preserve the original visual identity for model-free verification only.
config['agent'] = yaml.safe_load((root/'build/libcamera-sdd-issue211/publication/issue193/profiles/publication.yaml').read_text(encoding='utf-8'))['agent']
historical = dict(config)
historical['agent'] = yaml.safe_load((root/'build/libcamera-sdd-issue211/publication/issue193/profiles/independent-review.yaml').read_text(encoding='utf-8'))['agent']
historical['paths'] = dict(config['paths'])
historical['paths'].pop('consistency_review_config', None)
(work/'historical-contract-review.yaml').write_text(yaml.safe_dump(historical, allow_unicode=True, sort_keys=False), encoding='utf-8')
config['paths']['consistency_review_config'] = str(work/'historical-contract-review.yaml')
(work/'publication.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
# New source and bilingual reviews use this separate native Terra identity. The
# previous report is authenticated only under its actual historical Haiku args.
review = yaml.safe_load(Path(__file__).with_name('independent-review-profile.yaml').read_text(encoding='utf-8'))
(work/'new-document-review.yaml').write_text(yaml.safe_dump(review, allow_unicode=True, sort_keys=False), encoding='utf-8')
