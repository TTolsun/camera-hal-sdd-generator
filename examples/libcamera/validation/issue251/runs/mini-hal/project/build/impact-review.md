# 변경 문서 범위 검토

비교 범위: `16f6cb06d425cf390706a9c6b918fce003bcf44e..0c92b75dd1f9fc2ac97d2ef08e246bc081faaf48`

상태: **needs-review** · 검토 항목 1개

이 결과는 설정상 문서 범위 검사입니다. 문서의 존재·최신성·설명 정확성이나 사람의 승인을 보장하지 않습니다.

## 검토할 변경

- `src/device/RequestManager.cpp`: 추출한 클래스·함수와 연결되지 않아 범위를 확인할 수 없습니다. (미결)
  근거 파일: `src/device/RequestManager.cpp`.
  장부 키: `no-extracted-entity:file:src/device/RequestManager.cpp` (승인: `sdd accept --finding "no-extracted-entity:file:src/device/RequestManager.cpp"`)

## 파일 감시와 수동 검토 연결

- `src/device/RequestManager.cpp`: needs-review; watch=completion-demo; 수동 검토=(없음)

## 검사 한계

- 변경 파일 안의 선언·정의 위치를 사용합니다. 줄별 변경이나 LLM 입력 예산에 따른 생략은 별도 검증이 필요합니다.
- watch 일치만으로 누락이 해결되지는 않습니다. facts.classes/functions 범위를 보완하거나 검토자가 범위 밖 변경인지 판단해야 합니다.
- 효과가 분석한 빌드 밖에도 미치는 빌드 파일, 그리고 빌드에서 읽었지만 클래스·함수가 추출되지 않은 코드는 검토 대상으로 남습니다. 분석한 빌드가 읽지 않은 C/C++ 파일과, 설계 근거가 파일 전체를 현재 해시로 고정한 파일은 자동 분류합니다. 수동 문서의 근거 연결은 검토 위치만 안내합니다.
- 이전 facts가 없어 삭제된 심볼을 완전히 검사하지 못했습니다. --base-facts로 비교 기준의 facts를 제공하세요.
