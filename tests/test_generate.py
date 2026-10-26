from pathlib import Path

from sdd.budget import Block
from sdd.generate import Generator
from sdd.prompting import compose_system_prompt
from sdd.markdown_text import slugify
from sdd.impact import compute
from sdd.llm import Agent


class _FakeAgent:
    """정해진 답을 차례로 돌려주는 LLM 대역. 마지막 답을 반복한다."""

    def __init__(self, replies: list[str]):
        self.replies = replies
        self.users: list[str] = []

    def chat(self, system: str, user: str, tag: str = "") -> str:
        self.users.append(user)
        return self.replies[min(len(self.users) - 1, len(self.replies) - 1)]


_GOOD = ("`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:40`. "
         "스트림 구성은 `configureStreams()` 가 담당합니다 `device/CameraDevice.cpp:120`.")
_BAD = _GOOD.replace("담당합니다", "담당한다")


def _ask(tmp_cfg, sample_model, replies):
    tmp_cfg.agent.kind = "fake"
    agent = _FakeAgent(replies)
    gen = Generator(tmp_cfg, sample_model, agent)
    sec = {"id": "t", "title": "테스트"}
    blocks = [Block("core", "class CameraDevice `device/CameraDevice.h:40`", 0)]
    text, _, verdict = gen._ask("t", sec, "테스트", blocks, "")
    return text, verdict, agent


def test_slugify_keeps_korean_like_pymdownx():
    assert slugify("패키지별 역할") == "패키지별-역할"
    assert slugify("HAL 진입점") == "hal-진입점"
    assert slugify("코드를 처음 읽는 순서") == "코드를-처음-읽는-순서"


def test_incremental_facts_generation_does_not_call_model_for_summary(tmp_cfg, sample_model, monkeypatch):
    import argparse
    import yaml
    from sdd import cli
    from sdd.impact import ImpactReport

    section = dict(id='structure', title='구조', narration='facts', facts={'classes': ['CameraDevice']})
    tmp_cfg.sections_file.write_text(yaml.safe_dump({'sections': [section]}), encoding='utf-8')
    tmp_cfg.agent.kind = 'ollama'
    sample_model.save(tmp_cfg.facts_path)
    report = ImpactReport(base='old', head='abc123', sections={'structure': ['changed']})
    report.save(tmp_cfg.build_dir / 'impact.json')
    monkeypatch.setattr(cli, '_cfg', lambda args: tmp_cfg)
    def no_calls(*args, **kwargs):
        raise AssertionError('Facts-only incremental generation must not call an LLM')
    monkeypatch.setattr(cli.Agent, 'chat', no_calls)
    assert cli.cmd_generate(argparse.Namespace(from_impact=True, sections=None)) == 0
    assert 'generation_method: extracted-structure' in (tmp_cfg.sdd_dir / 'structure.md').read_text(encoding='utf-8')
    assert 'old..abc123' in (tmp_cfg.build_dir / 'change_impact.md').read_text(encoding='utf-8')


def test_system_prompt_includes_style_readme_only_by_default(tmp_cfg):
    system = compose_system_prompt(tmp_cfg)
    assert "개발자 가이드 집필 규칙:" in system and "1. 각 페이지는 독자가 먼저 할 일이나" in system
    assert "brief.mjs" not in system                          # README 의 설명 문단은 넣지 않는다
    assert "Lead with the next action" not in system       # i-have-adhd 원문은 기본 제외
    tmp_cfg.agent.full_style_guides = True
    assert "Lead with the next action" in compose_system_prompt(tmp_cfg)


def test_structured_prompt_is_optional_and_keeps_style(tmp_cfg):
    original = compose_system_prompt(tmp_cfg)
    assert compose_system_prompt(tmp_cfg, structured=True) == original
    (tmp_cfg.prompts_dir / 'design-system.md').write_text('Return structured JSON.', encoding='utf-8')
    structured = compose_system_prompt(tmp_cfg, structured=True)
    assert structured.startswith('Return structured JSON.')
    assert '개발자 가이드 집필 규칙:' in structured
    assert compose_system_prompt(tmp_cfg) == original


