"""Apply independent accuracy findings to questions, never hand-edit generated prose."""
from pathlib import Path
from copy import deepcopy
import json
import re
import yaml

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
RUN = ROOT/'build/issue252/run'


class NoAliases(yaml.SafeDumper):
    def ignore_aliases(self,data):
        return True


def replace_topic(text,topic):
    import re
    start = text.index('  - id: '+topic['id']+'\n',text.index('- id: request-lifecycle\n'))
    following = re.search(r'^  (?:- id: |design_requirements:)',text[start+1:],re.M)
    assert following
    end = start+1+following.start()
    rendered = yaml.dump([topic],Dumper=NoAliases,allow_unicode=True,sort_keys=False,width=105)
    return text[:start]+''.join(('  '+line).rstrip()+'\n' for line in rendered.splitlines())+text[end:]


def main():
    review = json.loads((RUN/'audits/accuracy-01/review.json').read_bytes())
    assert review['status']=='needs-work'
    config = RUN/'config/sections.yaml'
    data = yaml.safe_load(config.read_bytes())
    section = next(s for s in data['sections'] if s['id']=='request-lifecycle')
    amendments = {t['id']:deepcopy(t) for t in yaml.safe_load((HERE/'topics.yaml').read_bytes())['topics']
                  if t['id'] in ['callback-depth','callback-order','preparation-depth','uvc-depth','stop-depth']}
    callback = amendments['callback-depth']
    section['design_topics'] = [amendments.get(t['id'],t) for t in section['design_topics']]
    topics = {t['id']:t for t in section['design_topics']}
    journey = topics['journey']
    rejection = next(p for p in journey['parts'] if p['id']=='buffer')
    rejection['question'] = 'Request::addBuffer가 버퍼를 Stream과 연결하는 동작과 API의 -EINVAL·-EEXIST 반환 계약을 설명하세요. 구현이 확인한 -EINVAL 조건은 stream == nullptr이며 API 설명의 유효한 Stream이라는 표현을 비null 포인터 검증으로 확대하지 마세요. 두 문장 이내로 답하세요.'
    rejection['question'] += ' API 반환 계약의 유효한 Stream과 구현의 null 포인터 검사를 구분하세요. 구현이 임의의 유효하지 않은 비null Stream 포인터를 검증한다고 확대하지 마세요.' if '비null' not in rejection['question'] else ''
    implementation = dict(id='buffer-implementation',file='src/libcamera/request.cpp',start='int Request::addBuffer(const Stream *stream, FrameBuffer *buffer,',end='\n}')
    if not any(x['id']=='buffer-implementation' for x in journey['sources']):
        journey['sources'].append(implementation)
    rejection['sources']=['buffer','buffer-implementation']
    for rule in rejection.get('answer_contract',{}).get('reject_patterns',[]):
        if 'nullptr|' in rule['pattern']:
            rule['pattern']=rule['pattern'].replace('nullptr|','')
            rule['message']='오류 조건과 null stream 검사를 설명하고 스트림당 하나 일반론을 별도로 반복하지 마세요.'
    amendments['journey'] = journey
    target = topics['review']
    plan = yaml.safe_load((HERE/'verification-parts.yaml').read_bytes())
    target['question'] = plan['question']
    aliases = {
        'frame-status-contract':('uvc-depth','frame-validity'),
        'message-post':('preparation-depth','post-order'),
        'poll-events':('preparation-depth','poll-dispatch'),
        'timer-lifetime':('preparation-depth','timer-lifetime'),
        'prepare-flow':('preparation-depth','prepare'),'dispatch-flow':('preparation-depth','dispatch'),
        'completion-flow':('uvc-depth','complete'),'uvc-submit':('uvc-depth','submit'),
        'uvc-controls':('uvc-depth','controls'),'control-result':('uvc-depth','set-controls'),
        'qbuf-flow':('uvc-depth','qbuf'),'dequeue-flow':('uvc-depth','dequeue'),'uvc-ready':('uvc-depth','uvc-ready'),
        'common-stop':('stop-depth','common-stop'),'streamoff-flow':('stop-depth','streamoff'),
        'uvc-stop':('stop-depth','uvc-stop'),'release-buffers':('stop-depth','release'),
        'connection-rules':('callback-depth','connections'),'signal-lifetime':('callback-depth','signals'),
        'thread-contract':('callback-depth','thread-rules'),'owner-duty':('callback-order','lifetime'),
        'cancellation-flow':('preparation-depth','cancel'),
        'buffer-request':('callback-order','buffer-request'),'camera-notice':('preparation-depth','camera-notice'),'submit-message':('preparation-depth','submit-message'),'stop-entry':('preparation-depth','stop-entry'),
    }
    old_ids = {s['id'] for s in target['sources']}
    for alias,(tid,sid) in aliases.items():
        if alias not in old_ids:
            target['sources'].append(dict(deepcopy(next(s for s in topics[tid]['sources'] if s['id']==sid)),id=alias))
    if 'request-invariant' not in old_ids:
        target['sources'].append(dict(id='request-invariant',file='src/libcamera/request.cpp',
            start='\\brief Complete a buffer for the request',end='void Request::Private::doCancelRequest()'))
    if 'request-identity' not in old_ids:
        target['sources'].append(dict(id='request-identity',file='src/libcamera/request.cpp',
            start='std::string Request::toString() const',end='} /* namespace libcamera */'))
    revised={p['id']:p for p in plan['parts']}
    target['parts']=[deepcopy(revised.get(p['id'],p)) for p in target['parts']]
    old_parts = {p['id'] for p in target['parts']}
    target['parts'].extend(p for p in plan['parts'] if p['id'] not in old_parts)
    for part in target['parts']:
        if part['id'] in ['completion-invariants','delivery-case'] and 'request-identity' not in part['sources']:
            part['sources'].append('request-identity')
        if part['id'] in ['frame-error-case','stop-case','delivery-case']:
            part['answer_contract'] = dict(basis='investigation')
            part['prompt'] = '검증 계획을 완전한 평서문으로 설명하세요. ~인지, ~되는지 같은 명사절을 쉼표로 나열하지 말고 기록할 값·횟수·순서·수명과 기대 분기를 직접 연결하세요. 시험 완료를 주장하지 마세요.'
    config.write_text(yaml.safe_dump(data,allow_unicode=True,sort_keys=False),encoding='utf-8')
    main = ROOT/'examples/libcamera/config/sections.yaml'
    text = replace_topic(main.read_text(encoding='utf-8'),target)
    for topic in amendments.values():
        text=replace_topic(text,topic)
    main.write_text(text,encoding='utf-8',newline='\n')
    for path in [RUN/'config/visuals.yaml',ROOT/'examples/libcamera/config/visuals.yaml']:
        text = path.read_text(encoding='utf-8')
        text = text.replace('(구현 미검토, 측정 결과 아님)','(선택한 UVC 구현은 별도 정적 분석, 측정 결과 아님)')
        text = text.replace('(implementation not reviewed, not a measured result)',
                            '(selected UVC implementation statically analysed separately; not a measured result)')
        text = re.sub(r'implementation\s+not reviewed, not a measured result',
                      'selected UVC implementation statically analysed separately; not a measured result',text)
        visuals = yaml.safe_load(text)
        callback = next(v for v in visuals['sections']['request-lifecycle'] if v['id']=='callback-order-flow')
        callback.update(question='상태 검사를 통과하는 정상 완료에서 PipelineHandler::completeBuffer 진입, bufferCompleted 신호, Request::Private::completeBuffer와 pending 제거, 명시적 요청 완료와 선두 검사 뒤 통지 순서를 구분하세요.',
            prompt='호출 중인 PipelineHandler::completeBuffer와 나중에 호출하는 Request::Private::completeBuffer를 별도 노드로 그리고 레이블에 한정된 이름을 표시하세요. 두 노드의 소스 심볼은 completeBuffer로 같아도 되며 고유 id를 사용하세요. Request 상태 갱신 뒤 선두를 검사하고 Pending이면 멈추며, 그렇지 않을 때에만 pop_front 후 camera에 알립니다. 연결 해제 시 무조건 완료 가능하다는 레이블은 넣지 마세요. 이 그림은 Camera::requestComplete 상태 검사를 통과한 선택 UVC 경로입니다. Private completeBuffer에서 요청 완료로 병렬 분기하지 마세요. PH completeBuffer 진입→bufferCompleted→Private completeBuffer→pending 제거·연결 해제→PH completeBuffer 반환→UVC 명시적 completeRequest→complete→선두 상태 검사→pop→통지 순서입니다. completeBuffer 반환 노드도 별도로 그리고 pending 제거 뒤에만 연결하세요.',
            sources=['completion','status','notification','uvc-return'],whole_sources=['completion','status','notification','uvc-return'],
            required_symbols=['completeBuffer','bufferCompleted','pending_','complete','RequestPending','pop_front','requestComplete','requestCompleted'],max_nodes=11)
        if not any(v['id']=='change-verification-flow' for v in visuals['sections']['request-lifecycle']):
            visuals['sections']['request-lifecycle'].append(dict(id='change-verification-flow',topic='review',kind='flow',
                title='정상 완료와 bulk 취소의 검증 위치',generation='llm',max_nodes=9,
                question='정상 버퍼 완료와 bulk 취소에서 서로 다른 pending_ 정리 및 요청 완료의 검증 위치는 어디입니까?',
                prompt='실행 순서 전체가 아닌 소스 기반 검증 위치 그림입니다. 정상 Request::Private::completeBuffer의 erase와 doCancelRequest의 직접 버퍼 신호·pending clear를 구분하세요. complete()의 pending 부재 ASSERT도 별도 검사 위치로 표시하세요. pending을 비웠다고 요청을 자동 완료하는 화살표를 만들지 마세요. 필요하면 독립된 작은 경로로 배치하고 본문 시험 계획을 실행 결과로 표시하지 마세요.',
                sources=['request-invariant','cancellation-flow','completion-flow'],
                whole_sources=['request-invariant','cancellation-flow','completion-flow'],
                required_symbols=['completeBuffer','doCancelRequest','pending_','complete','hasPendingBuffers']))
        if not any(v['id']=='queued-lifetime-flow' for v in visuals['sections']['request-lifecycle']):
            visuals['sections']['request-lifecycle'].append(dict(id='queued-lifetime-flow',topic='callback-depth',kind='ownership',generation='llm',max_nodes=9,
                title='Queued 수신과 해제 시점의 책임',question='Signal 발신자의 포인터 수명 책임과 요청 소유자의 마지막 수신 사용 확인은 어떻게 연결됩니까?',
                prompt='다른 스레드의 Object 슬롯으로 전달하는 범위입니다. Signal 발신자의 신호 발생 이후 포인터·참조 유효성 책임과 기존 요청 완료 콜백까지 버퍼 유지 계약을 구분하세요. 별도 Queued 수신자의 마지막 사용을 추적·동기화한 뒤 삭제·재사용을 결정하는 부분은 검증 계획으로 레이블에 명시하세요. 자동 잠금·참조 소유·수신 완료 대기나 stop 반환으로 모든 수신자가 끝났다는 런타임 보장을 만들지 마세요. 이미 자원 절에서 설명한 소유권 전체를 되풀이하지 말고 수명 협의 경계를 작은 그림으로 보여 주세요.',
                sources=['signals','buffer-duty','invocation','notification'],whole_sources=['signals','buffer-duty','invocation','notification'],required_symbols=['Signal','Object','Request']))
        lifetime = next(v for v in visuals['sections']['request-lifecycle'] if v['id']=='queued-lifetime-flow')
        lifetime['sources']=['signals','buffer-duty','invocation','notification','signal-overloads','connections','thread-post','thread-dispatch','object-message','invoke-message']
        lifetime['whole_sources']=list(lifetime['sources'])
        lifetime['prompt']='다른 스레드의 Object 슬롯으로 전달하는 범위입니다. Signal 발신자의 신호 발생 이후 포인터·참조 유효성 책임과 기존 요청 완료 콜백까지 버퍼 유지 계약을 구분하세요. 별도 Queued 수신자의 마지막 사용을 추적·동기화한 뒤 삭제·재사용을 결정하는 부분은 검증 계획으로 레이블에 명시하세요. 자동 잠금·참조 소유·수신 완료 대기나 stop 반환으로 모든 수신자가 끝났다는 런타임 보장을 만들지 마세요. 이미 자원 절에서 설명한 소유권 전체를 되풀이하지 말고 수명 협의 경계를 작은 그림으로 보여 주세요. 그림 범위는 Auto의 타스레드 Queued 선택 또는 명시적 Queued입니다. Signal 주석의 emit 반환 뒤라는 문구를 실제 구현의 선후 보장으로 쓰지 마세요. Queued postMessage는 기다리지 않고, 타스레드의 수신 처리는 emit 반환 전에 시작될 수도 있습니다. 반환과 수신 실행을 직렬로 연결하지 말고 순서 미보장·수명 협의의 검증 조건으로 표현하세요. 명시적 Direct를 비동기로 일반화하지 마세요.'
        queued = next(v for v in visuals['sections']['request-lifecycle'] if v['id']=='callback-depth-flow')
        queued['prompt']='Auto의 실제 비교, Direct의 invokePack, Queued의 postMessage와 비동기 false 반환을 보여주세요. Queued 경로는 postMessage·false 반환에서 끝내고 수신자 실행 노드를 그리지 마세요. 이벤트 루프 복귀만으로 반드시 실행된다는 보장을 넣지 마세요. 수신 객체 유효성과 실제 메시지 처리 조건은 본문에서 설명합니다.'
        whole = {
            'preparation-depth-flow':['dispatch','prepare','completion'],
            'uvc-depth-flow':['submit','dispatch','complete','uvc-ready','dequeue','uvc-wiring'],
            'stop-depth-flow':['common-stop','uvc-stop','streamoff','release','dequeue'],
            'callback-depth-flow':['connections'],
        }
        for visual in visuals['sections']['request-lifecycle']:
            if visual['id'] in whole:
                visual['sources']=list(whole[visual['id']])
                visual['whole_sources']=list(whole[visual['id']])
        changes=yaml.safe_load((HERE/'visual-amendments.yaml').read_bytes())
        additions={visual['id']:visual for visual in changes['additions']}
        for visual in visuals['sections']['request-lifecycle']:
            visual.update(deepcopy(changes['overrides'].get(visual['id'],{})))
            visual.update(deepcopy(additions.get(visual['id'],{})))
        existing={visual['id'] for visual in visuals['sections']['request-lifecycle']}
        visuals['sections']['request-lifecycle'].extend(deepcopy(visual) for visual in changes['additions'] if visual['id'] not in existing)
        # Persist only the new automatic plan block in the main example.
        # No unrelated unpublished request-diagnosis diagrams are introduced.
        baseline = yaml.safe_load((RUN.parent/'public/publication/issue214/config/visuals.yaml').read_bytes())
        if path.parent==RUN/'config':
            if not (RUN/'public-base-integration.json').exists():
                visuals['sections']['request-diagnosis'] = baseline['sections']['request-diagnosis']
            path.write_text(yaml.safe_dump(visuals,allow_unicode=True,sort_keys=False),encoding='utf-8')
        else:
            # The main example retains its existing diagnosis plans and formatting.
            start,end = text.index('  - id: preparation-depth-flow\n'),text.index('  overview:\n')
            plans=[v for v in visuals['sections']['request-lifecycle']
                   if v.get('topic')=='resources' or (v.get('generation')=='llm'
                       and v['topic'] in ['preparation-depth','uvc-depth','stop-depth','callback-order','callback-depth','review'])]
            rendered = yaml.dump(plans,Dumper=NoAliases,allow_unicode=True,sort_keys=False,width=105)
            path.write_text(text[:start]+''.join(('  '+line).rstrip()+'\n' for line in rendered.splitlines())+text[end:],encoding='utf-8',newline='\n')
    print('Refined source-bound questions, verification cases and diagram order; regeneration required.',flush=True)


if __name__=='__main__':
    main()
