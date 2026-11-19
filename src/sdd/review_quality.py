"""Opt-in language and manuscript-grounding checks for claim reviews."""
import re


KOREAN_REVIEW_INSTRUCTIONS = """claim, correction, consequence는 한국어로 작성하고 코드 식별자와 기술 기호는 원문대로 유지한다.
supported와 stale의 claim에는 판정 근거가 되는 짧고 구체적인 구절을 후보 원고에서 연속된 원문 그대로 옮긴다. 인용 표시, 문장부호, 마크다운을 앞뒤에 덧붙이지 않는다. 원고가 출처와 모순되는 사실을 명시한 경우에만 stale로 판정한다.
설명이 빠졌거나 모호하면 missing으로 판정하고 claim에 빠졌거나 불분명한 조건이나 동작을 직접 적는다. missing의 claim과 모든 correction, consequence에서 원고·후보·초안·본문·문서 같은 지칭어를 사용하거나 원고가 무엇을 설명하는지 바꾸어 쓰지 않는다. 출처에서 확인한 경로, 필요한 수정, 예상되는 영향을 해당 필드에 직접 적는다. 과거 코드와 현재 코드를 구별하고 correction에서 supported 판정으로 이미 확인한 내용을 반복하지 않는다.
이 필드들에서 후보 원고의 표현을 꼭 인용해야 할 때는 원문에 연속해서 나오는 구체적인 구절을 «...» 안에 그대로 적는다. 인용 앞뒤에도 원고에 진술을 돌리는 표현을 쓰지 않는다.
각 references 항목의 줄 범위는 제공된 함수 하나의 시작 줄부터 끝 줄까지의 범위 안에 있어야 한다. 여러 함수 범위가 필요하면 항목을 따로 작성하고, 세부 줄 범위가 확실하지 않으면 임의로 만들지 말고 제공된 함수의 전체 범위를 인용한다."""

_HANGUL = re.compile(r'[가-힣\u1100-\u11ff\u3131-\u318e\ua960-\ua97f\ud7b0-\ud7ff]')
_KANA = re.compile(r'[ぁ-ゖゝ-ゟァ-ヺー-ヿㇰ-ㇿｦ-ﾟ\U0001aff0-\U0001afff\U0001b000-\U0001b16f]')
_INLINE_CODE = re.compile(r'(?<!`)(`+)(?!`)([^`\r\n]+)\1(?!`)')
_TECHNICAL_NAME = re.compile(r'\w+(?:[.:/#]\w+)*(?:\(\)|\[\])?')
_TAGGED_LITERAL = re.compile(r'«([^«»\r\n]+)»')
# 후보정 is a technical term with a different meaning from 후보.
_MANUSCRIPT_REFERENCE = re.compile(r'원고|후보(?!정)|초안|본문|문서|작성본|검토본|설계서')
_EMPTY_ASSERTIONS = {'한다', '있다', '없다', '된다', '이다', '아니다'}
_VERBATIM_ASSESSMENTS = {'supported', 'stale'}


def _is_meaningful_literal(text):
    if text != text.strip():
        return False
    content = text.strip(' .!?。…,:;\t\r\n`*“”‘’"\'«»')
    return (sum(character.isalnum() for character in content) >= 2
            and content not in _EMPTY_ASSERTIONS)


def _without_technical_names(match):
    name = match[2]
    if _TECHNICAL_NAME.fullmatch(name) and any(character in name for character in '_.:/#(['):
        return ' '
    return match[0]


def _check_prose(text, candidate, field, *, verbatim):
    if not isinstance(text, str):
        raise ValueError(f'{field} must be Korean prose')

    def omit_grounded_literal(match):
        literal = match[1]
        if literal in candidate and _is_meaningful_literal(literal):
            return ' '
        return match[0]

    prose = text if verbatim else _TAGGED_LITERAL.sub(omit_grounded_literal, text)
    if _KANA.search(_INLINE_CODE.sub(_without_technical_names, prose)):
        raise ValueError(f'{field} contains Japanese kana in prose')
    if not _HANGUL.search(_INLINE_CODE.sub(' ', prose)):
        raise ValueError(f'{field} must contain Hangul in its prose')
    return prose


def _check_grounding(prose, candidate, field, *, verbatim):
    if verbatim:
        if (prose not in candidate or not _is_meaningful_literal(prose)
                or len(_HANGUL.findall(_INLINE_CODE.sub(' ', prose))) < 2):
            raise ValueError(f'{field} must be a meaningful verbatim substring of the candidate')
        return

    if '«' in prose or '»' in prose:
        raise ValueError(f'{field} must use «...» only for a meaningful verbatim substring of the candidate')
    if _MANUSCRIPT_REFERENCE.search(_INLINE_CODE.sub(_without_technical_names, prose)):
        raise ValueError(f'{field} must state the detail directly without a manuscript reference')


def validate_korean_review(review, candidate):
    """Check Korean prose and literal grounding without grading factual support."""
    if not isinstance(candidate, str):
        raise ValueError('Korean review requires the exact candidate text')
    if not isinstance(review, dict) or not isinstance(review.get('claims'), list):
        raise ValueError('Korean review requires a claims list')
    fields = []
    for index, claim in enumerate(review['claims'], start=1):
        if not isinstance(claim, dict):
            raise ValueError(f'Claim {index} must be an object')
        for name in ('claim', 'correction', 'consequence'):
            text = claim.get(name)
            if name != 'claim' and text is None:
                continue
            verbatim = name == 'claim' and claim.get('assessment') in _VERBATIM_ASSESSMENTS
            field = f'Claim {index} {name}'
            prose = _check_prose(text, candidate, field, verbatim=verbatim)
            fields.append((prose, field, verbatim))

    # Preserve language diagnostics across the review before checking grounding.
    for prose, field, verbatim in fields:
        _check_grounding(prose, candidate, field, verbatim=verbatim)
