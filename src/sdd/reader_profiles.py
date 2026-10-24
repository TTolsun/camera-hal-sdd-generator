"""Portable, evidence-bound minimums for the two SDD reader roles."""

import re


PROFILES = {
    'vendor': {
        'inputs': '입력 조건과 구현 책임은 무엇입니까?',
        'ownership': '요청과 버퍼를 누가 유지하고 반환합니까?',
        'completion': '제출과 완료, 정지를 어떻게 구분합니까?',
        'failure': '실패를 어떻게 구분하고 처리합니까?',
        'verification': '어떤 조건을 실행에서 확인해야 합니까?',
    },
    'architecture': {
        'responsibility': '컴포넌트의 책임은 어떻게 나뉩니까?',
        'boundaries': '제어와 데이터는 어떤 경계를 통과합니까?',
        'lifecycle': '상태와 자원 수명은 어떻게 변합니까?',
        'concurrency': '스레드와 동기화 책임은 어디에 있습니까?',
        'verification': '정적 근거의 한계와 실행 확인 대상은 무엇입니까?',
    },
}


def profile_errors(section):
    profile = section.get('reader_profile')
    if profile is None:
        return []
    if not isinstance(profile, str) or profile not in PROFILES:
        return ['reader_profile은 vendor 또는 architecture여야 합니다.']
    requirements = section.get('design_requirements', [])
    found = set()
    for requirement in requirements:
        aspects = requirement.get('aspects', [])
        if not isinstance(aspects, list) or any(not isinstance(a, str) or a not in PROFILES[profile] for a in aspects):
            return [f'{profile}: aspects에는 프로필의 확인 항목을 지정해야 합니다.']
        found.update(aspects)
    errors = [f'{profile}/{key}: 필수 독자 질문이 없습니다. {question}'
              for key, question in PROFILES[profile].items() if key not in found]
    for topic in section.get('design_topics', []):
        for statement in topic.get('statements', []):
            text = statement.get('text', '')
            if isinstance(text, str) and _dense_paragraph(text):
                errors.append(f"{topic['id']}: 설명 문단은 600자·4문장 이내로 나누세요. 조건과 예외는 유지하세요.")
    return errors


def _dense_paragraph(text: str) -> bool:
    # A mechanical wall-of-text guard, not a comprehension or medical test.
    text = re.sub(r'(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$', '', text)
    for paragraph in re.split(r'\n\s*\n', text):
        lines = paragraph.strip().splitlines()
        if lines and all(re.match(r'^\s*(?:\||[-*+] |\d+\. |#)', line) for line in lines):
            continue  # Tables, individual steps and headings are structured content.
        prose = re.sub(r'`[^`]*`|\[[^]]*\]\([^)]*\)', ' ', paragraph)
        if len(prose.strip()) > 600 or len(re.findall(r'[.!?](?=\s|$)', prose)) > 4:
            return True
    return False