def test_dry_run_generates_all_pages_with_frame(tmp_cfg, sample_model):
    agent = Agent(tmp_cfg.agent, dump_dir=tmp_cfg.build_dir / "prompts")
    written = Generator(tmp_cfg, sample_model, agent).run()
    names = sorted(p.relative_to(tmp_cfg.sdd_dir).as_posix() for p in written)
    # 사람이 쓰는 문서(constraints, decisions)는 아직 없으므로 빈 자리를 만든다.
    assert names == ["components.md", "constraints.md", "decisions.md", "feature-flags.md", "index.md",
                     "overview.md", "scenarios/index.md", "scenarios/process_capture_request.md", "threading.md"]
    stub = (tmp_cfg.sdd_dir / "constraints.md").read_text(encoding="utf-8")
    assert "## 아직 작성되지 않았습니다" in stub and "status: needs-review" in stub

    overview = (tmp_cfg.sdd_dir / "overview.md").read_text(encoding="utf-8")
    # 페이지 뼈대: lead(굵게) -> 확인할 내용 표 -> 본문 -> 근거 -> 다음 단계
    assert overview.index("**수정할 기능이") < overview.index("| 지금 확인할 내용 | 이동할 절 |")
    assert "## 패키지별 역할" in overview and "| `device` | 1 |" in overview
    assert "## 선택한 시나리오의 코드 읽기 순서" in overview
    assert "1. 진입점 `CameraDevice::processCaptureRequest" in overview
    assert "`createFrame()` 부분을 읽습니다." not in overview
    assert '??? note "근거와 검토 정보"' in overview
    assert "- 근거 파일: `device/CameraDevice.cpp`" in overview
    assert overview.rstrip().endswith("다음 단계: [컴포넌트 구조와 책임](components.md)")

    components = (tmp_cfg.sdd_dir / "components.md").read_text(encoding="utf-8")
    assert "## device" in components and "## pipeline" in components
    assert "| `CameraDevice` | `device/CameraDevice.h:40` | – | HAL3 디바이스 진입점 |" in components
    assert "| `PipeThread` | `pipeline/PipeThread.h:8` | `Thread` | 확인 필요 |" in components
    assert "| device 패키지의 클래스를 수정합니다. | [device](#device) |" in components
    assert '??? note "근거와 검토 정보: pipeline"' in components

    flags = (tmp_cfg.sdd_dir / "feature-flags.md").read_text(encoding="utf-8")
    assert "| `USE_SAT` | `1` | `device/CameraDevice.cpp:310` |" in flags
    assert "status: ok" in flags            # table 종류는 LLM 을 안 거치므로 바로 ok

    scen = (tmp_cfg.sdd_dir / "scenarios/process_capture_request.md").read_text(encoding="utf-8")
    assert "```mermaid" in scen
    assert "| 1 | `CameraDevice` | `FrameFactory::createFrame()` | 정적 호출 지점입니다. | `device/CameraDevice.cpp:305` |" in scen
    assert "## 전체 추적 기록" in scen
    assert "status: ok" in scen  # Static scenarios do not depend on the dry-run agent.
    assert "generation_method: extracted-scenario" in scen
    assert "다음 단계: [핵심 시나리오 목록](index.md)" in scen   # scenarios/ 안에서는 index.md 가 같은 디렉터리

    index = (tmp_cfg.sdd_dir / "scenarios/index.md").read_text(encoding="utf-8")
    assert "| [캡처 요청 처리](process_capture_request.md) |" in index

    threading = (tmp_cfg.sdd_dir / "threading.md").read_text(encoding="utf-8")
    assert "needs_human: true" in threading and "PipeThread" in threading

    prompts = sorted((tmp_cfg.build_dir / "prompts").glob("*.md"))
    assert prompts, "dry-run 은 프롬프트를 기록해야 한다"
    body = prompts[0].read_text(encoding="utf-8")
    assert "개발자 가이드 집필 규칙" in body and "사실 (이 목록 밖의 내용은 쓰지 않습니다):" in body


def test_lint_finding_triggers_retry_with_reason(tmp_cfg, sample_model):
    text, verdict, agent = _ask(tmp_cfg, sample_model, [_BAD, _GOOD])
    assert verdict.ok and "담당합니다" in text
    assert len(agent.users) == 2
    # 재요청 프롬프트에 반려 사유가 들어간다.
    assert "[종결어미]" in agent.users[1] and "이전 출력의 문제" in agent.users[1]
    # 린트만 실패한 반려에는 인용 복사 지시를 붙이지 않는다.
    assert "복사해서 인용합니다" not in agent.users[1]


