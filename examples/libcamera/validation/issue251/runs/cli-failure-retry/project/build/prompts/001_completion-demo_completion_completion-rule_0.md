<!-- system -->
제공된 소스만 사용하여 한국어 기술 문서를 작성합니다. 질문의 각 조건에 답하세요. 원문에 없는 보장이나 이유를 추가하지 마세요. 의무(must/shall), 가능성(may), 부정을 그대로 유지하세요.

<!-- user -->
근거:
{"on-frame": [{"text": "void RequestManager::onFrame(Frame &frame) {\n    FrameFactory &factory = frame.isPreview ? static_cast<FrameFactory &>(previewFactory_)\n                                            : static_cast<FrameFactory &>(captureFactory_);\n    int ret = factory.runPipes(frame);\n    if (ret >= 0) {\n        sendResult(frame);\n    }\n    onFrameDone(frame);\n}\n\nvoid RequestManager::sendResult", "quote_id": "on-frame:0"}]}
질문: RequestManager::onFrame에서 runPipes 반환값에 따른 sendResult 조건과 onFrameDone 호출을 설명하세요. if 블록 안팎을 구분하고 실패 시 정리도 설명하세요. 실행 스레드나 성공 보장을 추정하지 마세요. 답변은 세 문장 이내로 작성하세요. runPipes와 sendResult의 현재 조건, 음수 반환 때의 호출 여부, if 블록 밖 onFrameDone의 무조건 호출을 각각 명시하세요. 전체 오류 처리가 미정이라고 추정하지 마세요. 현재 반환 조건을 다시 대조하세요.
작성 조건: {"_max_statements": 1, "answer_contract": {"basis": "implementation", "required_terms": [["runPipes"], ["sendResult"], ["onFrameDone"]]}}
문장은 합니다·입니다 형태로 끝내세요. 한 문단은 600자·4문장 이내로 쓰고, 필수 용어의 각 묶음에서 하나 이상을 원래 표기대로 포함하세요. 질문 밖의 함수 내부나 추가 조사 과제를 덧붙이지 마세요. 질문에서 요구한 사항을 확인할 수 없을 때만 확인되지 않은 대상을 짧게 밝히세요. 제공된 코드·제공된 근거 같은 작성 과정 표현은 쓰지 말고, 같은 내용을 바꿔 말하지 마세요.
출력: {"statements": [{"text": "질문의 모든 조건에 답하는 한 문단. 여러 문장을 써도 됩니다.", "quote_id": "직접 근거의 구절 ID", "covers": ["completion-rule"], "kind": "behavior"}]} 형식의 JSON만 반환하세요.
