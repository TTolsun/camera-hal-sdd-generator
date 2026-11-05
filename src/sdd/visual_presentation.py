"""Bind item presentation ancestry without treating it as explanatory prose.

This records static markup, not computed CSS or browser/device acceptance.
"""
import hashlib
import json


def paths(root):
    result = {}

    def visit(node, parents, position=0):
        if isinstance(node, str):
            return
        here = parents + ([dict(tag=node.tag, attrs=dict(node.attrs), position=position)]
                          if node.tag != 'document' else [])
        result[id(node)] = here
        for index,child in enumerate(node.children):
            visit(child, here, index)

    visit(root, [])
    return result


def bind(row, node, contexts, *, subtree=False, text=False):
    if node.tag == '!':
        return

    def visit(current, first=False):
        if isinstance(current, str):
            return
        if first or subtree:
            value = dict(path=contexts[id(current)])
            if subtree or text:
                # Associate text with its exact element once; aggregating every
                # ancestor's text repeats long source excerpts quadratically.
                value['text'] = ''.join(child for child in current.children if isinstance(child, str))
                value['text_nodes'] = [dict(position=i,text=child) for i,child in enumerate(current.children)
                                       if isinstance(child, str)]
            key = hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            row['presentation_contexts'][key] = value
        if subtree:
            for child in current.children:
                visit(child)

    visit(node, True)


def bind_text(row, parent, position, value, contexts):
    record = dict(path=contexts[id(parent)], text_nodes=[dict(position=position,text=value)])
    key = hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    row['presentation_contexts'][key] = record
