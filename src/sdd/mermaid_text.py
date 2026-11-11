"""Literal text in quoted Mermaid flowchart labels, separate from HTML escaping."""
import html

_ENTITIES = {char:'#'+str(ord(char))+';' for char in '&"\'<>#\\|`*_~[]()!='}


def label(value):
    # Mermaid uses #number; (without &) inside its grammar. HTML escaping is
    # applied separately when the complete source is placed in a <pre>.
    return ''.join(_ENTITIES.get(char, char) for char in value)


def wrapped_html_label(value):
    """Convert escaped wrapper output, preserving only its generated breaks."""
    return '<br/>'.join(label(html.unescape(part)) for part in value.split('<br/>'))
