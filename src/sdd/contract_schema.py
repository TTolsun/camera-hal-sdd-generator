"""Validate contract configuration without reading evidence or rendering pages."""
from .reader_profiles import profile_errors

def configuration_errors(section: dict) -> list[str]:
    errors = []
    for field in ('design_requirements', 'design_topics'):
        values = section.get(field, [])
        if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
            return [f'{field}는 객체 목록이어야 합니다.']
        if any(not isinstance(v.get('id'), str) or not v['id'].strip() for v in values):
            return [f'{field}의 id는 비어 있지 않은 문자열이어야 합니다.']
    for topic in section.get('design_topics', []):
        for field in ('sources', 'statements'):
            values = topic.get(field, [])
            if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
                return [f"{topic['id']}/{field}는 객체 목록이어야 합니다."]
        if any(not isinstance(s.get('id'), str) or not s['id'].strip() for s in topic.get('sources', [])):
            return [f"{topic['id']}: 소스 id가 비었거나 문자열이 아닙니다."]
        for source in topic.get('sources', []):
            for field in ('file', 'start', 'end'):
                if not isinstance(source.get(field), str) or not source[field].strip():
                    errors.append(f"{topic['id']}/{source['id']}: {field}는 비어 있지 않은 문자열이어야 합니다.")
        for st in topic.get('statements', []):
            for field in ('covers', 'evidence'):
                values = st.get(field, [])
                if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
                    errors.append(f"{topic['id']}/{field}는 문자열 목록이어야 합니다.")
    return errors + profile_errors(section) + generated_errors(section)


def generated_errors(section):
    if section.get('design_generation') not in (None, 'llm'):
        return ['design_generation은 llm이어야 합니다.']
    if section.get('design_generation') != 'llm':
        return []
    errors = []
    requirements = section.get('design_requirements', [])
    topics = section.get('design_topics', [])
    if section.get('kind', 'prose') != 'prose' or not requirements or not topics:
        errors.append('LLM 설계 생성에는 prose, design_requirements와 design_topics가 필요합니다.')
    ids = [r['id'] for r in requirements]
    covered = []
    for topic in topics:
        covers = topic.get('covers')
        if not isinstance(covers, list) or not covers or any(not isinstance(c, str) for c in covers):
            errors.append(f"{topic['id']}: covers는 비어 있지 않은 문자열 목록이어야 합니다.")
        else:
            covered.extend(covers)
        if 'statements' in topic:
            errors.append(f"{topic['id']}: LLM 모드에서는 statements를 미리 작성할 수 없습니다.")
        if any('sha256' in source for source in topic.get('sources', [])):
            errors.append(f"{topic['id']}: LLM 모드의 근거 해시는 현재 커밋에서 수집합니다.")
    if sorted(covered) != sorted(ids) or len(ids) != len(set(ids)):
        errors.append('각 필수 질문은 정확히 한 주제의 covers에 연결해야 합니다.')
    return errors


