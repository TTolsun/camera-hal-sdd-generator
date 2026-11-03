"""Seed source-bound example plans from unresolved independent item reviews.

Produces questions and source selectors, never nodes, arrows or acceptance.
Existing visual revisions and non-topic questions remain explicitly pending.
"""
import argparse
import json
from pathlib import Path
import yaml

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report', type=Path, required=True)
parser.add_argument('--sections', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
report = json.loads(args.report.read_bytes())
sections = yaml.safe_load(args.sections.read_bytes())['sections']
pages = {s.get('output', s['id']+'.md').removesuffix('.md')+'.html':s for s in sections}
plans, pending = {}, []
for row in report['items']:
    if row['language'] != 'ko' or row['status'] != 'needs_visual':
        continue
    section = pages.get(row['page'], {})
    topic = next((t for t in section.get('design_topics', []) if t['title'] == row['title']), None)
    if not topic or row.get('role') == 'visual_title':
        pending.append(dict(id=row['id'], reason='Existing visual revision, structural placement or non-topic question; inspect individually'))
        continue
    if (section['id'], topic['id']) in {('onboarding','why'), ('pipeline-handler','shutdown')}:
        pending.append(dict(id=row['id'], reason='Already handled by separate isolated draft/review runs; integration remains pending'))
        continue
    question = row.get('proposed_question') or row['question']
    signals = row.get('complexity_signals', [])
    kind = 'ownership' if 'ownership' in signals else ('decision' if 'branch' in signals else 'flow')
    plans.setdefault(section['id'], []).append(dict(
        id='item-'+topic['id'], topic=topic['id'], kind=kind,
        title=topic['title']+'의 관계와 경계', question=question, generation='llm',
        max_nodes=12, max_label_chars=160, max_edge_label_chars=96,
        while_conditions=True, condition_display='evidence', require_connected=True,
        answer_contract_en=dict(basis='description', reject_patterns=[
            dict(pattern=r'[\x00-\x08\x0b\x0c\x0e-\x1f가-힣]', message='English labels must not contain control characters or untranslated Korean.'),
            dict(pattern=r'(?m)^[^\n]*[^\s.!?\]][ \t\u00a0]*$', message='English labels must be complete short sentences; source guard suffixes are retained separately.')]),
        sources=[s['id'] for s in topic['sources']],
        prompt=('독립 항목 조사에서 다음 미충족 관계를 찾았습니다: '+row['reason']+' '
            '이 질문에만 답하는 그림을 만드세요. 다른 질문의 일반 구조도를 반복하거나 소스에 없는 실행·인과 관계를 만들지 마세요. '
            '구조와 책임은 구성 관계로, 순서는 순서도로, 상태·실패는 결정과 양쪽 결과로, 소유권은 보유·반환 관계로 표현합니다. '
            '실제 if/while의 참·거짓 양쪽과 종료를 보존하되 전체 함수가 아닌 일부 계약 관계이면 그 범위를 라벨에서 밝힙니다. '
            '각 화살표가 인용한 구절 묶음에는 양 끝 symbol이 실제로 존재해야 합니다. 필요한 근거가 없으면 새 사실을 지어내지 마세요. '
            '한영 모두 같은 조건·부정·반환 경계를 보존하며, 영문 노드는 90자 이내, 영문 화살표는 70자 이내의 완전한 짧은 문장으로 '
            '직접 요약하세요. 상한에 맞추려고 문장 끝을 자르거나 제어 문자를 넣지 마세요. 복잡한 단일 질문이 12개 노드에 안 맞으면 '
            '조건을 생략해 통과시키지 말고 실패 원인을 남겨 질문 분할과 소스 창을 다시 검토하게 하세요.')))
args.out.mkdir(parents=True, exist_ok=False)
for section, values in plans.items():
    (args.out/(section+'.yaml')).write_text(yaml.safe_dump({section:values},allow_unicode=True,sort_keys=False),encoding='utf-8')
(args.out/'pending.json').write_text(json.dumps(pending,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(sections=len(plans),candidate_plans=sum(map(len,plans.values())),pending=len(pending))))