def test_citation_failure_keeps_citation_guidance(tmp_cfg, sample_model):
    no_cite = "이 문서는 카메라 장치의 초기화 순서와 스트림 구성 절차, 콜백 등록 시점을 순서대로 설명합니다. 각 단계는 이후 절에서 자세히 다룹니다."
    _, verdict, agent = _ask(tmp_cfg, sample_model, [no_cite])
    assert not verdict.ok
    assert "복사해서 인용합니다" in agent.users[1]


def test_lint_finding_survives_retries_as_needs_review(tmp_cfg, sample_model):
    _, verdict, agent = _ask(tmp_cfg, sample_model, [_BAD])
    assert not verdict.ok
    assert len(agent.users) == tmp_cfg.max_retries + 1
    assert any("[종결어미]" in n for n in verdict.notes)


def test_fence_wrapped_reply_is_unwrapped_before_checks(tmp_cfg, sample_model):
    text, verdict, agent = _ask(tmp_cfg, sample_model, [f"```markdown\n{_GOOD}\n```"])
    assert verdict.ok and len(agent.users) == 1
    assert "```" not in text


def test_per_package_incremental_preserves_other_sections(tmp_cfg, sample_model):
    from sdd.impact import ImpactReport
    tmp_cfg.agent.kind = "fake"
    sec = {"id": "components", "title": "컴포넌트 구조와 책임", "facts": {"classes": ["*"]}}
    first = _FakeAgent([_GOOD])
    Generator(tmp_cfg, sample_model, first)._per_package(sec, None)
    assert len(first.users) == 2                       # device, pipeline 두 번 호출
    page = tmp_cfg.sdd_dir / "components.md"
    assert page.read_text(encoding="utf-8").count("만들어집니다") == 2

    second = _FakeAgent([_GOOD.replace("만들어집니다", "새로 생성됩니다")])
    report = ImpactReport(base="a", head="b", packages=["device"], sections={"components": []})
    Generator(tmp_cfg, sample_model, second)._per_package(sec, report)
    text = page.read_text(encoding="utf-8")
    assert len(second.users) == 1                      # device 만 다시 생성
    assert "새로 생성됩니다" in text                     # device 절은 갱신
    assert "만들어집니다" in text                        # pipeline 절은 이월
    assert '??? note "근거와 검토 정보: pipeline"' in text
    assert "| pipeline 패키지의 클래스를 수정합니다. |" in text


def test_per_package_regenerates_reused_section_with_broken_citations(tmp_cfg, sample_model):
    from sdd.impact import ImpactReport
    tmp_cfg.agent.kind = "fake"
    sec = {"id": "components", "title": "컴포넌트 구조와 책임", "facts": {"classes": ["*"]}}
    Generator(tmp_cfg, sample_model, _FakeAgent([_GOOD]))._per_package(sec, None)
    page = tmp_cfg.sdd_dir / "components.md"
    # 이월 후보 절의 인용이 새 facts 와 어긋난 상황을 만든다.
    page.write_text(page.read_text(encoding="utf-8").replace("device/CameraDevice.cpp:120", "gone/Gone.cpp:1"),
                    encoding="utf-8", newline="\n")

    second = _FakeAgent([_GOOD])
    report = ImpactReport(base="a", head="b", packages=["device"], sections={"components": []})
    Generator(tmp_cfg, sample_model, second)._per_package(sec, report)
    assert len(second.users) == 2                      # pipeline 도 이월하지 않고 다시 생성
    assert "gone/Gone.cpp:1" not in page.read_text(encoding="utf-8")


def test_impact_limits_regeneration(tmp_cfg, sample_model):
    agent = Agent(tmp_cfg.agent)
    report = compute(tmp_cfg, sample_model, ["pipeline/PipeThread.h"], base="a", head="b")
    written = Generator(tmp_cfg, sample_model, agent).run(impact=report)
    names = {p.name for p in written}
    assert "threading.md" in names and "overview.md" in names
    assert "process_capture_request.md" not in names


