"""Keep untouched public pages searchable in an explicitly partial preview."""
import json
from urllib.parse import unquote, urlsplit


def merge_search(public, stage, selected_pages):
    replaced = {name.removesuffix('.md')+'.html' for name in selected_pages}
    for prefix in ('', 'en/'):
        relative = prefix+'assets/search.json'
        original = json.loads((public/relative).read_bytes())
        generated = json.loads((stage/relative).read_bytes())
        retained = [entry for entry in original
                    if unquote(urlsplit(entry['url']).path) not in replaced]
        (stage/relative).write_text(json.dumps(retained+generated, ensure_ascii=False),
                                   encoding='utf-8', newline='\n')
