"""Expose the archived reader's document and source evidence as separate MCP calls."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROUTE_PARTS = {'route': 'sections', 'route_source': 'code_links_opened'}
DESCRIPTIONS = {
    'route': 'Read the document excerpts and diagrams for one fixed question. '
             'Call route_source with the same question for the linked source.',
    'route_source': 'Read the numbered source lines reached through the document links '
                    'for the same fixed question. Returns source windows without document excerpts.',
}


def text_result(value: dict) -> dict:
    return {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]}


def write_message(stream, message: dict) -> None:
    stream.write(json.dumps(message, ensure_ascii=False).encode('utf-8') + b'\n')
    stream.flush()


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
            question = params.get('arguments', {}).get('question')
            if name not in ROUTE_PARTS or question not in ('Q1', 'Q2', 'Q3'):
                result = {**text_result({'error': 'Use route or route_source with Q1, Q2 or Q3.'}),
                          'isError': True}
                write_message(responses, {'jsonrpc': '2.0', 'id': message['id'], 'result': result})
                continue
            if question not in routes:
                archived_call = {**message, 'params': {**params, 'name': 'route'}}
                write_message(reader.stdin, archived_call)
                reply = json.loads(reader.stdout.readline())
                if 'error' in reply or reply['result'].get('isError'):
                    write_message(responses, reply)
                    continue
                [content] = reply['result']['content']
                bundle = json.loads(content['text'])
                if not all(isinstance(bundle.get(part), list) for part in ROUTE_PARTS.values()):
                    raise ValueError('Archived route must return document sections and source windows.')
                routes[question] = bundle
            part = ROUTE_PARTS[name]
            result = text_result({part: routes[question][part]})
            write_message(responses, {'jsonrpc': '2.0', 'id': message['id'], 'result': result})
            continue

        write_message(reader.stdin, message)
        reply = json.loads(reader.stdout.readline())
        if method == 'tools/list' and 'result' in reply:
            [route] = [tool for tool in reply['result']['tools'] if tool['name'] == 'route']
            reply['result'] = {'tools': [
                {**route, 'name': name, 'description': description}
                for name, description in DESCRIPTIONS.items()
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
