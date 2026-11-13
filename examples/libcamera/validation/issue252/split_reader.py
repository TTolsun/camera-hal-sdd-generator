"""Expose the archived reader's document and source evidence as separate MCP calls."""
from __future__ import annotations

import json
from pathlib import Path
from secrets import token_urlsafe
import subprocess
import sys


SOURCE_BATCH_BYTES = 12_000
DESCRIPTIONS = {
    'route': 'Read the document excerpts and diagrams for one fixed question. '
             'Wait for its source_cursor, then call route_source with that cursor and the same question.',
    'route_source': 'Read one batch of numbered source lines reached through the document links. '
                    'Use the source_cursor from route or the next_cursor from the previous batch. '
                    'Wait for each result and continue until next_cursor is null.',
}


def text_result(value: dict) -> dict:
    return {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]}


def write_message(stream, message: dict) -> None:
    stream.write(json.dumps(message, ensure_ascii=False).encode('utf-8') + b'\n')
    stream.flush()


def paginate_source(windows: list[dict]) -> tuple[str | None, dict[str, dict]]:
    """Keep complete source windows and cap the serialized size of each tool response."""
    batches = []
    batch = []
    # A 16-byte cursor is always 22 ASCII characters. Reserve its serialized space on every page.
    def fits(items):
        payload = {'next_cursor': 'x' * 22, 'code_links_opened': items}
        return len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) <= SOURCE_BATCH_BYTES

    for window in windows:
        if not fits([window]):
            raise ValueError('One archived source window exceeds the source batch size.')
        if batch and not fits([*batch, window]):
            batches.append(batch)
            batch = []
        batch.append(window)
    if batch:
        batches.append(batch)

    cursors = [token_urlsafe(16) for _ in batches]
    pages = {
        cursor: {'next_cursor': next_cursor, 'code_links_opened': batch}
        for cursor, next_cursor, batch in zip(cursors, [*cursors[1:], None], batches)
    }
    return (cursors[0] if cursors else None), pages


def serve(reader: subprocess.Popen, requests, responses) -> None:
    routes = {}
    for line in requests:
        message = json.loads(line)
        method = message['method']
        if 'id' not in message:
            write_message(reader.stdin, message)
            continue
        params = message.get('params', {})
        if method == 'tools/call':
            name = params.get('name')
            arguments = params.get('arguments', {})
            question = arguments.get('question')
            try:
                if name not in DESCRIPTIONS or question not in ('Q1', 'Q2', 'Q3'):
                    raise ValueError('Use route or route_source with Q1, Q2 or Q3.')
                if name == 'route' and question not in routes:
                    write_message(reader.stdin, message)
                    reply = json.loads(reader.stdout.readline())
                    if 'error' in reply or reply['result'].get('isError'):
                        write_message(responses, reply)
                        continue
                    [content] = reply['result']['content']
                    bundle = json.loads(content['text'])
                    if not all(isinstance(bundle.get(part), list) for part in ('sections', 'code_links_opened')):
                        raise ValueError('Archived route must return document sections and source windows.')
                    first, pages = paginate_source(bundle['code_links_opened'])
                    routes[question] = ({'source_cursor': first, 'sections': bundle['sections']}, pages)
                document, pages = routes.get(question, (None, {}))
                if name == 'route':
                    payload = document
                else:
                    cursor = arguments.get('cursor')
                    if not isinstance(cursor, str) or cursor not in pages:
                        raise ValueError('Use the source_cursor from route or next_cursor from the previous batch.')
                    payload = pages[cursor]
                result = text_result(payload)
            except ValueError as error:
                result = {**text_result({'error': str(error)}), 'isError': True}
            write_message(responses, {'jsonrpc': '2.0', 'id': message['id'], 'result': result})
            continue

        write_message(reader.stdin, message)
        reply = json.loads(reader.stdout.readline())
        if method == 'tools/list' and 'result' in reply:
            [route] = [tool for tool in reply['result']['tools'] if tool['name'] == 'route']
            schema = route['inputSchema']
            source_schema = {**schema, 'properties': {**schema['properties'], 'cursor': {'type': 'string'}},
                             'required': [*schema['required'], 'cursor']}
            reply['result'] = {'tools': [
                {**route, 'description': DESCRIPTIONS['route']},
                {**route, 'name': 'route_source', 'description': DESCRIPTIONS['route_source'],
                 'inputSchema': source_schema},
            ]}
        write_message(responses, reply)


def main() -> None:
    archived_reader, site, journal = map(Path, sys.argv[1:])
    command = [sys.executable, str(archived_reader), str(site), str(journal)]
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE) as reader:
        try:
            serve(reader, sys.stdin.buffer, sys.stdout.buffer)
        finally:
            reader.stdin.close()
            if reader.poll() is None:
                reader.terminate()


if __name__ == '__main__':
    main()
