"""Human-readable presentation of impact coverage results; no analysis or I/O."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .approvals import finding_key, finding_state

if TYPE_CHECKING:
    from .impact import ImpactReport


def review_markdown(report: ImpactReport, ledger: dict[str, Any] | None = None,
                    triage: dict[str, dict[str, Any]] | None = None, passed: set[str] | None = None) -> str:
    coverage = report.coverage
    ledger = ledger or {}
    triage = triage or {}
    passed = passed or set()
    lines = ["# 변경 문서 범위 검토", "", f"비교 범위: `{report.base}..{report.head}`", ""]
    if not coverage:
        return "\n".join(lines + ["범위 검사가 없는 이전 영향 보고서입니다. impact를 다시 실행하세요.", ""])
    lines += [f"상태: **{coverage['status']}** · 검토 항목 {len(coverage['findings'])}개", "",
              "이 결과는 설정상 문서 범위 검사입니다. 문서의 존재·최신성·설명 정확성이나 사람의 승인을 보장하지 않습니다.", "",
              "## 검토할 변경", ""]
    labels = {"entity-outside-document-scope": "클래스·함수를 선택하는 문서가 없습니다",
              "document-not-scheduled": "대응 문서는 있지만 재생성 대상으로 선택되지 않았습니다",
              "no-extracted-entity": "추출한 클래스·함수와 연결되지 않아 범위를 확인할 수 없습니다"}
    state_labels = {"accepted": "장부에서 승인됨 · 관문 제외",
                    "deferred": "장부에서 보류됨 · 관문 유지", "open": "미결"}
    decisions = {"out-of-scope": "범위 밖", "needs-document": "문서 추가 필요", "unsure": "판단 불가"}
    for item in coverage["findings"]:
        state = finding_state(ledger, item) if ledger else "open"
        key = finding_key(item)
        lines += [f"- `{item['name']}`: {labels[item['reason']]}. ({state_labels[state]})",
                  "  근거 파일: " + ", ".join(f"`{f}`" for f in item["files"]) + ".",
                  f"  장부 키: `{key}` (승인: `sdd accept --finding \"{key}\"`)"]
        if key in triage:
            entry = triage[key]
            gate = "관문 제외" if key in passed else "관문 유지"
            lines.append(f"  LLM 판정: **{decisions[entry['decision']]}** · {entry['reason']} "
                         f"({entry['model']}, 사람 검토 전 · {gate})")
    if not coverage["findings"]:
        lines.append("현재 추출 사실과 설정에서 범위 누락을 찾지 못했습니다.")
    if coverage.get("classified"):
        kinds = {"comment-whitespace-include-only": "주석·공백·#include만 바뀜",
                 "outside-analyzed-build": "분석한 빌드에서 컴파일되지 않음"}
        lines += ["", "## 자동 분류한 변경", "",
                  "주석·공백·`#include`만 바뀌고 구조가 같은 항목, 그리고 분석한 빌드 구성에서 컴파일되지 않는 파일입니다. "
                  "문서가 다루는 코드가 바뀌지 않았으므로 검토 항목에서 뺐습니다. 사람의 승인이 아니며 장부에 기록하지 않습니다.", ""]
        for item in coverage["classified"]:
            lines.append(f"- `{item['name']}` ({kinds.get(item['classification'], item['classification'])}): "
                         + ", ".join(f"`{f}`" for f in item["files"]))
    lines += ["", "## 파일 감시와 수동 검토 연결", ""]
    for item in coverage["files"]:
        lines.append(f"- `{item['file']}`: {item['status']}; watch={', '.join(item['watch_sections']) or '(없음)'}; "
                     f"수동 검토={', '.join(item['manual_review_sections']) or '(없음)'}")
    lines += ["", "## 검사 한계", "",
              "- 변경 파일 안의 선언·정의 위치를 사용합니다. 줄별 변경이나 LLM 입력 예산에 따른 생략은 별도 검증이 필요합니다.",
              "- watch 일치만으로 누락이 해결되지는 않습니다. facts.classes/functions 범위를 보완하거나 검토자가 범위 밖 변경인지 판단해야 합니다.",
              "- 빌드 파일, 그리고 빌드에서 읽었지만 클래스·함수가 추출되지 않은 코드는 검토 대상으로 남습니다. "
              "분석한 빌드가 읽지 않은 C/C++ 파일은 자동 분류합니다. 수동 문서의 근거 연결은 검토 위치만 안내합니다."]
    if not coverage["baseline_available"]:
        lines.append("- 이전 facts가 없어 삭제된 심볼을 완전히 검사하지 못했습니다. --base-facts로 비교 기준의 facts를 제공하세요.")
    if coverage["ignored_files"]:
        lines += ["", "source.exclude로 제외한 파일: " + ", ".join(f"`{f}`" for f in coverage["ignored_files"])]
    return "\n".join(lines) + "\n"
