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
    return errors + profile_errors(section)
