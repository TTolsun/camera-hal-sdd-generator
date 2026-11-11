"""Keep full validation questions; display concise reader navigation labels."""
import hashlib
import json
from pathlib import Path
import re
import yaml
from sdd.config import load
from sdd.document_metadata import split_frontmatter
from sdd.facts.model import KnowledgeModel
from sdd.site_markdown import _render

ROOT=Path(__file__).resolve().parents[4]
RUN=ROOT/'build/issue252/run'
LABELS={
    'journey':'요청 제출 0 이후 어느 단계에서 대기하며 누가 완료를 알립니까?',
    'preparation-depth':'제출 메시지·준비 대기·장치 한도·정지 교차를 어떤 순서로 좁힙니까?',
    'uvc-depth':'UVC 제출·DQBUF 오류는 어디에서 취소나 프레임 상태로 이어집니까?',
    'resources':'요청·버퍼·fence를 누가 언제까지 유지하고 재사용합니까?',
    'callback-order':'버퍼 신호와 내부 정리·요청 반환 사이에서 언제 재사용할 수 있습니까?',
    'callback-depth':'연결 방식별 실행 스레드와 지연 포인터의 마지막 사용을 어떻게 확인합니까?',
    'stopping':'정지의 대기 분리·장치 취소·반환 순서는 무엇입니까?',
    'stop-depth':'STREAMOFF 실패 뒤 어떤 상태가 남으며 후속 알림을 어떻게 조사합니까?',
    'review':'변경 뒤 어떤 불변조건과 실패 분기를 다시 검증해야 합니까?',
    'observed-callbacks':'보존한 가상 프로브의 관측과 미검증 범위는 무엇입니까?',
}


def main():
    cfg=load(RUN/'publication.yaml')
    section=next(s for s in cfg.sections() if s['id']=='request-lifecycle')
    path=cfg.sdd_dir/'request-lifecycle.md'
    _,body=split_frontmatter(path.read_text(encoding='utf-8'))
    model=KnowledgeModel.load(cfg.facts_path)
    document=_render(body,'request-lifecycle.md',{'request-lifecycle.md'},model,'',model.meta['source_commit'])[0]
    listing=re.search(r'<ul class="coverage-links">(.*?)</ul>',document,re.S)
    assert listing
    questions=re.findall(r'<li><p>(.*?)</p><p>',listing[1],re.S)
    requirements=section['design_requirements']
    assert len(questions)==len(requirements)==len(LABELS)
    edits={}
    rows=[]
    for requirement,original in zip(requirements,questions):
        label=LABELS[requirement['id']]
        fingerprint=hashlib.sha256(original.encode()).hexdigest()
        assert fingerprint not in edits
        edits[fingerprint]=dict(label=label)
        rows.append(dict(id=requirement['id'],original_html=original,sha256=fingerprint,label=label))
    # The production formatter validates all fingerprints before rendering.
    _render(body,'request-lifecycle.md',{'request-lifecycle.md'},model,'',model.meta['source_commit'],coverage_question_edits=edits)
    for name in ['publication.yaml','contract-review.yaml']:
        profile=RUN/name
        data=yaml.safe_load(profile.read_bytes())
        data['site'].setdefault('coverage_question_edits',{})['request-lifecycle.md']=edits
        profile.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8',newline='\n')
    (RUN/'reader-question-labels.json').write_text(json.dumps(dict(manuscript_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        full_validation_questions_preserved=True,rows=rows),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Ten reader labels bound to unchanged full validation questions.',flush=True)


if __name__=='__main__':main()
