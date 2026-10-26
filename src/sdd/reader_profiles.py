"""Portable, evidence-bound minimums for SDD readers, including the legacy architecture profile."""

import re


PROFILES = {
    'vendor': {
        'inputs': '입력 조건과 구현 책임은 무엇입니까?',
        'ownership': '요청과 버퍼를 누가 유지하고 반환합니까?',
        'completion': '제출과 완료, 정지를 어떻게 구분합니까?',
        'failure': '실패를 어떻게 구분하고 처리합니까?',
        'verification': '어떤 조건을 실행에서 확인해야 합니까?',
    },
    'developer': {
        'entry': '처음 읽을 파일과 진입점, 요청을 따라갈 순서는 무엇입니까?',
        'responsibility': '각 컴포넌트는 무엇을 담당합니까?',
        'boundaries': '요청과 결과는 어느 호출·큐·콜백을 통과합니까?',
        'lifecycle': '상태와 자원 수명은 어떻게 변합니까?',
        'concurrency': '호출 스레드와 작업 스레드, 잠금은 어떻게 구분합니까?',
        'verification': '수정·디버깅할 코드와 확인 조건, 정적 근거의 한계는 무엇입니까?',
    },
    'architecture': {
        'responsibility': '컴포넌트의 책임은 어떻게 나뉩니까?',
        'boundaries': '제어와 데이터는 어떤 경계를 통과합니까?',
        'lifecycle': '상태와 자원 수명은 어떻게 변합니까?',
        'concurrency': '스레드와 동기화 책임은 어디에 있습니까?',
        'verification': '정적 근거의 한계와 실행 확인 대상은 무엇입니까?',
    },
}

# Keep implementation contracts useful as detail pages. The entry page must
# additionally answer adoption questions, without repeating them on every page.
PROFILES['vendor-overview'] = {
    'capabilities': '어떤 기능을 제공하며 어디까지 지원합니까?',
    'benefits': '구현 근거로 설명할 수 있는 강점과 그 조건은 무엇입니까?',
}
PROFILES['vendor-assurance'] = {
    'constraints': '지원 전제, 미지원 범위와 별도 검증할 제약은 무엇입니까?',
    'verification': '어떤 근거가 있고 무엇을 아직 검증하지 않았습니까?',
}
# 다른 팀이 이 프로젝트가 하는 일을 이해하기 위한 최소 질문. 전문 용어 없이 역할·입력·출력·경계를 먼저 답합니다.
PROFILES['team'] = {
    'role': '이 프로젝트는 무엇을 하며 누구의 어떤 문제를 풉니까?',
    'inputs': '이 프로젝트는 무엇을 입력으로 받습니까?',
    'outputs': '이 프로젝트는 무엇을 결과로 내놓습니까?',
    'boundaries': '어느 계층·팀과 책임이 나뉩니까?',
}


def profile_errors(section):
    profile = section.get('reader_profile')
    if profile is None:
        return []
    if not isinstance(profile, str) or profile not in PROFILES:
        return ['reader_profile은 ' + ', '.join(PROFILES) + ' 중 하나여야 합니다.']
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
