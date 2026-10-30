"""Read-only inline identities and authenticated cited source for translation."""
import hashlib
import json
from functools import lru_cache
from pathlib import PurePosixPath
import re
import subprocess


def _sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _identity(record):
    return _sha(json.dumps(record, ensure_ascii=False, sort_keys=True))


def git_loader(root, commit):
    @lru_cache(maxsize=None)
    def load(file):
        path = PurePosixPath(file)
        if (not re.fullmatch(r'[0-9a-f]{40}', commit) or path.is_absolute()
                or '..' in path.parts or ':' in file or '\\' in file):
            raise ValueError('Invalid immutable translation source location')
        result = subprocess.run(['git', 'show', f'{commit}:./{file}'], cwd=root,
                                capture_output=True, encoding='utf-8', check=False)
        if result.returncode:
            raise ValueError(f'Translation source unavailable at {commit}: {file}')
        return result.stdout
    return load


def _bounds(record):
    start, end, text = record.get('line'), record.get('end_line'), record.get('text')
    return (type(start) is int and start > 0 and type(end) is int
            and isinstance(text, str) and bool(text)
            and end in {start + text.count('\n'), start + text.count('\n') - int(text.endswith('\n'))})


def _contains_line(record, line):
    text, start = record.get('text'), record.get('line')
    return (isinstance(text, str) and bool(text) and type(start) is int
            and start <= line <= start + text.count('\n') - int(text.endswith('\n')))


def collect(document, model, contexts, pool, source_loader=None):
    from .site_localization import DisplayText

    def observe(key, resolved, tokens, attrs):
        refs = json.loads(attrs.get('data-sdd-evidence', '[]'))
        ids = set()
        for ref in refs:
            if not isinstance(ref, list) or not ref or not isinstance(ref[0], str):
                raise ValueError('Malformed translation source reference')
            file, separator, number = ref[0].rpartition(':')
            if not separator or not number.isdigit() or int(number) < 1:
                raise ValueError('Malformed translation source location')
            candidates = [r for r in model.evidence.values()
                          if r.get('status') == 'available' and r.get('file') == file
                          and _contains_line(r, int(number))]
            if not candidates:
                if source_loader is None or ref[0] not in model.citations:
                    raise ValueError(f'Translation source reference cannot be resolved: {ref[0]}')
                text = source_loader(file)
                record = dict(file=file, line=1, end_line=1 + text.count('\n'),
                              text=text, sha256=_sha(text), commit=model.meta['source_commit'])
                if not _contains_line(record, int(number)):
                    raise ValueError('Translation source line is outside the pinned file')
            else:
                record = min(candidates, key=lambda r: len(r['text']) if isinstance(r.get('text'), str) else 0)
            if (record.get('commit') != model.meta.get('source_commit') or not _bounds(record)
                    or _sha(record['text']) != record.get('sha256')):
                raise ValueError('Translation source checksum mismatch')
            context = record.get('context')
            context = context if isinstance(context, dict) and 'text' in context else record
            if (context.get('file', file) != file
                    or context.get('source_commit', model.meta['source_commit']) != model.meta['source_commit']
                    or context.get('commit', model.meta['source_commit']) != model.meta['source_commit']):
                raise ValueError('Translation source file or commit mismatch')
            if (not _bounds(context) or _sha(context['text']) != context.get('sha256')
                    or not context['line'] <= record['line'] <= record['end_line'] <= context['end_line']
                    or record['text'] not in context['text']):
                raise ValueError('Translation source context checksum mismatch')
            positions = [m.start() for m in re.finditer(re.escape(record['text']), context['text'])]
            if not any(context['line'] + context['text'][:offset].count('\n') == record['line'] for offset in positions):
                raise ValueError('Translation source context line binding mismatch')
            item = dict(file=file, line=context.get('line', record['line']),
                        end_line=context.get('end_line', record.get('end_line', record['line'])),
                        text=context['text'], sha256=context['sha256'], source_commit=model.meta['source_commit'])
            identity = _identity(item)
            pool[identity] = item
            ids.add(identity)
        item = dict(resolved_source=resolved, inline_tokens=tokens, source_ids=sorted(ids))
        if attrs.get('translation-unit'):
            item['unit_kind'] = attrs['translation-unit']
        if item not in contexts.setdefault(key, []):
            contexts[key].append(item)

    parser = DisplayText(lambda value: value, context_observer=observe)
    parser.feed(document)
    parser.output


def for_source(catalog, source):
    result = []
    for context in catalog.get('translation_contexts', {}).get(source, []):
        sources = []
        for identity in context['source_ids']:
            record = catalog.get('source_contexts', {}).get(identity)
            if (not isinstance(record, dict) or _identity(record) != identity
                    or not isinstance(record.get('text'), str) or not isinstance(record.get('sha256'), str)
                    or _sha(record['text']) != record['sha256']
                    or record['source_commit'] != catalog.get('source_commit')):
                raise ValueError('Translation context identity or source commit mismatch')
            sources.append(record)
        item = dict(resolved_source=context['resolved_source'], inline_tokens=context['inline_tokens'], sources=sources)
        if 'unit_kind' in context:
            item['unit_kind'] = context['unit_kind']
        result.append(item)
    return result


def matches_archive(record, key, catalog, source):
    try:
        request, _ = json.JSONDecoder().raw_decode(record['request']['user'])
        old = request.get('read_only_context', {}).get(key, [])
    except (KeyError, TypeError, ValueError):
        return False
    return old == for_source(catalog, source)