def test_manual_page_evidence_files_flagged(tmp_cfg, sample_model):
    page = tmp_cfg.sdd_dir / "constraints.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("---\nstatus: ok\nkind: manual\nevidence_files:\n  - device/CameraDevice.cpp\n---\n\n# 제약\n",
                    encoding="utf-8")
    report = compute(tmp_cfg, sample_model, ["device/CameraDevice.cpp"], base="a", head="b")
    assert "constraints" in report.sections
    assert any("재검토" in r for r in report.sections["constraints"])
    # manual 은 재생성 대상이 아니다.
    written = Generator(tmp_cfg, sample_model, Agent(tmp_cfg.agent)).run(impact=report)
    assert all(Path(p).name != "constraints.md" for p in written)


def _overview_presenter(tmp_cfg, sample_model):
    """개요 표 검사용 presenter. 익명 구조체와 표에서 뺀 패키지를 섞어 둔다."""
    from sdd.facts.model import ClassInfo, Location, PackageInfo, Relation

    m = sample_model
    m.packages["src/gen"] = PackageInfo(name="src/gen", path="src/gen", classes=["Generated"])
    m.classes["Generated"] = ClassInfo(
        name="Generated", loc=Location("src/gen/generated.h", 3), package="src/gen")
    # libclang 이 익명 구조체에 붙이는 이름에는 파싱한 기계의 절대 경로가 들어간다.
    anon = "Ctx::(unnamed struct at /home/someone/work/src/hal/ctx.h:33:2)"
    m.classes[anon] = ClassInfo(name=anon, loc=Location("device/ctx.h", 33), package="device")
    m.packages["device"].classes.append(anon)
    m.relations.append(Relation(source="Generated", target="CameraDevice", type="association"))
    m.relations.append(Relation(source="PipeThread", target="CameraDevice", type="inheritance"))
    m.relations.append(Relation(source="FrameFactory", target="CameraDevice", type="association"))
    from sdd.fact_presenter import FactPresenter
    return FactPresenter(m, tmp_cfg.package_depth)


def test_패키지_표는_익명_구조체_이름을_싣지_않는다(tmp_cfg, sample_model):
    presenter = _overview_presenter(tmp_cfg, sample_model)
    table = presenter.package_table(["device", "pipeline"])
    assert "unnamed struct" not in table and "/home/someone" not in table
    assert "`CameraDevice`" in table
    # 클래스 수는 익명 구조체를 포함한 실제 개수를 그대로 보여 준다.
    assert "| `device` | 2 |" in table


def test_의존_표는_선택한_패키지만_방향마다_한_줄로_싣는다(tmp_cfg, sample_model):
    presenter = _overview_presenter(tmp_cfg, sample_model)
    deps = presenter.package_deps_table(["device", "pipeline"])
    assert "src/gen" not in deps                                  # 표에 없는 패키지는 의존에서도 뺀다
    assert deps.count("`pipeline` → `device`") == 1               # 상속과 참조를 한 줄로 합친다
    assert "| `pipeline` → `device` | 1 | 1 |" in deps


def test_시나리오가_없으면_목차를_통과로_기록하지_않는다(tmp_cfg, sample_model):
    sample_model.scenarios.clear()
    sample_model.meta["callgraph"] = {"missing_entries": 3}
    tmp_cfg.agent.kind = "fake"
    gen = Generator(tmp_cfg, sample_model, _FakeAgent([_GOOD]))
    sec = {"id": "scenarios", "title": "핵심 시나리오 시퀀스", "output": "scenarios/index.md",
           "kind": "per-scenario", "lead": "고르세요.", "facts": {"scenarios": "*"},
           "next": {"title": "다음", "link": "camera-model.md"}}
    written = gen._per_scenario(sec, None)
    text = written[-1].read_text(encoding="utf-8")
    assert "status: needs-review" in text
    assert "확인 필요: 추적한 시나리오가 없습니다." in text
    assert "진입 함수 3 개를 추출에서 찾지 못했습니다." in text


def _scenario_cfg(tmp_cfg, body: str):
    (tmp_cfg.config_dir / "scenarios.yaml").write_text(body, encoding="utf-8")


