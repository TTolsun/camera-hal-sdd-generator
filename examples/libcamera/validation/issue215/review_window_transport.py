"""Share exact ancestry paths in native review input without dropping source text."""
from copy import deepcopy
import hashlib
import json

from sdd.review_context import INSTRUCTIONS as SHARED_INSTRUCTIONS, prepare
from sdd.visual_audit import WINDOW_BINDING, digest


INSTRUCTIONS = (
    'A source window with window_binding retains the exact text in text and '
    'its verification metadata in window_binding. An ancestry object stores paths '
    'as [parent_index, element] rows; null denotes the beginning of a path. '
    'In contexts, path is an index into paths. Reconstruct an ancestry path '
    'from its root to the indexed element. Use the supplied visible text, '
    'source, and presentation for the same independent review.\n'
)
CHECKED_PRESENTATION = (
    'The reviewer has already checked the original HTML paths for hidden content and unsupported presentation. '
    'The complete paths are archived with their counts and hashes below. Evaluate the supplied bilingual '
    'content, source text, figure definitions, placement and scope. Do not infer rendered browser behavior from a hash.\n'
)


def _encode(contexts):
    identities, paths, records = {}, [], {}
    for name, context in contexts.items():
        parent = None
        for element in context['path']:
            key = (parent, json.dumps(element, ensure_ascii=False, sort_keys=True))
            if key not in identities:
                identities[key] = len(paths)
                paths.append([parent, element])
            parent = identities[key]
        records[name] = {**context, 'path': parent}
    restored = []
    for parent, element in paths:
        restored.append([element] if parent is None else [*restored[parent], element])
    decoded = {name: {**row, 'path': [] if row['path'] is None else restored[row['path']]}
               for name, row in records.items()}
    if decoded != contexts:
        raise ValueError('Review ancestry did not round-trip exactly')
    return dict(paths=paths, contexts=records)


def structured_payload(payload, *, checked_presentation=False):
    def pack_paths(owner):
        contexts = owner.pop('presentation_contexts')
        if checked_presentation:
            owner['checked_presentation'] = dict(contexts=len(contexts),sha256=digest(contexts))
        else:
            owner['presentation_ancestry'] = _encode(contexts)

    result = deepcopy(payload)
    for item in result['items']:
        if 'presentation_contexts' in item:
            pack_paths(item)
    for window in result['source_windows'].values():
        text, marker, suffix = window['text'].rpartition(WINDOW_BINDING)
        if not marker:
            continue
        try:
            binding = json.loads(suffix)
        except json.JSONDecodeError:
            continue  # Source text can contain the literal delimiter.
        if not isinstance(binding, dict) or 'presentation_contexts' not in binding:
            continue
        if json.dumps(binding, ensure_ascii=False, sort_keys=True) != suffix:
            raise ValueError('Review window binding serialization changed')
        if checked_presentation:
            pack_paths(binding)
        else:
            binding['ancestry'] = _encode(binding.pop('presentation_contexts'))
        window.update(text=text, window_binding=binding)
    return result


def prepare_review(payload, *, structured=False, compact_json=False, checked_presentation=False):
    if not structured:
        return prepare(payload)
    context = structured_payload(payload,checked_presentation=checked_presentation)
    user, package, proof = prepare(context)
    format_name = 'structured-source-windows-v1'
    if compact_json:
        encoded = json.dumps(package if package is not None else context,ensure_ascii=False,separators=(',',':'))
        prefix = SHARED_INSTRUCTIONS if package is not None else ''
        user = prefix+encoded
        if package is not None:
            proof['encoded_sha256'] = hashlib.sha256(encoded.encode()).hexdigest()
        format_name = 'structured-source-windows-compact-json-v1'
    if package is None:
        package = context
    prefix = INSTRUCTIONS
    if checked_presentation:
        if not compact_json:
            raise ValueError('Checked presentation input requires compact JSON')
        prefix = CHECKED_PRESENTATION
        format_name = 'checked-presentation-source-windows-v1'
        proof['complete_input_round_trip'] = False
    proof.update(format=format_name, complete_input_sha256=digest(payload),
                 native_chars=len(prefix)+len(user))
    return prefix+user, package, proof
