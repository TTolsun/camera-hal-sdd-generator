import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

root = next(p for p in Path(__file__).resolve().parents if (p/'pyproject.toml').is_file())
record = root / 'docs/libcamera/records/issue253'
work = root / 'build/issue253'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
manifest = json.loads((work/'public/docs/site-manifest.json').read_text(encoding='utf-8'))
bad = [p for p, h in manifest['outputs'].items() if sha(work/'public/docs'/p) != h]
assert not bad, bad
source_files = {str(p.relative_to(work/'source')).replace('\\','/'): sha(p)
                for name in ['Documentation', 'include', 'src', 'test']
                for p in (work/'source'/name).rglob('*') if p.is_file()}
tasks = {}
for line in (record/'protocol.md').read_text(encoding='utf-8').splitlines():
    cells = [x.strip() for x in line.split('|')]
    if len(cells)>3 and cells[1] in ['T1','T2','T3','T4','T5','T6','D1','D2']:
        tasks[cells[1]] = cells[2]
assign = {'E01':['T1','T4','D1','D2'], 'E02':['T2','T3','D1','D2'], 'E03':['T5','T6','D1','D2']}
for eid, ids in assign.items():
    orders = ['AB','BA','AB','BA'] if eid != 'E02' else ['BA','AB','BA','AB']
    p = work/'participants'/eid
    p.mkdir(parents=True, exist_ok=True)
    packet = {'evaluator_id': eid, 'kind':'automated_subagent',
      'conditions': {'A':{'root':str(work/'source'), 'start':'Documentation/index.rst',
         'allowed':['Documentation/**','include/**','src/**','test/**']},
       'B':{'root':str(work/'public/docs'), 'start':'index.html',
         'allowed':['*.html','scenarios/*.html','en/*.html','assets/*','*.mmd']}},
      'tasks':[{'id':tid,'prompt':tasks[tid],'order':order} for tid,order in zip(ids,orders)],
      'rules':['정답표·설정·기록·외부 지식·웹·다른 평가 결과를 읽지 마세요.',
       '과업마다 지정된 첫 조건에서 탐색·답 제출을 끝낸 뒤 두 번째 조건을 읽으세요. 다른 조건의 근거를 이 조건의 답에 사용하지 마세요.',
       'B는 HTML의 main 본문·그림 원문·발췌를 읽고 검색할 수 있지만 Markdown frontmatter와 생성 설정은 읽지 마세요.',
       '시작/첫 근거/제출 시각을 도구로 측정하고 600초 제한을 지키세요. 시간을 추정하지 마세요.',
       '답과 경로·검색어·실제 근거 파일/줄·누락·환경 지연·도움 요청을 기록하세요. 실패도 보고하세요.',
       '사람 읽기 부담·사람 검토 시간은 null입니다. 스스로 정답 채점하지 마세요.',
       '입력은 읽기 전용이며 이 참가자 폴더의 results.json에만 결과를 쓰세요.'],
      'result_fields':['evaluator_id','task_id','condition','exposure','started_at','first_evidence_at','ended_at','elapsed_seconds','answer','evidence','visited','queries','help_count','missing','reading_ease_1_to_5','environment_delay_seconds']}
    (p/'packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
with (record/'human-results.csv').open('w',encoding='utf-8',newline='') as f:
    fields=['session_id','participant_id','perspective','task_id','condition','exposure','version','started_at','first_evidence_at','ended_at','elapsed_seconds','answer','evidence','queries','help_count','correct','independent','reading_ease_1_to_5','blocked_reason','reading_experience']
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
    for eid,ids in assign.items():
        for i,tid in enumerate(ids):
            orders=['AB','BA','AB','BA'] if eid!='E02' else ['BA','AB','BA','AB']
            for j,c in enumerate(orders[i]):
                w.writerow({'participant_id':eid.replace('E','P'),'task_id':tid,'condition':c,'exposure':j+1})
lock = {'schema':1,'frozen_at':datetime.now(timezone.utc).isoformat(),
 'generator':'bc58d09a35e2169bc1d23d972721dd97eaa68ebb',
 'source':'293d751a814e0d4c34e85ad457ccd9d5eefd1a61',
 'publication':'178aa978890a22df5e984bc5efe18a1a3756aa1b',
 'build_id':manifest['build_id'], 'manifest_sha256':sha(work/'public/docs/site-manifest.json'),
 'protocol_sha256':sha(record/'protocol.md'),'rubric_sha256':sha(record/'rubric.md'),
 'source_files':source_files,'site_outputs':manifest['outputs'],
 'packets':{eid:sha(work/'participants'/eid/'packet.json') for eid in assign},
 'source_change':{'base':'be909e49b7cfcbf8e888b6a17928ae06fd7f9a96','head':'293d751a814e0d4c34e85ad457ccd9d5eefd1a61'},
 'human_participants':0,'human_trials':0,'effects_status':'pending-human-evaluation'}
(record/'lock.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'frozen_at':lock['frozen_at'],'site_verified':len(manifest['outputs']),'source_files':len(source_files),'packets':lock['packets']}))