def _two_scenario_model(sample_model):
    from sdd.facts.model import Location, Message, Scenario

    sample_model.scenarios["b_second"] = Scenario(
        id="b_second", title="두 번째", entry="CameraDevice::flush()",
        participants=["CameraDevice"],
        messages=[Message("CameraDevice", "PipeThread", "enqueue", Location("device/CameraDevice.cpp", 400))])
    sample_model.scenarios["a_first"] = Scenario(
        id="a_first", title="첫 번째", entry="CameraDevice::open()",
        participants=["CameraDevice"],
        messages=[
            Message("CameraDevice", "Log", "trace", Location("device/CameraDevice.cpp", 10)),
            Message("CameraDevice", "RequestManager", "submit", Location("device/CameraDevice.cpp", 20)),
            Message("RequestManager", "FrameFactory", "_d", Location("pipeline/FrameFactory.cpp", 30)),
        ])
    del sample_model.scenarios["process_capture_request"]
    return sample_model


def test_시나리오는_설정한_순서대로_이어진다(tmp_cfg, sample_model):
    _scenario_cfg(tmp_cfg, "scenarios:\n  - id: a_first\n    from: CameraDevice::open()\n"
                           "  - id: b_second\n    from: CameraDevice::flush()\n")
    tmp_cfg.agent.kind = "fake"
    gen = Generator(tmp_cfg, _two_scenario_model(sample_model), _FakeAgent([_GOOD]))
    sec = {"id": "scenarios", "title": "시나리오", "output": "scenarios/index.md", "kind": "per-scenario",
           "lead": "고르세요.", "facts": {"scenarios": "*"}, "next": {"title": "다음", "link": "camera-model.md"}}
    gen._per_scenario(sec, None)
    first = (tmp_cfg.sdd_dir / "scenarios" / "a_first.md").read_text(encoding="utf-8")
    # 이름 순이면 a_first 다음이 b_second 가 아니라 목록으로 갔을 것이다.
    assert "다음 단계: [두 번째](b_second.md)" in first
    assert [s[0] for s in gen._ordered_scenarios()] == ["a_first", "b_second"]


def test_hide_규칙은_표시만_줄이고_뺀_개수를_적는다(tmp_cfg, sample_model):
    _scenario_cfg(tmp_cfg, "defaults:\n  hide:\n    owners: [\"Log\"]\n    names: [\"_d\"]\n"
                           "scenarios:\n  - id: a_first\n    from: CameraDevice::open()\n"
                           "  - id: b_second\n    from: CameraDevice::flush()\n")
    tmp_cfg.agent.kind = "fake"
    model = _two_scenario_model(sample_model)
    gen = Generator(tmp_cfg, model, _FakeAgent([_GOOD]))
    shown, hidden = gen._visible_messages(model.scenarios["a_first"])
    assert [m.name for m in shown] == ["submit"]
    assert hidden == 2
    sec = {"id": "scenarios", "title": "시나리오", "output": "scenarios/index.md", "kind": "per-scenario",
           "lead": "고르세요.", "facts": {"scenarios": "*"}, "next": {"title": "다음", "link": "camera-model.md"}}
    gen._per_scenario(sec, None)
    page = (tmp_cfg.sdd_dir / "scenarios" / "a_first.md").read_text(encoding="utf-8")
    assert "`RequestManager::submit()`" in page
    overview = page.split("## 주요 확인 지점")[1].split("## 추적 범위와 경계")[0]
    assert "trace()" not in overview and "_d()" not in overview
    assert "요약의 hide 규칙에 해당하는 호출은 2개입니다." in page
    assert "Log::trace()" in page and "FrameFactory::_d()" in page
    # 사실은 그대로 남는다.
    assert len(model.scenarios["a_first"].messages) == 3


