# 공개 libcamera의 항목별 시각화 완료 확인

2026년 11월 14일에 [이슈 #215](https://github.com/TTolsun/camera-hal-sdd-generator/issues/215)의 완료 조건을 현재 공개 루트 Pages에서 다시 확인했습니다. 항목 820개의 본문·그림·소스 근거 지문이 기존 판정과 일치해 전부 재사용했습니다. 그림이 적절한 항목은 242개, 개별 사유를 기록하고 그림을 생략한 항목은 578개입니다. 보완 필요·근거 부족·미검토 항목은 0개입니다. [공개 시각화 감사](https://ttolsun.github.io/libcamera-sdd/item-visual-audit.json)

## 확인한 빌드와 판정 범위

| 확인 대상 | 값 |
| --- | --- |
| 공식 libcamera HEAD와 공개 루트의 소스 | `da6a6ed33ed0ab305f10b6f8b44736150d39cef4` |
| 생성기 확인 기준과 루트 빌드 | 생성기 main `c67720a888cdd6796595eb11822f4d3f203d9923`에서 검증했습니다. 발행에는 생성기 PR #310의 예제 설정과 렌더러 `13facb30acde25ba0151af1474a4f683dee64b03`을 사용했습니다. [공개 발행 기록](https://github.com/TTolsun/libcamera-sdd/blob/be012aa897dd2562e55c842c996ef41cf45bd1a8/publication/issue297/pages-followup/README.md) |
| 공개 SDD와 Pages | 병합 커밋 `be012aa897dd2562e55c842c996ef41cf45bd1a8`, Pages 실행 `43296145459`. [공개 PR #112](https://github.com/TTolsun/libcamera-sdd/pull/112) · [Pages 실행](https://github.com/TTolsun/libcamera-sdd/actions/runs/43296145459) |
| `build_id` | `48c4f23e4b9c3246b3d365d07ddbf032944450cf5a133e3dcec1824b248055d3` |
| `site-manifest.json` SHA-256 | `c67448d2360d59a6e861c6f80ff62089d9acf8d6b2014e3bdd376e2c682c4055`. 실효 설정과 집필 규칙의 지문도 manifest에서 확인했습니다. [공개 manifest](https://ttolsun.github.io/libcamera-sdd/site-manifest.json) |
| 시각화 판정 장부 SHA-256 | `5db550f1e26ca33261d88cfd4f2fb57e4dc58b43a29155f0753612803ffac667`. 공개 장부를 압축 해제한 바이트의 해시가 manifest의 `inputs.item_visual_reviews`와 일치했습니다. [장부 원본](https://github.com/TTolsun/libcamera-sdd/blob/be012aa897dd2562e55c842c996ef41cf45bd1a8/publication/issue297/pages-followup/visual-review-ledger.json.gz) |

manifest에 있는 한영 HTML 62개를 다시 조사했습니다. Vendor·Developer·시나리오·홈·참조 페이지의 한국어 31개와 영어 31개를 포함합니다. 410쌍에는 독자 항목 510개와 보조 시각화 항목 310개가 있습니다. 장부에는 항목별 URL과 앵커, 본문 분량, 복잡성, 그림 ID, 판정 사유와 확인한 근거 창이 기록되어 있습니다. 820개 모두 미검토 범위 필드가 비어 있고, 새로 검토할 항목과 삭제된 항목은 각각 0개입니다. 별도 경로로 발행한 #252와 ColourTemperature의 검증 결과는 각 작업 기록에 있습니다. [#252 완료 기록](issue252.md) · [ColourTemperature 발행 기록](https://github.com/TTolsun/libcamera-sdd/tree/e01740e41a9329c98da7b238531400bccf9a5467/publication/issue304)

## 완료 조건별 근거

| 완료 조건 | 확인 결과 |
| --- | --- |
| 생성·검토 규칙과 focused 계약 | 생성기 main에 반영된 규칙을 실제 공개 프로필로 준비한 요청 수명 문서의 주제별 생성 프롬프트 10개에서 확인했습니다. focused JSON 계약과 최종 HTML에서 별도로 적용하는 발행 검사를 회귀 시험에서 확인했습니다. [생성기 PR #216](https://github.com/TTolsun/camera-hal-sdd-generator/pull/216) · [시각화 감사 계약](../reference/visual-audit.md) |
| 장문·복잡한 항목의 보완과 생략 사유 | 최초 전체 보완의 전후 판정과 600자·3문단 후보 기준을 실제 한영 항목으로 조정한 근거가 공개되어 있습니다. 이후 #303에서 소스가 바뀌어도 근거가 동일한 820개 판정을 재사용했고, 공개 PR #112는 영향을 받은 20개를 다시 검토했습니다. 이번에는 그 발행본의 820개 판정을 정확히 일치하는 지문으로 재사용했습니다. [최초 전체 보완](https://github.com/TTolsun/libcamera-sdd/tree/efad8548dbf2bdd8427e0e7ac935f2a5878b71fe/publication/issue215) · [기준 조정 사례](https://github.com/TTolsun/libcamera-sdd/blob/efad8548dbf2bdd8427e0e7ac935f2a5878b71fe/publication/issue215/threshold-calibration.json) · [#303](https://github.com/TTolsun/camera-hal-sdd-generator/issues/303) · [공개 PR #112](https://github.com/TTolsun/libcamera-sdd/pull/112) |
| 누락·변경 감지와 발행 실패 처리 | 관련 회귀 295개가 통과했습니다. 새 장문, 짧지만 복잡한 절, 표로 충분한 절, 하위 절 분할, 그림 삭제와 `stale: omit`, 한영 불일치, 근거·노드 한도 실패, 발행 실패 시 직전 산출물 보존을 포함합니다. [발행 검사 PR #294](https://github.com/TTolsun/camera-hal-sdd-generator/pull/294) · [회귀 보완 PR #295](https://github.com/TTolsun/camera-hal-sdd-generator/pull/295) |
| 독립 CLI 검토 기록 | 현재 장부에는 별도 Codex CLI `gpt-6.1-terra` high의 검토 출처를 가진 401개 판정과, 문서 표시 또는 추출 기록을 대조한 작업 에이전트 판정 419개가 있습니다. 이번 확인에서는 기존 판정을 재사용해 추가 CLI 검토 호출은 0회였습니다. 공개 발행 기록의 사람 검토 상태는 대기입니다. [최초 발행 기록과 검토 프로필](https://github.com/TTolsun/libcamera-sdd/tree/efad8548dbf2bdd8427e0e7ac935f2a5878b71fe/publication/issue215) · [현재 장부 원본](https://github.com/TTolsun/libcamera-sdd/blob/be012aa897dd2562e55c842c996ef41cf45bd1a8/publication/issue297/pages-followup/visual-review-ledger.json.gz) |
| 실제 화면과 그림 조작 | Chrome에서 62개 문서를 390px와 1440px로 각각 열었습니다. 124회 모두 가로 넘침이 없었고, 폭별 그림 표시 322건이 모두 렌더링됐습니다. 요청 수명과 정지 시나리오의 그림 여섯 개를 한영·두 화면 폭에서 열어 확대, 노드 검색, Escape, 초점 복귀, 소스 링크를 확인했습니다. 한영·두 화면 폭에서 Mermaid 모듈의 로딩 실패를 재현해 안내문, 원문 표시, `.mmd` 링크를 확인했습니다. [요청 수명](https://ttolsun.github.io/libcamera-sdd/request-lifecycle.html) · [정지 시나리오](https://ttolsun.github.io/libcamera-sdd/scenarios/camera_stop.html) |
| 병합·배포·실제 산출물 | 최초 공개 SDD PR #105와 후속 공개 PR #112의 병합과 Pages 성공을 확인했습니다. 현재 루트의 487개 산출물을 실제 URL에서 받아 manifest의 해시와 모두 대조했습니다. 이번에는 수정할 공개 항목이 0개여서 기존 발행본을 확인하는 것으로 배포 검증을 마쳤습니다. [공개 PR #105](https://github.com/TTolsun/libcamera-sdd/pull/105) · [최초 Pages 실행](https://github.com/TTolsun/libcamera-sdd/actions/runs/43123178634) · [현재 Pages 실행](https://github.com/TTolsun/libcamera-sdd/actions/runs/43296145459) · [공개 루트](https://ttolsun.github.io/libcamera-sdd/) |

GitHub의 #215는 이번 확인을 시작할 때 이미 완료 상태였습니다. 위 결과는 공개 libcamera 문서의 생성·검토·배포에 대한 기록입니다. [이슈 상태](https://github.com/TTolsun/camera-hal-sdd-generator/issues/215)
