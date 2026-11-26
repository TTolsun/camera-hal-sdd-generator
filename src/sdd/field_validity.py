"""Preserve qualified field validity in claims about documented states."""

from collections import Counter
import re


INSTRUCTIONS = (
    'Preserve the distinction between guaranteed valid fields and fields that may be invalid. '
    'If a state documents some valid fields and says the other fields may be invalid, explicitly retain '
    'both facts when explaining field validity. Do not say that only those fields are valid or that all '
    'others are invalid. If the source declares the other fields invalid in another state, retain that '
    'state-specific restriction. Preserve these distinctions in every language you write.'
)

_IDENTIFIER = r'[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*'
_SOURCE_STATES = re.compile(
    rf'^\s*(?:\*\s*)?(?:[\\@](?:var|retval)\s+(?P<doxygen>{_IDENTIFIER})'
    rf'|(?P<heading>{_IDENTIFIER}):[ \t]+)', re.M | re.ASCII)
_OTHER_FIELDS = r'\b(?:other|remaining)\s+(?:\w+\s+){0,3}?fields?'
_MAY_BE_INVALID = re.compile(_OTHER_FIELDS + r'\s+(?:may|might|could)\s+be\s+invalid\b', re.I)
_FIELD_NAMES = re.compile(
    rf'(?P<names>{_IDENTIFIER}(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+){_IDENTIFIER})*)'
    r'\s+fields?\b[^.!?;]{0,100}?\b(?:are|is)\s+valid\b', re.I | re.ASCII)
_FIELD_WORDS = re.compile(r'메타데이터|필드|\b(?:metadata|fields?)\b', re.I)
_CLAUSE_END = re.compile(r'(?<=[.!?;])\s+|\n')
_ONLY_VALID = (
    re.compile(r'(?<!에서)(?<!경우)(?<!때)(?<!에)만\s*유효(?:합니다|하다고|하다|하며|하고|하거나|하지만|해|한)(?![가-힣])'
               r'(?!\s*(?:것(?:으로|이)?\s*)?(?:보장|보증))'),
    re.compile(r'\bonly\s+[^.?!;]{1,120}?\s+(?:are|is|remain|remains)\s+valid\b', re.I),
    re.compile(r'\b(?:are|is)\s+the\s+only\s+valid\s+fields?\b', re.I),
    re.compile(_OTHER_FIELDS + r'\s+(?:are|is)\s+invalid\b', re.I),
    re.compile(r'(?:나머지|그\s*밖의|다른)\s*(?:메타데이터\s*)?(?:필드|항목)?\s*(?:는|가|은|이)?'
               r'\s*(?:모두\s*)?(?:유효하지\s*않습니다|무효입니다|무효입니)'),
)


def check(text, sources, *, symbol=None):
    """Compare only the claim about the same source-identified state."""
    states = {}
    for source in sources:
        headings = list(_SOURCE_STATES.finditer(source))
        for current, following in zip(headings, [*headings[1:], None]):
            name = current['doxygen'] or current['heading']
            body = source[current.end():following.start() if following else len(source)]
            body = re.sub(r'(?m)^\s*\*\s*', ' ', body)
            if match := _MAY_BE_INVALID.search(body):
                fields = {part for names in _FIELD_NAMES.finditer(body)
                          for part in re.findall(_IDENTIFIER, names['names'], re.ASCII) if part.lower() != 'and'}
                states[name] = (' '.join(match[0].split()), fields)
            else:
                states.setdefault(name, None)
    if not any(states.values()):
        return
    spellings = {name: name for name in states}
    short_names = Counter(name.rsplit('::', 1)[-1] for name in states)
    for name in states:
        short = name.rsplit('::', 1)[-1]
        if short_names[short] == 1:
            spellings[short] = name
    alternatives = '|'.join(map(re.escape, sorted(spellings, key=len, reverse=True)))
    mentions = list(re.finditer(rf'(?<![A-Za-z0-9_])(?<!::)(?:{alternatives})(?![A-Za-z0-9_]|::)', text))
    claims = [(spellings[current[0]], text[current.end():following.start() if following else len(text)])
              for current, following in zip(mentions, [*mentions[1:], None])]
    if not claims and symbol in spellings:
        claims.append((spellings[symbol], text))
    for state, claim in claims:
        validity = states[state]
        if not validity:
            continue
        qualifier, fields = validity
        for clause in _CLAUSE_END.split(claim):
            for pattern in _ONLY_VALID:
                for finding in pattern.finditer(clause):
                    subject = clause[clause.rfind(',', 0, finding.start()) + 1:finding.end()]
                    names = set(re.findall(_IDENTIFIER, subject, re.ASCII))
                    if fields & names or _FIELD_WORDS.search(subject):
                        raise ValueError(f'{state}: source says "{qualifier}". Preserve which fields are valid '
                                         'and which other fields may be invalid in the same state; '
                                         'remove the exclusivity, not the qualification.')