def test_문서_안내는_섹션_정의로_만든다(tmp_cfg, sample_model):
    (tmp_cfg.config_dir / "sections.yaml").write_text('''sections:
  - id: index
    title: 문서 안내
    output: index.md
    kind: index
    lead: 아래 표에서 고르세요.
    reader: 처음 여는 개발자
    next: {title: Device, link: device.md}
  - id: device
    title: Device
    output: device.md
    kind: prose
    lead: 클래스부터 확인하세요.
    reader: 클래스를 수정하는 개발자
    facts:
      classes: [CameraDevice]
    next: {title: 문서 안내, link: index.md}
  - id: manual-page
    title: 설계 결정 기록
    output: decisions.md
    kind: manual
    next: {title: 문서 안내, link: index.md}
''', encoding="utf-8")
    tmp_cfg.agent.kind = "fake"
    agent = _FakeAgent([_GOOD])
    gen = Generator(tmp_cfg, sample_model, agent)
    sec = next(s for s in tmp_cfg.sections() if s["id"] == "index")
    page = gen._index_page(sec).read_text(encoding="utf-8")
    assert "| [Device](device.md) | 클래스를 수정하는 개발자 | 클래스부터 확인하세요. |" in page
    assert "index.md" not in page.split("## 문서 목록")[1]        # 자기 자신은 넣지 않는다
    assert "decisions.md" not in page                            # 아직 없는 수동 문서로 링크하지 않는다
    assert "status: ok" in page
    assert agent.users == []                                     # LLM 을 부르지 않는다


def test_기존_본문을_그대로_다시_써도_메아리로_지우지_않는다(tmp_cfg, sample_model):
    """프롬프트는 기존 본문의 구조를 유지하라고 지시한다. 그대로 돌아온 문장을 지우면 본문이 사라진다."""
    kept = ("`CameraDevice` 는 카메라마다 하나씩 만들어집니다 `device/CameraDevice.h:40`. "
            "스트림 구성은 `configureStreams()` 가 담당합니다 `device/CameraDevice.cpp:120`.")
    tmp_cfg.agent.kind = "fake"
    agent = _FakeAgent([kept])
    gen = Generator(tmp_cfg, sample_model, agent)
    sec = {"id": "t", "title": "테스트"}
    blocks = [Block("core", "class CameraDevice `device/CameraDevice.h:40`", 0)]
    text, _, verdict = gen._ask("t", sec, "테스트", blocks, existing=kept)
    assert kept in agent.users[0]          # 기존 본문은 프롬프트에 들어간다
    assert text.strip() == kept            # 그대로 돌아와도 본문이 남는다
    assert verdict.ok


def test_사실_목록을_되풀이한_줄은_계속_지운다(tmp_cfg, sample_model):
    tmp_cfg.agent.kind = "fake"
    fact_line = "class CameraDevice `device/CameraDevice.h:40`"
    good = "`CameraDevice` 는 요청을 큐에 넣습니다 `device/CameraDevice.cpp:300`."
    agent = _FakeAgent([fact_line + "\n" + good])
    gen = Generator(tmp_cfg, sample_model, agent)
    text, _, _ = gen._ask("t", {"id": "t", "title": "테스트"}, "테스트",
                          [Block("core", fact_line, 0)], existing="")
    assert fact_line not in text and good in text


def test_페이지_머리말을_본문에_되풀이하면_지운다(tmp_cfg, sample_model):
    """머리말은 뼈대가 굵게 한 번 찍는다. 본문 첫 줄에 같은 문장이 또 나오면 중복으로 보인다."""
    lead = "수정할 코드가 어느 패키지에 있는지 아래 표에서 먼저 찾으세요."
    body = "`CameraDevice` 는 요청을 큐에 넣습니다 `device/CameraDevice.cpp:300`."
    tmp_cfg.agent.kind = "fake"
    gen = Generator(tmp_cfg, sample_model, _FakeAgent([lead + "\n\n" + body]))
    text, _, _ = gen._ask("t", {"id": "t", "title": "테스트", "lead": lead}, "테스트",
                          [Block("core", "class CameraDevice `device/CameraDevice.h:40`", 0)], existing="")
    assert lead not in text and body in text


def test_줄여_쓴_한정_이름을_사실의_이름으로_되돌린다(tmp_cfg, sample_model):
    """소형 모델은 앞 네임스페이스를 뺀다. 인용을 고치는 것과 같은 원칙으로 이름도 되돌린다."""
    from sdd.facts.model import ClassInfo, Location

    sample_model.classes["hal::ipa::ipu3::IPAIPU3"] = ClassInfo(
        name="hal::ipa::ipu3::IPAIPU3", loc=Location("device/CameraDevice.h", 40))
    tmp_cfg.agent.kind = "fake"
    said = ("`ipa::ipu3::IPAIPU3` 는 요청을 처리합니다 `device/CameraDevice.h:40`.")
    gen = Generator(tmp_cfg, sample_model, _FakeAgent([said]))
    text, _, _ = gen._ask("t", {"id": "t", "title": "테스트"}, "테스트",
                          [Block("core", "class `device/CameraDevice.h:40`", 0)], existing="")
    assert "`hal::ipa::ipu3::IPAIPU3`" in text


