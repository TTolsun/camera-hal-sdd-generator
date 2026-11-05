"""Native independent CLI review of selected bilingual inventory items.

Run against immutable public baseline files. Every response and source window
is archived; a successful call is not final publication or human acceptance.
"""
import argparse
from dataclasses import asdict
import json
import re
from pathlib import Path
import subprocess
import hashlib
import html
import time
from urllib.parse import unquote, urlsplit

from sdd.config import load
from sdd.cli_agent import command, arguments, build_prompt
from sdd.generation_run import Execution
from sdd.llm import Agent
from sdd.visual_audit import (Document, digest, source_window, node_window, all_nodes,
                              plain, inspect_site, without_navigation,
                              source_container, _generated_route_alias, canonical,
                              WINDOW_BINDING)
from review_contract import SYSTEM, response_schema
from sdd.visual_presentation import paths as presentation_paths


def validate_presentation(contexts, ident):
    for value in contexts.values():
        for element in value['path']:
            attrs = element['attrs']
            if ('hidden' in attrs or 'inert' in attrs or attrs.get('style')
                    or str(attrs.get('aria-hidden', '')).lower() == 'true'):
                raise ValueError('Selected item has hidden or unassessed inline presentation; '
                                 'text-only review cannot approve it: '+ident)
            if (element['tag'] in {'template', 'noscript', 'style', 'script', 'img', 'image', 'svg', 'canvas',
                                   'video', 'audio', 'source', 'iframe', 'object', 'embed', 'use', 'link'}
                    or any(attrs.get(key) for key in ('src', 'srcset', 'poster', 'background'))):
                raise ValueError('Selected presentation needs asset/visual review; '
                                 'text-only CLI review cannot approve it: '+ident)


