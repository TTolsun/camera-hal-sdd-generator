"""Construct the static HTML5 tree before assigning reader-item ownership."""
from xml.dom import Node as DOM

import html5lib


def parse(source, node_factory):
    parser = html5lib.HTMLParser(tree=html5lib.getTreeBuilder('dom'), namespaceHTMLElements=False)
    document = parser.parse(source, scripting=True)
    def convert(current):
        if current.nodeType in {DOM.TEXT_NODE, DOM.CDATA_SECTION_NODE}:
            return current.data
        if current.nodeType == DOM.COMMENT_NODE:
            return node_factory('!', {'value':current.data.strip()})
        if current.nodeType == DOM.ELEMENT_NODE:
            return node_factory(current.tagName.lower(),dict(current.attributes.items()),
                [child for item in current.childNodes if (child := convert(item)) is not None])
        return None

    try:
        if any(code == 'duplicate-attribute' for position,code,data in parser.errors):
            raise ValueError('Ambiguous duplicate HTML attributes in visualization input')
        return node_factory('document',children=[child for item in document.childNodes
                                                if (child := convert(item)) is not None])
    finally:
        document.unlink()