def test_뒤가_같은_이름이_둘이면_손대지_않는다(tmp_cfg, sample_model):
    from sdd.semantic import normalize_symbols
    from sdd.facts.model import ClassInfo

    for name in ("a::pkg::Same", "b::pkg::Same"):
        sample_model.classes[name] = ClassInfo(name=name)
    said = "`pkg::Same` 을 확인하세요."
    assert normalize_symbols(said, sample_model) == said


def test_확인_필요_문단에는_인용을_요구하지_않는다(sample_model):
    """확인되지 않았다고만 적은 문단에는 인용할 위치가 없다."""
    from sdd.semantic import review
    supplied = {"device/CameraDevice.h:40"}
    text = ("`CameraDevice` 는 요청을 큐에 넣습니다 `device/CameraDevice.h:40`.\n\n"
            "콜백이 실행되는 스레드는 정적 분석으로 확인할 수 없습니다. "
            "종료 순서는 코드를 실행해서 확인해야 합니다.")
    assert "설명 문단에 근거 인용이 없습니다." not in review(text, sample_model, supplied)


def test_사실을_주장하는_문단에는_계속_인용을_요구한다(sample_model):
    from sdd.semantic import review
    text = ("`CameraDevice` 는 요청을 큐에 넣습니다 `device/CameraDevice.h:40`.\n\n"
            "버퍼는 파이프라인이 해제합니다. 종료 순서는 확인해야 합니다.")
    assert "설명 문단에 근거 인용이 없습니다." in review(text, sample_model, {"device/CameraDevice.h:40"})



def test_사람이_쓴_문서는_덮어쓰지_않는다(tmp_cfg, sample_model):
    tmp_cfg.sdd_dir.mkdir(parents=True, exist_ok=True)
    written_by_hand = '''
---
section: constraints
---

# 제약

버퍼는 파이프라인이 해제합니다.
'''
    (tmp_cfg.sdd_dir / "constraints.md").write_text(written_by_hand, encoding="utf-8")
    tmp_cfg.agent.kind = "fake"
    Generator(tmp_cfg, sample_model, _FakeAgent([_GOOD])).run()
    assert (tmp_cfg.sdd_dir / "constraints.md").read_text(encoding="utf-8") == written_by_hand


def test_고른_섹션만_만들_때는_범위_밖_자리를_만들지_않는다(tmp_cfg, sample_model):
    tmp_cfg.agent.kind = "fake"
    Generator(tmp_cfg, sample_model, _FakeAgent([_GOOD])).run(section_ids=["overview"])
    assert (tmp_cfg.sdd_dir / "overview.md").exists()
    assert not (tmp_cfg.sdd_dir / "constraints.md").exists()


def test_지정한_설정_파일을_그대로_읽는다(tmp_path):
    """이름을 버리고 sdd.yaml 을 읽으면 지정하지 않은 설정이 조용히 돈다."""
    import pytest
    from sdd.config import load

    (tmp_path / "sdd.yaml").write_text("source:\n  root: ./default\n", encoding="utf-8")
    (tmp_path / "sdd.a.yaml").write_text("source:\n  root: ./side-a\n", encoding="utf-8")
    (tmp_path / "sdd.a.local.yaml").write_text("agent:\n  model: side-a-model\n", encoding="utf-8")

    assert load(tmp_path / "sdd.yaml").source_root.name == "default"
    chosen = load(tmp_path / "sdd.a.yaml")
    assert chosen.source_root.name == "side-a"
    # 로컬 덮어쓰기는 같은 이름 옆에서 찾는다.
    assert chosen.agent.model == 'side-a-model'
    # 기본 설정의 로컬 덮어쓰기가 다른 설정에 새지 않는다.
    assert load(tmp_path / "sdd.yaml").agent.model != "side-a-model"

    with pytest.raises(FileNotFoundError):
        load(tmp_path / "sdd.없음.yaml")
