"""Opt-in language and manuscript-grounding checks for claim reviews."""
import re


KOREAN_REVIEW_INSTRUCTIONS = """각 claim, correction, consequence의 설명은 한국어로 작성하고 코드 식별자와 기술 기호는 원문대로 유지한다.
후보 원고가 출처와 모순되는 사실을 명시한 경우에만 stale로 판정한다. 이때 claim에는 후보 원고의 관련 절 하나를 가급적 통째로, 원문에 연속해서 나오는 그대로 적는다. correction에는 원고가 실제로 말한 내용과 코드에서 확인되는 사실이 어떻게 다른지 설명한다.
원고의 설명이 빠져 있거나 모호하면 missing으로 판정하고 무엇이 빠졌거나 불분명한지 설명한다. 과거 코드, 현재 코드, 후보 원고의 진술을 분명히 구별한다. 원고가 어떤 동작을 명시한다고 서술할 때는 해당 원문을 인용한다. 코드에서만 확인되는 동작을 원고가 설명한 것으로 돌리지 않는다. 이 원칙은 supported와 missing의 설명 및 correction에도 적용한다."""

_HANGUL = re.compile(r'[가-힣\u1100-\u11ff\u3131-\u318e\ua960-\ua97f\ud7b0-\ud7ff]')
_KANA = re.compile(r'[ぁ-ゖゝ-ゟァ-ヺー-ヿㇰ-ㇿｦ-ﾟ\U0001aff0-\U0001afff\U0001b000-\U0001b16f]')
_INLINE_CODE = re.compile(r'(?<!`)(`+)(?!`)([^`\r\n]+)\1(?!`)')
_TECHNICAL_NAME = re.compile(r'[\w]+(?:[.:/#][\w]+)*(?:\(\)|\[\])?')
_QUOTES = re.compile(r'"([^"\n]+)"|“([^”\n]+)”|‘([^’\n]+)’|「([^」\n]+)」|(?<!\w)\'([^\'\n]+)\'(?!\w)')
_EMPTY_ASSERTIONS = {'한다', '있다', '없다', '된다', '이다', '아니다'}


def _exact_quotes(text, candidate):
    for match in _QUOTES.finditer(text):
        quote = next(group for group in match.groups() if group is not None)
        if sum(character.isalnum() for character in quote) >= 2 and quote in candidate:
            yield match


def _check_prose(text, candidate, field, *, verbatim=False):
    if not isinstance(text, str):
        raise ValueError(f'{field} must be Korean prose')

    def kana_in_code(match):
        name = match[2]
        if _TECHNICAL_NAME.fullmatch(name) and any(c in name for c in '_.:/#(['):
            return ' '
        return match[0]

    kana_text = _INLINE_CODE.sub(kana_in_code, text)
    for match in reversed(list(_exact_quotes(kana_text, candidate))):
        kana_text = kana_text[:match.start()] + ' ' + kana_text[match.end():]
    if _KANA.search(kana_text):
        raise ValueError(f'{field} contains Japanese kana in prose')
    prose = _INLINE_CODE.sub(' ', text)
    if not _HANGUL.search(prose):
        raise ValueError(f'{field} must contain Hangul in its prose')
    if verbatim:
        if (text not in candidate or len(_HANGUL.findall(prose)) < 2
                or prose.strip(' .!?。\t\r\n') in _EMPTY_ASSERTIONS):
            raise ValueError(f'{field} must be a meaningful verbatim substring of the candidate for stale')


def validate_korean_review(review, candidate):
    """Check native claim prose and quotation grounding without deciding semantic contradiction."""
    if not isinstance(candidate, str):
        raise ValueError('Korean review requires the exact candidate text')
    if not isinstance(review, dict) or not isinstance(review.get('claims'), list):
        raise ValueError('Korean review requires a claims list')
    for index, claim in enumerate(review['claims'], start=1):
        if not isinstance(claim, dict):
            raise ValueError(f'Claim {index} must be an object')
        stale = claim.get('assessment') == 'stale'
        for name in ('claim', 'correction', 'consequence'):
            text = claim.get(name)
            if text is not None or (stale and name == 'claim'):
                _check_prose(text, candidate, f'Claim {index} {name}',
                             verbatim=stale and name == 'claim')
