"""Reassemble configured figures without claiming new prose inference.

The caller supplies an independently pinned original manuscript digest. This
returns a derived manuscript and never writes a file or calls an agent. Original
prose, source bindings, native graph records and approval metadata stay intact;
the ordinary item/publication gates still apply to the derived document.
Body bytes outside owned edit regions are preserved literally. Frontmatter is
serialized again: its values are preserved except for derived body hashes and
the appended lineage event; comments and YAML formatting are not preserved.
The original artifact and its pinned digest remain the historical byte record.
"""
from __future__ import annotations

import copy
from bisect import bisect_right
import hashlib
import json
import re

import yaml

from .config import section_output
from .document_metadata import split_frontmatter
from .generated_design import enabled, verify as verify_design
from .generated_visuals import from_manuscript, plans, render, resolve
from .render_profiles import for_page
from .validation_stage import staged
from .visuals import place, placement_stage, owned_spans as _owned_spans, verify_stage_placement


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _body_digest(value):
    return _digest(value.strip().encode('utf-8'))


def _json_digest(value):
    return _digest(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8'))


def _normalized(raw):
    # Only CRLF changes character offsets; a lone CR becomes one LF.
    crlf_ends = [match.end() - index - 1 for index, match in enumerate(re.finditer('\r\n', raw))]
    return raw.replace('\r\n', '\n').replace('\r', '\n'), crlf_ends


def _reassemble(body, raw_body, to_raw, rendered, section):
    """Replace owned spans and prove insertions preserve every original byte."""
    spans = _owned_spans(body)
    old_ids = {ident for _, _, ident in spans}
    current = {value[0]['id']: value for value in rendered}
    if old_ids - current.keys():
        raise ValueError('Visual refresh cannot delete an existing owned figure')
    from .next_steps import _outside_fence
    headings = [match for match in re.finditer(r'^## ([^\n]+)\n', body, re.M)
                if _outside_fence(body[:match.start()])]
    topics = {topic['id']: topic for topic in section.get('design_topics', [])}
    for start, _, ident in spans:
        preceding = [match for match in headings if match.start() < start]
        title = topics[current[ident][0]['topic']]['title']
        if not preceding or preceding[-1][1] != title:
            raise ValueError('Moving an existing figure to another topic requires normal generation')
    def placement_key(visual):
        topic = visual['topic']
        return topic, placement_stage(visual, topics[topic])

    by_stage, old_by_stage = {}, {}
    for visual, _, _ in rendered:
        by_stage.setdefault(placement_key(visual), []).append(visual['id'])
    for _, _, ident in spans:
        old_by_stage.setdefault(placement_key(current[ident][0]), []).append(ident)
    groups = {ident: [ident] for ident in old_ids}

    for key, old_order in old_by_stage.items():
        # Production placement orders explicit stages by their H3 positions,
        # independently of definition order. Use an anchor in the same stage
        # when inserting a figure between existing spans.
        configured_order = by_stage[key]
        if [ident for ident in configured_order if ident in old_ids] != old_order:
            raise ValueError('Reordering existing figures requires normal generation')
        pending = []
        for ident in configured_order:
            if ident in old_ids:
                groups[ident] = [*pending, ident]
                pending = []
            else:
                pending.append(ident)
        groups[old_order[-1]].extend(pending)
    eol_match = re.search(r'\r\n|\r|\n', raw_body)
    default_eol = eol_match[0] if eol_match else '\n'
    edits = []
    for start, end, ident in spans:
        first, last = to_raw(start), to_raw(end)
        original = raw_body[first:last]
        ending = re.search(r'\r\n|\r|\n', original)
        block = '\n\n'.join(current[key][1] for key in groups[ident])
        block = block.replace('\n', ending[0] if ending else default_eol)
        edits.append((first, last, block, groups[ident]))

    unanchored = {key: ids for key, ids in by_stage.items() if key not in old_by_stage}
    old_topics = {topic for topic, _ in old_by_stage}
    if any(topic in old_topics for topic, _ in unanchored):
        raise ValueError('Adding a figure to a stage without an existing anchor requires normal generation')
    if unanchored:
        # Use the production placement contract on a probe. Existing figures
        # are opaque anchors, so its legacy strip_blocks cannot eat their
        # surrounding whitespace. The probe must differ by insertions only.
        seed = _digest(body.encode())[:20]
        chunks, masks, cursor, probe_length = [], [], 0, 0
        for index, (start, end, _) in enumerate(spans):
            prefix = body[cursor:start]
            chunks.append(prefix)
            probe_length += len(prefix)
            token = f'<!-- sdd-refresh-anchor:{seed}:{index} -->'
            if token in body:
                raise ValueError('Visual refresh probe conflicts with source text')
            masks.append((probe_length, probe_length + len(token), start, end))
            chunks.append(token)
            probe_length += len(token)
            cursor = end
        chunks.append(body[cursor:])
        probe = ''.join(chunks)
        tokens, fake = {}, []
        for index, ids in enumerate(unanchored.values()):
            token = f'SDD_REFRESH_INSERT_{seed}_{index}'
            if token in body:
                raise ValueError('Visual refresh probe conflicts with source text')
            tokens[token] = ids
            fake.append((current[ids[0]][0], token, 'placement probe'))
        placed = place(probe, fake, section)
        additions = []
        for token, ids in tokens.items():
            needle = '\n\n' + token
            if placed.count(needle) != 1:
                raise ValueError('Cannot prove the new figure placement is insertion-only')
            start = placed.index(needle)
            additions.append((start, start + len(needle), ids))
        additions.sort()
        restored, cursor = [], 0
        for start, end, _ in additions:
            restored.append(placed[cursor:start])
            cursor = end
        restored.append(placed[cursor:])
        if ''.join(restored) != probe:
            raise ValueError('Placement would change text outside the new figure insertion')
        removed = 0
        for start, end, ids in additions:
            position = start - removed
            removed += end - start
            delta = 0
            for first, last, original_first, original_last in masks:
                if position <= first:
                    break
                if position < last:
                    raise ValueError('New figure placement intersects an existing figure')
                delta += (original_last - original_first) - (last - first)
            original_position = position + delta
            block = '\n\n' + '\n\n'.join(current[key][1] for key in ids)
            first = to_raw(original_position)
            edits.append((first, first, block.replace('\n', default_eol), ids))

    pieces, outside, regions, cursor, output_position = [], [], [], 0, 0
    for start, end, block, ids in sorted(edits, key=lambda value: (value[0], value[1])):
        if start < cursor:
            raise ValueError('Visual refresh edit regions overlap')
        untouched = raw_body[cursor:start]
        outside.append(untouched)
        pieces.extend([untouched, block])
        output_position += len(untouched)
        regions.append((output_position, output_position + len(block), dict(
            original_start_byte=len(raw_body[:start].encode()),
            original_end_byte=len(raw_body[:end].encode()),
            original_sha256=_digest(raw_body[start:end].encode()),
            replacement_sha256=_digest(block.encode()), visual_ids=ids)))
        output_position += len(block)
        cursor = end
    pieces.append(raw_body[cursor:])
    outside.append(raw_body[cursor:])
    updated = ''.join(pieces)
    projected, cursor = [], 0
    for start, end, _ in regions:
        projected.append(updated[cursor:start])
        cursor = end
    projected.append(updated[cursor:])
    if ''.join(projected) != ''.join(outside):
        raise ValueError('Visual refresh changed bytes outside owned edit regions')
    verify_stage_placement(updated,rendered,section)
    return updated, old_ids, _digest(''.join(outside).encode()), [row for _, _, row in regions]


@staged
def refresh(cfg, model, section_id, manuscript: bytes, *, expected_sha256: str,
            original_cfg=None, visual_artifact=None) -> bytes:
    """Return current source figures inside an authenticated, unchanged prose page.

    Use a prior publication/native-generation digest, not an unchecked modified
    input. A historical profile is used only for artifact verification; this API
    cannot execute that runner or substitute stored responses for new inference.
    For separately generated native graph records, supply both original_cfg and
    the unassembled visual_artifact returned by generated_visuals.generate().
    The old profile verifies the original only; current records must independently
    resolve under the current page profile. Prose and its authorship stay intact.
    """
    if (not isinstance(manuscript, bytes) or not isinstance(expected_sha256, str)
            or not re.fullmatch(r'[0-9a-f]{64}', expected_sha256 or '')
            or _digest(manuscript) != expected_sha256):
        raise ValueError('Original manuscript does not match its pinned digest')
    sections = [s for s in cfg.sections() if s['id'] == section_id]
    if len(sections) != 1 or not enabled(sections[0]):
        raise ValueError('Visual refresh requires one source-bound generated-prose section')
    section = sections[0]
    selected = for_page(cfg, section_output(section))
    replacing = original_cfg is not None or visual_artifact is not None
    if replacing and (original_cfg is None or visual_artifact is None):
        raise ValueError('Native graph replacement requires original config and new artifact together')
    # Match production read_text's universal newline handling while retaining
    # the original byte identity and returning exact input bytes for a no-op.
    raw_text = manuscript.decode('utf-8')
    text, crlf_ends = _normalized(raw_text)
    metadata, body = split_frontmatter(text)
    commit = model.meta.get('source_commit', '')
    if not re.fullmatch(r'[0-9a-f]{40}', commit) or metadata.get('source_commit') != commit:
        raise ValueError('Facts and original manuscript source commits differ')
    verify_design(model, section, text, cfg=selected)
    if section.get('scenario'):
        from .scenario_sections import verify
        verify(selected, model, section, metadata, body)
    saved = metadata.get('generated_visuals')
    if saved is not None and (not isinstance(saved, dict) or not isinstance(saved.get('records'), dict)):
        raise ValueError('Saved LLM visual records are invalid')
    saved_ids = set((saved or {}).get('records', {}))
    planned_ids = {plan['id'] for plan in plans(selected, section)}
    if saved_ids != planned_ids:
        raise ValueError('Saved LLM visual records must match current plans; refresh cannot remove or convert them')
    if replacing:
        originals = [value for value in original_cfg.sections() if value['id'] == section_id]
        if len(originals) != 1:
            raise ValueError('Original configuration requires the same source-bound section')
        origin = for_page(original_cfg, section_output(originals[0]))
        verify_design(model, originals[0], text, cfg=origin)
        if saved_ids != {plan['id'] for plan in plans(origin, originals[0])}:
            raise ValueError('Original native graph plans must match the original saved records')
        from_manuscript(origin, model, originals[0], text)
        if (not planned_ids or not isinstance(visual_artifact, dict) or set(visual_artifact) != {'schema', 'records'}
                or visual_artifact.get('schema') != 1 or not isinstance(visual_artifact['records'], dict)
                or set(visual_artifact['records']) != planned_ids):
            raise ValueError('Replacement must be a complete unassembled native graph artifact')
        artifact = copy.deepcopy(visual_artifact)
        # Original records have already passed the original profile above and
        # still pass resolve() below. Keep their actual historical provenance;
        # only changed records must come from the current generation profile.
        if any(not isinstance(record, dict) or (_json_digest(record) != _json_digest((saved or {}).get('records', {}).get(ident))
               and (record.get('generation_commit') != commit or record.get('producer') != selected.agent.label))
               for ident, record in artifact['records'].items()):
            raise ValueError('Replacement graph commit or producer differs from current profile')
        resolve(selected, model, section, artifact)
    else:
        artifact = from_manuscript(selected, model, section, text)
    rendered = render(selected, model, section, artifact)
    if any(not source for _, _, source in rendered):
        raise ValueError('A current visual is missing/stale; refresh cannot omit it')
    body_start = len(text) - len(body)
    raw_body_start = body_start + bisect_right(crlf_ends, body_start)
    raw_body = raw_text[raw_body_start:]
    def to_raw(position):
        offset = body_start + position
        return offset + bisect_right(crlf_ends, offset) - raw_body_start
    updated_raw, old_ids, outside_digest, regions = _reassemble(body, raw_body, to_raw, rendered, section)
    current_ids = {visual['id'] for visual, _, _ in rendered}
    if updated_raw == raw_body and (not replacing or artifact['records'] == saved['records']):
        return manuscript
    updated, _ = _normalized(updated_raw)
    result = copy.deepcopy(metadata)
    # deepcopy preserves YAML alias sharing; detach each field we modify from
    # historical mirrors elsewhere in the metadata before changing its value.
    result['generated_design'] = copy.deepcopy(result['generated_design'])
    result['managed_visual_refresh'] = copy.deepcopy(result.get('managed_visual_refresh', []))
    if 'generated_visuals' in result:
        result['generated_visuals'] = copy.deepcopy(result['generated_visuals'])
    result['generated_design']['body_sha256'] = _body_digest(updated)
    if replacing:
        result['generated_visuals']['records'] = artifact['records']
    if 'generated_visuals' in result:
        result['generated_visuals']['body_sha256'] = _body_digest(updated)
    event = dict(
        schema=1, source_commit=commit, original_manuscript_sha256=expected_sha256,
        previous_body_sha256=_body_digest(body), body_sha256=_body_digest(updated),
        visual_definitions_sha256=_json_digest([v for v, _, _ in rendered]),
        unchanged_native_records_sha256=_json_digest((artifact or {}).get('records', {})),
        preserved_outside_body_sha256=outside_digest, owned_edit_regions=regions,
        added_visuals=sorted(current_ids - old_ids),
        scope='Configured figure reassembly only; figure authorship remains per visual',
        new_inference=False, semantic_approval=False, human_review='unchanged')
    if replacing:
        event.pop('unchanged_native_records_sha256')
        event.update(schema=2, scope='Separately generated native graph replacement; original prose/authorship retained',
                     graph_records_replaced=True,
                     previous_native_records_sha256=_json_digest((saved or {}).get('records', {})),
                     current_native_records_sha256=_json_digest(artifact['records']))
    result.setdefault('managed_visual_refresh', []).append(event)
    ending = re.search(r'\r\n|\r|\n', raw_text)
    eol = ending[0] if ending else '\n'
    header = '---\n' + yaml.safe_dump(result, allow_unicode=True, sort_keys=False) + '---\n'
    derived = header.replace('\n', eol) + updated_raw
    view, _ = _normalized(derived)
    verify_design(model, section, view, cfg=selected)
    from_manuscript(selected, model, section, view)
    if section.get('scenario'):
        from .scenario_sections import verify
        verify(selected, model, section, result, updated)
    return derived.encode('utf-8')
