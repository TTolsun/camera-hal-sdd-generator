"""Reader-facing contract views; validation never depends on this module."""
import re
import hashlib
from .design_contracts import enforce
from .facts.model import KnowledgeModel
from .markdown_text import slugify

def coverage_table(model: KnowledgeModel, section: dict) -> str:
    report = enforce(model, section)
    topics = {t["id"]: t for t in section["design_topics"]}
    rows = ["질문별 답변과 근거 연결을 검사했습니다. 의미와 실행 결과는 사람 검토가 필요합니다.", "",
            "| 설계 질문 | 설명 위치 | 확인 범위 |", "|---|---|---|"]
    for item in report["requirements"]:
        links = ", ".join(f"[{topics[t]['title']}](#{slugify(topics[t]['title'])})" for t in item["topics"])
        label = "코드 근거와 설명 연결" + (" · 실행 확인 항목 별도" if item["limitations"] else "")
        rows.append(f"| {item['question'].replace('|', '&#124;')} | {links} | {label} |")
    return '??? note "설계 질문과 검증 범위"\n' + '\n'.join('    ' + line for line in rows)


class SourceDetails:
    """One original excerpt per page; topics link to that shared evidence."""
    def __init__(self):
        self.records = {}

    def links(self, model, section, topic):
        links = []
        for source in topic.get('sources', []):
            record = model.evidence.get(f"{section}/{topic['id']}/{source['id']}", {})
            if record.get('status') != 'available' or not record.get('text'):
                continue
            key = f"{record['file']}:{record['line']}:{record['sha256']}"
            anchor = 'source-' + hashlib.sha256(key.encode()).hexdigest()[:16]
            self.records.setdefault(anchor, (source, record))
            label = f"{record['file']}:{record['line']}"
            links.append(f'[{label}](#{anchor})')
        return '근거 원문: ' + ' · '.join(dict.fromkeys(links)) if links else ''

    def render(self):
        if not self.records:
            return ''
        parts = ['## 소스 근거', '같은 발췌는 한 번만 싣습니다. 필요한 원문을 펼쳐 설명과 대조하세요.']
        for anchor, (source, record) in self.records.items():
            title = f"{record['file']}:{record['line']}"
            parts.append(f'<a id="{anchor}"></a>\n\n' + _source_detail(record, title))
        return '\n\n'.join(parts)


def source_details(model: KnowledgeModel, section: str, topic: dict) -> str:
    """Keep the original excerpt inspectable without mixing it with interpretation."""
    parts = []
    for source in topic.get("sources", []):
        record = model.evidence.get(f"{section}/{topic['id']}/{source['id']}", {})
        if record.get("status") != "available" or not record.get("text"):
            continue
        parts.append(_source_detail(record, str(source['id'])))
    return "\n\n".join(parts)


def _source_detail(record: dict, title: str) -> str:
    raw = record["text"]
    fence = "`" * max(3, 1 + max((len(m[0]) for m in re.finditer(r"`+", raw)), default=0))
    title = title.replace('"', "'").replace("\n", " ")
    body = (f"`{record['file']}:{record['line']}`에서 시작하는 발췌입니다. "
            f"종료 줄은 {record['end_line']}이며, 아래 원문을 설명과 대조할 수 있습니다.\n\n"
            f"SHA-256: `{record['sha256']}`\n\n{fence}text\n{raw}\n{fence}")
    return f'??? note "소스 근거: {title}"\n' + "\n".join("    " + line for line in body.splitlines())