def presented_window(document, fragment, root, page):
    text = source_window(document, fragment, root=root, page=page, presentation=True)
    binding = json.loads(text.rsplit(WINDOW_BINDING, 1)[1])
    validate_presentation(binding['presentation_contexts'], page+'#'+fragment)
    return text


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: '+key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def literal_label(value):
    # Decode once, in this order, to preserve a literal entity-looking string
    # such as #quot; or &lt; encoded by the current Mermaid serializer.
    return re.sub(r'#([0-9]+);', lambda match: chr(int(match[1])),
                  html.unescape(re.sub(r'<br\s*/?>', '', value)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--site', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--item', action='append', help='Korean page#item, including its English peer')
    selection.add_argument('--page', help='Korean HTML page path, including all English peers')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--plan-only', action='store_true', help='Archive exact payload and measured input size without calling the CLI')
    parser.add_argument('--source', type=Path, help='Matching official checkout used for immutable git-show source windows')
    parser.add_argument('--facts', type=Path, help='Matching immutable structural facts for locating every displayed class declaration')
    parser.add_argument('--facts-sha256', help='Pinned digest from the separately retained extraction/integration provenance; required with --facts')
    parser.add_argument('--style-dir', type=Path, help='Actual writing rules matching the inventory policy; default ./style')
    parser.add_argument('--reader-models', type=Path, action='append', default=[],
                        help='Preliminary source-bound model ledger; context only, never item approval')
    parser.add_argument('--previous-inventory', type=Path,
                        help='Actual prior published item inventory for condition/exception preservation review')
    parser.add_argument('--historical-artifacts', type=Path,
                        help='Committed public repository for explicitly historical model artifact references')
    parser.add_argument('--fit-input', action='store_true', help='Execution-local character boundary equals the measured complete prompt')
    parser.add_argument('--native-input-cap', type=int, default=1000000,
                        help='Conservative execution-local CLI input cap; split groups instead of truncating evidence')
    parser.add_argument('--input-rationale', help='Required explanation for an execution-local input boundary adjustment')
    args = parser.parse_args()
    args.out = args.out.resolve()
    for immutable in [args.site, *([args.source] if args.source else []),
                      *([args.historical_artifacts] if args.historical_artifacts else [])]:
        target = immutable.resolve()
        if args.out.is_relative_to(target) or target.is_relative_to(args.out):
            raise ValueError('Review output must not overlap the site or source checkout: '+str(args.out))
    if args.facts:
        if (not re.fullmatch(r'[0-9a-f]{64}', args.facts_sha256 or '')
                or hashlib.sha256(args.facts.read_bytes()).hexdigest() != args.facts_sha256):
            raise ValueError('Structural facts do not match the independently pinned provenance digest')
    elif args.facts_sha256:
        raise ValueError('--facts-sha256 requires --facts')
    cfg = load(args.profile)
    cfg.root = args.out
    if (cfg.agent.kind != 'cli' or cfg.agent.runner != 'codex' or cfg.agent.model != 'gpt-6.1-terra'
            or cfg.agent.command or cfg.agent.args != ['-c', 'model_reasoning_effort="high"']):
        raise ValueError('This public independent review requires native Codex/Terra High with no inherited wrapper')
    report = json.loads(args.inventory.read_bytes())
    if not re.fullmatch(r'[0-9a-f]{40}', report.get('source_commit', '')):
        raise ValueError('Immutable source review requires a full source commit')
    facts = json.loads(args.facts.read_bytes()) if args.facts else None
    if facts and facts.get('meta', {}).get('source_commit') != report['source_commit']:
        raise ValueError('Structural facts and reviewed source commits differ')
    style_texts = {}
    for name, expected in report['policy'].get('style_policy', {}).items():
        raw = ((args.style_dir or Path.cwd()/'style')/name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Writing policy changed; make a new inventory before review')
        style_texts[name] = raw.decode('utf-8')
    selected = [row for row in report['items'] if (row['page'].removeprefix('en/') == args.page if args.page
                                                   else row['id'].removeprefix('en/') in args.item)]
    peers = {}
    for row in selected:
        peers.setdefault(row['id'].removeprefix('en/'), []).append(row['language'])
    if (not peers or any(sorted(values) != ['en', 'ko'] for values in peers.values())
            or (args.item and set(peers) != set(args.item))):
        raise ValueError('Every selected item needs exactly two language peers')
    if any(row['page'] in report['policy']['deferred_pages'] for row in selected):
        raise ValueError('Another session owns a selected item; wait for integration')
    actual = {row['id']:row for row in inspect_site(
        args.site, report['policy'], source_commit=report['source_commit'])['items']}
    derived = {'status', 'reason', 'judgment', 'source_windows', 'unreviewed_scope'}
    for row in selected:
        current = actual.get(row['id'])
        if current is None or any(row.get(key) != value for key,value in current.items() if key not in derived):
            raise ValueError('Inventory review content differs from the actual site: '+row['id'])
    selected = [actual[row['id']] for row in selected]
    for row in selected:
        if 'presentation_contexts' not in row:
            raise ValueError('Current item presentation context is missing; collect a fresh inventory')
        validate_presentation(row['presentation_contexts'], row['id'])
    windows, additional, document_windows, structural_classes, structural_scenarios = {}, {}, {}, {}, {}
    excluded_by_page = {}
    wanted_by_page = {}
    for row in selected:
        wanted_by_page.setdefault(row['page'], set()).update(
            (record['kind'], record['markup_sha256'], digest(record['presentation_context']))
            for record in row['excluded'])
    for row in selected:
        doc = None
        # Excluded source/log material stays outside explanatory length counts,
        # but its actual presentation must be visible to the editorial review.
        if row['excluded']:
            path = args.site/row['page']
            doc = Document(path.read_text(encoding='utf-8'))
            if row['page'] not in excluded_by_page:
                excluded_by_page[row['page']] = {}
                readable = without_navigation(doc.root)
                articles = list(readable.all('article'))
                if len(articles) != 1:
                    raise ValueError('Excluded presentation requires exactly one readable article')
                contexts = presentation_paths(readable)
                for node in all_nodes(articles[0]):
                    if (node.tag in {'pre', 'script', 'style'}
                            or (node.tag == 'details' and source_container(node))):
                        kind = node.tag
                    elif _generated_route_alias(node):
                        kind = 'navigation'
                    else:
                        continue
                    markup = canonical(node)
                    # Decide ownership from static markup before resolving any
                    # asset: unrelated excluded containers cannot block this item.
                    key = (kind, digest(markup), digest(contexts[id(node)]))
                    if key not in wanted_by_page[row['page']]:
                        continue
                    # Match the inventory's exact excluded container and tree;
                    # a generated route alias is visible review context, not
                    # explanatory prose and never a reason to drop the item.
                    text = node_window(node, args.site.resolve(), row['page'])
                    binding = json.loads(text.rsplit(WINDOW_BINDING, 1)[1])
                    # This reviewer sends text, not rendered media or asset
                    # contents. Keep unsupported selected material unresolved.
                    media = any(child.tag in {'style', 'script', 'img', 'image', 'svg', 'canvas', 'video', 'audio',
                                              'source', 'iframe', 'object', 'embed', 'use', 'link'}
                                or child.attrs.get('src') or child.attrs.get('poster')
                                for child in all_nodes(node))
                    excluded_by_page[row['page']][(kind, digest(text))] = dict(
                        text=text, markup=markup, markup_sha256=digest(markup),
                        unsupported_assets=bool(binding['assets']) or media)
            owned = []
            for record in row['excluded']:
                key = (record['kind'], record['sha256'])
                if key not in excluded_by_page[row['page']]:
                    raise ValueError('Excluded presentation changed since inventory: '+row['id'])
                value = excluded_by_page[row['page']][key]
                if value['unsupported_assets']:
                    raise ValueError('Selected excluded presentation needs asset/visual review; '
                                     'text-only CLI review cannot approve it: '+row['id'])
                owned.append(value)
            text = '\n\n'.join(value['text'] for value in owned)
            document_windows[row['id']] = dict(text=text, sha256=digest(text),
                window_hashes=[r['sha256'] for r in row['excluded']],
                presentation=[dict(kind=record['kind'], inventory_window_sha256=record['sha256'],
                                   markup=value['markup'], markup_sha256=value['markup_sha256'],
                                   ancestors_and_self=record['presentation_context'])
                              for record,value in zip(row['excluded'], owned)],
                purpose='Exactly this item\'s excluded source/log/code windows; not explanatory length or the entire page')
        structural_hrefs = []
        scenario = facts.get('scenarios', {}).get(Path(row['page']).stem) if facts else None
        if any(f['id'] == 'class-diagram' for f in row['figures']) or (scenario and row['figures']):
            # Class declarations live in the neighboring declaration table,
            # whereas behavioral excerpts often contain only implementations.
            doc = doc or Document((args.site/row['page']).read_text(encoding='utf-8'))
            labels, names = set(), set()
            if facts:
                labels = {literal_label(label)
                          for f in row['figures'] if f['id'] == 'class-diagram' or scenario
                          for label in re.findall(r'\b[cp]\d+\["([^"]+)"\]', f['source'])}
                for name, cls in facts['classes'].items():
                    def matches(label):
                        if scenario and label == 'Private':
                            return name.endswith('::'+scenario['entry'].split('::')[0]+'::Private')
                        return name == label or name.endswith('::'+label)
                    if not any(matches(label) for label in labels):
                        continue
                    structural_classes[name] = cls
                    names.add(name)
                    if cls.get('loc', {}).get('file'):
                        structural_hrefs.append('git:'+report['source_commit']+':'+cls['loc']['file'])
                if scenario:
                    shown = literal_label('\n'.join(f['source'] for f in row['figures']))
                    messages = [m for m in scenario['messages'] if m['src'] in labels and m['dst'] in labels
                                and m['name']+'()' in shown]
                    structural_scenarios[scenario['id']] = dict(entry=scenario['entry'], messages=messages,
                        scope='Source-extracted shown static call candidates; not runtime order or execution evidence')
                    structural_hrefs.extend('git:'+report['source_commit']+':'+m['loc']['file'] for m in messages if m.get('loc'))
            # Do not collect every page link: #main would resend the whole
            # page and unrelated neighboring behavioral windows. Only the
            # declaration rows for actual displayed symbols are needed here.
            structural_hrefs.extend(a.attrs.get('href', '') for a in doc.root.all('a')
                if urlsplit(a.attrs.get('href', '')).fragment.startswith('symbol-')
                and (not facts or plain(a) in names or plain(a) in labels))
            for href in structural_hrefs.copy():
                parts = urlsplit(href)
                if (parts.scheme or parts.netloc or not parts.path.endswith('.html')
                        or not parts.fragment.startswith('symbol-')):
                    continue
                from sdd.site_paths import owned_path
                name = ((args.site/row['page']).parent/unquote(parts.path)).resolve().relative_to(args.site.resolve()).as_posix()
                target = owned_path(args.site.resolve(), name)
                symbols = Document(target.read_text(encoding='utf-8'))
                found = [n for n in all_nodes(symbols.root) if n.attrs.get('id') == unquote(parts.fragment)]
                if len(found) != 1:
                    raise ValueError('Class declaration window missing or ambiguous: '+href)
                text = presented_window(symbols, unquote(parts.fragment), args.site.resolve(), name)
                document_windows[name+'#'+parts.fragment] = dict(text=text, sha256=digest(text),
                    purpose='Exact class declaration row linked by this page; not explanatory length')
                structural_hrefs.extend(a.attrs.get('href', '') for a in found[0].all('a'))
        for href in row['available_source_windows'] + [u for f in row['figures'] for u in f['evidence']] + structural_hrefs:
            parts = urlsplit(href)
            if parts.scheme or parts.netloc:
                marker = '/'+report['source_commit']+'/'
                git_path = parts.scheme == 'git' and parts.path.startswith(report['source_commit']+':')
                if args.source and (git_path or marker in parts.path):
                    name = unquote(parts.path.split(':', 1)[1] if git_path else parts.path.split(marker, 1)[1])
                    from sdd.site_paths import owned_path
                    owned_path(args.source.resolve(), name)
                    key = 'git:'+report['source_commit']+':'+name
                    if key not in additional:
                        raw = subprocess.check_output(['git', 'show', report['source_commit']+':./'+name], cwd=args.source.resolve())
                        text = raw.decode('utf-8')
                        additional[key] = dict(file=name, source_commit=report['source_commit'],
                            first_line=1, last_line=len(text.splitlines()), sha256=hashlib.sha256(raw).hexdigest(), text=text)
                continue
            if not parts.fragment:
                continue
            path = (args.site/row['page']).parent/unquote(parts.path) if parts.path else args.site/row['page']
            path = path.resolve()
            if not path.is_relative_to(args.site.resolve()) or not path.is_file():
                raise ValueError('Missing or unsafe source window: '+href)
            key = path.relative_to(args.site.resolve()).as_posix()+'#'+parts.fragment
            page = path.relative_to(args.site.resolve()).as_posix()
            raw = path.read_text(encoding='utf-8')
            if path.suffix == '.html':
                text = presented_window(Document(raw), unquote(parts.fragment), args.site.resolve(), page)
            else:
                lines = re.fullmatch(r'L([1-9][0-9]*)(?:-L([1-9][0-9]*))?', unquote(parts.fragment))
                if not lines or int(lines[1]) > int(lines[2] or lines[1]) or int(lines[2] or lines[1]) > len(raw.splitlines()):
                    raise ValueError('Source window line range is invalid: '+key)
                text = raw
            windows[key] = dict(text=text, sha256=digest(text))
        document = {key:row[key] for key in ('title', 'body', 'tables', 'content_blocks')}
        document_hash = digest(document)
        for key, expected_hash in row['source_window_hashes'].items():
            if key == 'item:'+row['id'] or (key == row['id'] and expected_hash == document_hash):
                text = json.dumps(document, ensure_ascii=False, sort_keys=True)
                actual_hash = document_hash
            elif '#' not in key:
                from sdd.site_paths import owned_path
                path = owned_path(args.site.resolve(), key)
                if path.suffix.lower() == '.html':
                    raise ValueError('Unscoped whole-page HTML evidence needs an exact reviewed fragment: '+key)
                raw = path.read_bytes()
                actual_hash = digest(raw.hex())
                try:
                    text = raw.decode('utf-8')
                except UnicodeError as exc:
                    raise ValueError('Text-only native review cannot inspect this binary window: '+key) from exc
            else:
                target, fragment = key.rsplit('#', 1)
                from sdd.site_paths import owned_path
                path = owned_path(args.site.resolve(), target)
                raw = path.read_text(encoding='utf-8')
                if path.suffix == '.html':
                    text = presented_window(Document(raw), fragment, args.site.resolve(), target)
                    actual_hash = digest([path.read_bytes().hex(), text] if target != row['page'] else text)
                else:
                    text, actual_hash = raw, digest(path.read_bytes().hex())
            if actual_hash != expected_hash:
                raise ValueError('Source window changed since inventory; make a new inventory: '+key)
            windows[key] = dict(text=text, sha256=digest(text), inventory_sha256=actual_hash)
        if not set(row['source_window_hashes']) <= windows.keys():
            raise ValueError('Inventory evidence was not completely collected: '+row['id'])
    current = {row['id']:row['fingerprint'] for row in inspect_site(
        args.site, report['policy'], source_commit=report['source_commit'])['items']}
    if any(current.get(row['id']) != row['fingerprint'] for row in selected):
        raise ValueError('Selected site items changed since inventory; make a new inventory')
    schema = response_schema([f for row in selected for f in row['figures']])
    figures, item_inputs = {}, []
    for row in selected:
        compact = {k:v for k,v in row.items() if k not in {'paragraphs', 'figures'}}
        compact['figures'] = []
        for figure in row['figures']:
            key = row['page']+'/'+figure['id']
            if key in figures and figures[key] != figure:
                raise ValueError('One page has conflicting figure definitions: '+key)
            figures[key] = figure
            compact['figures'].append(dict(id=figure['id'], sha256=figure['sha256'], definition=key))
        item_inputs.append(compact)
    payload = dict(items=item_inputs, figures=figures, source_windows=windows, additional_source_windows=additional,
                   document_windows=document_windows,
                   structural_classes=structural_classes,
                   structural_scenarios=structural_scenarios,
                   structural_facts_sha256=hashlib.sha256(args.facts.read_bytes()).hexdigest() if args.facts else None,
                   visual_policy=report['policy'], writing_rules=style_texts,
                   inventory_sha256=digest(report), source_commit=report.get('source_commit'))
    if args.reader_models:
        preliminary, provenance = {}, []
        wanted = {row['id'].removeprefix('en/') for row in selected}
        for path in args.reader_models:
            raw = path.read_bytes()
            ledger = strict_json(raw)
            if type(ledger.get('schema')) is not int or ledger['schema'] != 1 or not isinstance(ledger.get('items'), dict):
                raise ValueError('Reader model context requires a schema1 item ledger')
            provenance.append(dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                                   source_commit=ledger.get('source_commit')))
            for ident in wanted & ledger['items'].keys():
                value = ledger['items'][ident]
                if (value.get('item_id') != ident or not isinstance(value.get('model'), dict)
                        or value['model'].get('item_id') != ident):
                    raise ValueError('Invalid preliminary reader model identity: '+ident)
                if ident in preliminary and preliminary[ident] != value['model']:
                    raise ValueError('Conflicting preliminary reader models: '+ident)
                preliminary[ident] = value['model']
        payload['preliminary_untrusted_reader_models'] = preliminary
        payload['reader_model_input_provenance'] = provenance
        def model_references(value):
            if isinstance(value, dict):
                if 'window' in value or 'quote' in value:
                    if (set(value) != {'window', 'quote'}
                            or any(not isinstance(value[key], str) or not value[key].strip()
                                   for key in ('window', 'quote'))):
                        raise ValueError('Preliminary model citations require nonempty window and quote strings')
                    yield value['window']
                for child in value.values():
                    yield from model_references(child)
            elif isinstance(value, list):
                for child in value:
                    yield from model_references(child)
        references = list(model_references(preliminary))
        if any(not isinstance(value, str) for value in references):
            raise ValueError('Preliminary model references must be strings')
        contextual_documents = {}
        historical_context = {}
        reference_map = {}
        historical_commit = None
        for reference in sorted(set(references)):
            match = re.fullmatch(r'git:[0-9a-f]{40}:(.+)', reference)
            if not match:
                if reference.startswith('git:'):
                    raise ValueError('Malformed preliminary Git reference: '+reference)
                if reference.startswith(('document:', 'reference:')):
                    ident = reference.split(':', 1)[1]
                    if ident not in actual:
                        raise ValueError('Unknown preliminary document reference: '+reference)
                    row = actual[ident]
                    text = json.dumps({k:row[k] for k in ('title', 'body', 'tables', 'content_blocks')},
                                      ensure_ascii=False, sort_keys=True)
                    contextual_documents[reference] = dict(item_id=ident, fingerprint=row['fingerprint'],
                        text=text, sha256=digest(text), scope='Current document context only; not implementation evidence or inherited model approval.')
                elif reference.startswith('artifact:'):
                    if args.historical_artifacts is None:
                        raise ValueError('Historical artifact references require --historical-artifacts')
                    name = reference.removeprefix('artifact:')
                    from sdd.site_paths import owned_path
                    owned_path(args.historical_artifacts.resolve(), name)
                    if historical_commit is None:
                        historical_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                            cwd=args.historical_artifacts.resolve(), text=True).strip()
                    raw = subprocess.check_output(['git', 'show', historical_commit+':./'+name],
                        cwd=args.historical_artifacts.resolve())
                    text = raw.decode('utf-8')
                    historical_context[reference] = dict(file=name, artifact_repository_commit=historical_commit,
                        first_line=1, last_line=len(text.splitlines()), sha256=hashlib.sha256(raw).hexdigest(),
                        text=text, scope='Committed historical observation/procedure artifact only. Original recorded source/dates remain in the text; not a new execution or current implementation evidence.')
                elif reference not in windows and reference not in additional:
                    raise ValueError('Unsupported preliminary evidence reference: '+reference)
                continue
            if args.source is None:
                raise ValueError('Source-bound preliminary models require --source')
            name = match[1]
            from sdd.site_paths import owned_path
            owned_path(args.source.resolve(), name)
            key = 'git:'+report['source_commit']+':'+name
            reference_map[reference] = key
            if key not in additional:
                raw = subprocess.check_output(['git', 'show', report['source_commit']+':./'+name],
                                              cwd=args.source.resolve())
                text = raw.decode('utf-8')
                additional[key] = dict(file=name, source_commit=report['source_commit'],
                    first_line=1, last_line=len(text.splitlines()), sha256=hashlib.sha256(raw).hexdigest(), text=text)
        payload['preliminary_current_document_context'] = contextual_documents
        payload['preliminary_current_git_reference_map'] = reference_map
        payload['preliminary_historical_artifact_context'] = historical_context
    if args.previous_inventory:
        raw = args.previous_inventory.read_bytes()
        previous = strict_json(raw)
        if type(previous.get('schema')) is not int or previous['schema'] != 1 or not isinstance(previous.get('items'), list):
            raise ValueError('Previous published context requires a schema1 inventory')
        before = {row['id']:row for row in previous['items']}
        if len(before) != len(previous['items']):
            raise ValueError('Previous inventory has duplicate identities')
        payload['previous_published_items'] = {row['id']:before[row['id']]
                                               for row in selected if row['id'] in before}
        payload['previous_inventory_provenance'] = dict(
            sha256=hashlib.sha256(raw).hexdigest(), source_commit=previous.get('source_commit'))
    if args.reader_models or args.previous_inventory:
        payload['context_constraints'] = [
            'Preliminary reader models and prior published items are untrusted comparison context, not current evidence or inherited approval. Judge the actual current items and supplied immutable sources independently.',
            'Check the actual reader question, central conclusion, necessary conditions and useful counterexamples before figure adequacy. Preserve the full question and source-supported exceptions. Do not narrow a question to make its diagram pass or demand every irrelevant implementation detail.',
            'When prior published text differs, check whether reader-relevant conditions, ownership and exceptions remain supported in the current item. Correcting an old source-inaccurate claim is allowed; preserve its correction rationale rather than treating the old claim as authority.',
            'A model-only pass never approves a current figure, omission, translation, source commit or writing policy. Apply current writing_rules and current exact item fingerprints, even where the original manuscript was authenticated under historical policy bytes.',
            'Preliminary models may cite older commits. Only current pinned immutable additional_source_windows and current item evidence establish present behavior; check the actual current source rather than inheriting a model conclusion.',
            'Do not repeat diagrams solely for counts. A concrete short table or simple independent facts may suffice with an individual reason; a general link elsewhere does not satisfy a needed local figure.'
        ]
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/'inputs.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (args.out/'execution-profile.json').write_text(json.dumps(dict(agent=asdict(cfg.agent),
        argv=command(cfg.agent)+arguments(cfg.agent, schema)), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    system = SYSTEM
    user = json.dumps(payload, ensure_ascii=False)
    measured = len(build_prompt(system, user, schema))
    if args.fit_input:
        if not args.input_rationale:
            raise ValueError('--fit-input requires a measured-input rationale; model/runner/args remain fixed')
        cfg.agent.max_input_chars = max(cfg.agent.max_input_chars, measured)
        (args.out/'execution-profile.json').write_text(json.dumps(dict(agent=asdict(cfg.agent),
            argv=command(cfg.agent)+arguments(cfg.agent, schema), input_rationale=args.input_rationale),
            ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if args.native_input_cap < 1:
        raise ValueError('The native input cap must be positive')
    plan = dict(input_chars=measured, max_input_chars=cfg.agent.max_input_chars,
                native_input_cap=args.native_input_cap,
                fits=measured <= min(cfg.agent.max_input_chars, args.native_input_cap), native_call=False,
                pages=sorted({row['page'] for row in selected}), items=len(selected))
    (args.out/'input-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if args.plan_only:
        print(json.dumps(plan, ensure_ascii=False))
        return
    if not plan['fits']:
        raise ValueError('Measured complete input exceeds the configured boundary; split item groups before native calls')
    started = time.monotonic()
    execution = Execution(cfg, Agent(cfg.agent, dump_dir=args.out/'prompts'))
    try:
        with execution.track('item-visual-review'):
            response = execution.chat(system, user, tag='item-visual-review', response_schema=schema)
        result = json.loads(response)
        ids = [r['id'] for r in result['items']]
        if sorted(ids) != sorted(r['id'] for r in selected):
            raise ValueError('Independent review IDs differ from supplied item set')
        for row in result['items']:
            if not set(row['additional_source_windows']) <= additional.keys():
                raise ValueError('Review named an unsupplied additional source window')
        result.update(seconds=round(time.monotonic()-started, 3), human_review='pending',
                      inventory_sha256=digest(report), input_sha256=digest(payload),
                      additional_source_manifest={key:{k:v for k,v in value.items() if k != 'text'} for key,value in additional.items()})
        (args.out/'review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(result, ensure_ascii=True))
    finally:
        execution.persist()


if __name__ == '__main__':
    main()
