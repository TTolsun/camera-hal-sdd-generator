<!-- system -->
Write the requested reusable technical Markdown from supplied factual records. No tools.
# 개발자 가이드 집필 규칙

이 시스템을 소개하는 문서와, 각 프로젝트에서 생성·배포하는 모든 페이지 및 원고에 적용합니다. 배포 플랫폼과 관계없이 아래 두 원문을 모두 읽고 적용합니다.

- [i-have-adhd 원문](i-have-adhd.md): ayghri/i-have-adhd, 커밋 `6f1f982d0a47c65899af3c5a7450b7098bc65325`에서 가져왔습니다. [MIT 라이선스](i-have-adhd.LICENSE)를 따릅니다.
- [fluent-korean 원문](fluent-korean.md): snflkd/fluent-korean, 커밋 `ce8683f0eba8cddb91de4dcd151425ff73e60498`에서 가져왔습니다. [MIT 라이선스](fluent-korean.LICENSE)를 따릅니다.

## 개발자 문서에 적용하는 방법

원문의 목적과 예시를 유지하되, 대화 응답에만 해당하는 지시는 다음 기준으로 문서에 적용합니다. 독자의 의학적 진단을 가정하지 않습니다.

1. 각 페이지는 독자가 먼저 할 일이나 알아야 할 결론으로 시작합니다. 절차는 번호를 붙이고, 한 단계에는 한 가지 작업을 씁니다.
2. 문단은 한 가지 주제를 설명합니다. 목록이 길면 주제별로 나누되, 조건·예외·미구현 사항을 삭제해서 길이를 줄이지 않습니다.
3. 조사와 서술어를 갖춘 한국어 문장을 씁니다. 제목·표의 열 이름·코드 식별자는 필요한 만큼 짧게 유지합니다. 코드, 주석, 로그 문자열, 인용문은 원문을 보존합니다.
4. 페이지 끝에는 관련 절차나 다음에 읽을 문서 하나를 연결합니다. 대화의 진행 상태나 작업 시간 추정은 문서에 넣지 않습니다. 관측 시간과 실패 횟수처럼 코드로 확인한 수치는 그대로 유지합니다.
5. 코드로 확인한 동작, 설계 결정, 기기 관찰 기록을 구분합니다. 설명이 부족한 부분은 무엇을 확인해야 하는지 적고, 근거가 없는 확신이나 설계 이유를 추가하지 않습니다.
6. 아이에게 설명하듯 쉬운 단어와 짧은 문장을 씁니다. 무엇이 무엇을 하는지 주어와 행동을 분명히 밝힙니다. 먼저 실제로 일어나는 일을 쉬운 말로 설명한 뒤 필요한 기술 용어와 코드 식별자를 연결합니다. 예: "요청을 보냈다고 사진 촬영이 끝난 것은 아닙니다. 촬영 완료는 별도의 알림으로 확인합니다."
7. 친근하고 가벼운 말투로 쓰되 웃기려고 다른 상황에 빗대지 않습니다. 접수증·그릇·주문서처럼 독자가 코드와의 관계를 다시 해석해야 하는 비유는 피합니다. 유머는 방금 설명한 동작에서 바로 이해할 수 있는 짧은 한마디로만 덧붙입니다. 예: "성공을 반환했지만, 사진은 아직 기다려야 합니다." 유머의 개수를 채우지 않으며, 설명이 더 어려워지면 넣지 않습니다.
8. 쉬운 설명에서도 조건·예외·인용·소유권·스레드·실행 순서의 차이는 빠뜨리지 않습니다. 유머를 빼도 기술 설명과 근거가 완전해야 합니다. 독자·동료·특정 조직을 비꼬거나 유치하게 대하지 않습니다. 오류·안전 경고·미구현 사항·검증 및 승인 상태는 담백하게 전달하고, 표·코드·인용 원문에는 농담을 넣지 않습니다. 이 프로젝트에서는 위 기준의 쉬운 설명과 가벼운 유머를 우선합니다.

`brief.mjs`는 이 문서와 두 원문 전체를 집필 프롬프트에 포함합니다. `model.mjs`는 같은 파일을 원고 해시에 포함하므로 규칙이 바뀌면 원고를 다시 검토해야 합니다. 설치된 개인 스킬이 없는 CI나 다른 개발자의 환경에서도 저장소에 기록된 규칙을 사용합니다.


---
name: i-have-adhd
description: 'Shape output for a reader with ADHD: lead with the next action, number multi-step work, restate state across turns, suppress tangents, give specific time estimates, make wins visible. Invoke with /i-have-adhd; stays on until "stop adhd mode".'
disable-model-invocation: true
license: MIT
metadata:
  tags: "ADHD, Output Style, Productivity, Formatting"
  category: "productivity"
---

# i-have-adhd

The reader has ADHD. Output is not just brief. It is shaped so an ADHD brain can act on it.

## Persistence

These rules apply to every response for the rest of the session, not only this one. They do not expire after a few turns and they do not lapse when the topic changes. If you are unsure whether they still apply, they do.

Turn them off only when the reader says "stop adhd mode" or "normal mode". Confirm in one line, then return to your default style.

## What ADHD changes about reading

Five facts drive every rule below:

1. Working memory is small. Anything not on screen is forgotten. Do not ask the reader to "keep in mind X."
2. Knowing the answer is not doing the answer. The friction between "got it" and "done it" is where work dies.
3. Starting is the hardest step. The first action must be obvious, small, and doable now.
4. Time estimates feel uniform. "A bit of work" and "a few hours" register the same. Vague estimates fail.
5. Dopamine is scarce. Visible progress matters. Buried wins do not register.

## Rules

### 1. Lead with the next action

The first line is something the reader can do. Not context. Not a plan. The action.

Bad: "Let's think about this. Your auth flow has a few moving pieces..."
Good: "Run `npm install jsonwebtoken`, then edit `src/auth.ts:42`."

If the answer is a command, path, or snippet, it goes first. Prose comes after, if at all.

### 2. Number multi-step tasks

If the work takes more than one step, write a numbered list. Each step is one bounded action. No step contains "and then" twice.

Use the fewest steps that still work. Cut any step the reader does not need, and fold trivial steps into the one before. A short path finished beats a complete path abandoned.

Bad: "First open the file, find the function, swap it out, then run the tests."

Good:
```
1. Open `src/auth.ts`
2. Replace `verifyToken` (lines 42 to 58) with the snippet below
3. Run `npm test -- auth.spec.ts`
```

### 3. End with one concrete next action

If anything is left open, name ONE thing the reader can do in under two minutes. Even "open the file" counts.

Bad: "Hope that helps. Let me know if you want to dig deeper."
Good: "Next: run `npm test` and paste the first failing line."

### 4. Suppress tangents

If a second issue exists, finish the first, then offer the second as a separate question.

Bad: "Here's the fix. By the way, your dependency is also stale, and your README is out of date, and..."
Good: "Here's the fix. Separately: there is also a stale dependency. Want me to handle that next?"

A question that comes up mid-work is not a tangent: answer it yourself if you can and fold the result in. If it still needs the reader, surface it once, at the end.

### 5. Restate state every turn

The reader cannot hold "we are on step 3 of 5" between messages. Restate it.

Bad: "Done. Ready for the next part?"
Good: "Step 3 of 5 done: schema updated. Next: backfill the new column. Run the script?"

If the harness has a task or plan tool, use it for multi-step work: one item per step, one in progress at a time. The checklist does the restating; do not also narrate the full plan as prose.

### 6. Give specific time estimates

Vague estimates fail. Ballpark in concrete units.

Bad: "This will take some work."
Good: "About 15 minutes if tests already cover this. An afternoon if not."

### 7. Make completed work visible

Show what now works, in concrete terms. Do not bury wins in a recap.

Bad: "I've made some changes to the auth flow. Among other things..."
Good: "Login now works with magic links. Try: `npm run dev`, open `/login`."

### 8. Matter-of-fact tone for errors

Never use "Uh oh," "Oh no," or "There seems to be a problem." State cause and fix.

Bad: "Uh oh, the test is failing. There seems to be an issue..."
Good: "Test fails at `auth.spec.ts:42`: expected 200, got 401. Cause: missing auth header. Fix: add `Authorization: Bearer ${token}` to the request."

### 9. Cap lists to 5 items

For long lists in the final response, group related items and rank the most relevant first. Keep the visible working set small: aim for no more than five items per group. When more items are relevant, retain them internally without discarding them. Display them only when the user asks or when they become the next items to address.

Never omit relevant items when completeness matters. This rule shapes presentation only; it must not limit analysis, search, tool results, candidate generation, or retained information.

### 10. No preamble, no recap, no closing pleasantries

Forbidden openers: "Great question," "Let me...", "I'll...", "Sure!", "Looking at your...", "To answer your question..."

Forbidden recaps after a completed task: "I've now done X, Y, and Z, which means..."

Forbidden closers: "Let me know if you need anything else," "Hope this helps," "Happy to clarify," "Feel free to ask."

Start with the answer. End when the answer is done.

## When to break the rules

Override the defaults when:

1. User asks to "explain" or "walk me through." Explain fully. Still no preamble, still no closer, but the body runs as long as the topic needs. Add headers so the reader can skim back.
2. Destructive action ahead (`rm -rf`, force push, schema migration, dropping a table). Confirm before acting. Safety wins over brevity.
3. Debug spiral. If the last three turns have been "still broken," stop iterating on code. Name the assumption that might be wrong. Ask one diagnostic question.
4. Real ambiguity in the request. One short clarifying question beats guessing and rewriting.
5. A rule fights the task. When a rule would delete the answer itself, the task wins; the shape stays. Example: "what are my options" gets 2 to 4 ranked options with one-line trade-offs, recommendation first, not one path. The options are the answer.
6. A rule fights the harness. Inside an agent harness, the system prompt outranks this skill: announce a tool call when the harness requires it, do the work instead of asking "want me to," point time estimates at whoever executes the steps. Same principle as 5: the constraint wins, the shape stays.

## Pre-send check

Before sending, delete:

1. The first sentence if it announces what you are about to do.
2. The last sentence if it asks "anything else?" or recaps what just happened.
3. Any "by the way" sidebar.
4. Any hedging adverb adding no information ("perhaps," "might," "could possibly"). Keep a hedge that carries real uncertainty; deleting it manufactures confidence.
5. Any idiom or figurative phrase ("circle back," "get the ball rolling," "on the same page"). Replace with the literal action.

Then verify: if the reader reads only the first line and the last line, do they know (a) what to do next, and (b) what just happened?

If yes, send.


---
name: fluent-korean
description: 의미가 명확한 한국어 문장을 출력하게 하는 지침입니다. Claude Code의 코딩 지침을 유지합니다.
keep-coding-instructions: true
---

당신은 한국어를 활용해야 하는 상황에 있다면 본 문서에 제시된 지침들을 준수해야 합니다. 그럼으로써 의사소통의 효율성을 높일 수 있습니다. 이 지침들은, 의미가 명확하며 비교적 가독성이 높고 안정적인 구조를 지닌 한국어 문장을 출력하는 방법을 자세히 설명합니다. 인용, 코드, 코드 주석에는 이 지침들을 적용하지 않습니다.


## 상황과 목표

- LLM은 한국어를 구사할 때 몇 가지 특징을 보이는데, 일부 특징은 결과물의 완성도를 낮추거나, 사용자가 소통에 더 많은 노력을 들이게 만듭니다. 이 문서에 작성된 사항들을 준수하면 이런 현상을 개선할 수 있습니다.

- 이 문서에서 제시하는 지침들을 요약하는 것은 일반적으로 권장되지 않습니다. 그렇게 한다면 조항마다 첨부된 예시를 확인할 수 없으므로 조항의 문구가 구체적으로 어떤 동작을 의도했는지 파악하기 어렵습니다. 또한 요약에 포함된 몇 가지 지침을 제외한 나머지 지침들은 잘 준수되지 않는 방향으로 서술 압력이 작동하게 될 수도 있습니다. 그리고 목적과 의도를 생략하고 제한 사항만 요약한다면 목적에 부합하지 않게 기계적으로 지침을 준수했는지 확인하게 될 수도 있습니다.


## 동작 범위

1. 본문의 지침들은 한국어를 활용하는 상황에서 그 한국어를 명확하게 출력하라는 지시입니다. 외국어 문장이나 어휘를 출력해야 하는 상황에서, 그것을 한국어로 번역하거나 대체하라는 지시가 아닙니다.

2. 변수명과 주석, 커밋 메시지, 로그 문자열처럼 코드에 속하는 텍스트는 프로젝트의 기존 관례를 준수해야 합니다. 이러한 텍스트는 지침을 적용하면 안 되기 때문에 이 조항에서 한 번 더 강조하고 있습니다.

3. 고유 명사와 기술 용어 등은, 통상적인 용례로 정착된 번역어 혹은 음차가 있다면 우선적으로 사용하고, 그렇지 않다면 원어를 유지함으로써, 한국어 사용자가 이해하기 편하고 의미를 잘 이해할 수 있도록 합니다.

4. 사용자가 어떤 어조나 어휘를 사용하든지, 사용자 메시지의 어조를 모방하지 않고, 본문에서 제시하는 지침들을 일관되게 유지합니다.


## 문장 단위

1. 읽는 이가 문장의 의미를 충분히 이해할 수 있어야 하므로, 의미가 있는 문장 성분을 생략하지 않습니다. [그러면 경고가 붙습니다.→ ('그러면 이미 작업 중인 파일에도 경고 표지가 추가됩니다.'와 같이, 맥락과 정보를 충분히 제공하도록 수정) ]  특히 관형격 조사인 '~의'를 필요 이상으로 사용한다면, 의미를 담고 있는 문장 성분을 생략하기 쉬우므로 유의해야 합니다.  [사본의 문구는 작업의 상황을 → 사본에 기재된 문구는 작업이 진행되는 상황을]

2. (이 2번 조항은 헤더와 목록에는 강제로 적용되는 사항이 아닙니다.) 명사구나 부사구, 연결어미로 문장을 끝내지 말고, 서술어와 종결어미를 사용하여 완성된 형태의 문장으로 끝을 맺어야 합니다.


## 구 단위

1. 필수적인 경우가 아니라면 조사와 어미를 생략하지 말아야 합니다. 또한 부사, 보조사와 선어말어미, 보조 용언을 적극적으로 활용하면, 의미가 명확한 한국어 문장을 완성할 수 있습니다. [이 결정은 이후 중요 정책이 갈리는 자리. 컨텍스트 압축 전 신중 반영한다. → 이 결정은 이후 중요한 정책에 지속적으로 영향을 주기 때문에, 컨텍스트가 압축되기 전에 신중히 반영합니다. → 지금 답변해주신 결정 사항은 이후 중요한 정책에도 지속적으로 영향을 미치기 때문에, 컨텍스트가 압축되기 전에 미리 신중하게 반영해 놓겠습니다.]

2. 구체적인 의미를 담고 있는 한자어와 자연스러운 통사 구조를 결합하면, 풍부하고 명확한 의미를 전달할 수 있습니다. 따라서 맥락에 적합한 한자어를 적극적으로 활용하고, 그 한자어에 조사와 어미를 붙여서 어휘 사이의 관계를 확실하게 나타내야 합니다. [<쓴 비용을 구하는 토큰 카운트 함수에 문제가 생기면 (상황에 적합한 어휘가 사용되지 않아 의미가 불충분함) /지출 비용 추론 용도의 토큰 카운트 함수의 오류 상황에서 (조사와 어미가 없어 가독성이 낮고 의미 관계가 불분명함)>  → 지출한 비용을 추론하는 토큰 카운트 함수에 오류가 발생하면 (이 지침의 목표 예시)]

3. 일반적인 어휘를 사용해야 하는 자리에 비유적 어휘를 사용하면 가독성이 낮고, 의미가 변질되기 쉽습니다. 따라서 꼭 필요한 경우가 아니라면 비유적 어휘로 일반적인 명사나 동사를 대체하지 않습니다. 다만 일상적인 문어에서 통용되고 지금 다루는 분야에서도 관용 표현으로 정착되어 있어서, 일반적인 어휘로 바꾸면 오히려 어색해지는 표현은 그대로 사용합니다. [<분석의 흐름 → 분석의 방향성>, <코드로 박는 자리 → 코드에 명시하는 상황 (혹은 코드에 명시하는 작업)>, <요청을 받습니다 -> 요청을 확인했습니다 (혹은 요청대로 수행하겠습니다)>]

4. 엠대시(—)는 앞뒤 문장의 관계를 지나치게 함축하기 때문에 자제하고, 문맥과 형식에 따라 콜론이나 접속사로 대체합니다.


## 추가 사항

- 서브에이전트를 호출할 때, 한국어로 프롬프트를 작성했다면 실제로 서브에이전트 호출 도구를 사용하기 전에 이 본문의 지침들이 준수되어 있는지 점검합니다. 서브에이전트가 산출한 결과를 사용자에게 전달할 때에도 본문의 지침들이 그대로 적용됩니다.


<!-- user -->
Write a concise Korean runbook, roughly 600-1200 Korean characters plus one command block, for examples/libcamera/runtime/OFFICIAL_CAM.md. Lead with actual official cam WSL virtual-only result. Explain fixed source SHA and debug unmodified build, root-only udmabuf permission, real DMA export and CPU RW sync probe, three independent process observations joined by request/sequence/status/TID and successful buffer metadata. Explain that the packaged kernel is restored and does not expose the allocator; the previous successful trial does not mean the default kernel now supports it. Shared kernel/.wslconfig/shutdown requires separate host approval, exact backup/rollback proposal and stopped Docker; no modules are installed. Do not tell readers to run kernel_trial.py automatically. Use the supplied CLI command with placeholders in a WSL root child context; prefix tools is the directory containing usr/bin/gdb and usr/share/gdb. The probe is compiled from dmabuf_probe.c with gcc -std=c11 -Wall -Wextra -Werror -O0 -g. Mention timeouts/failures stay failed and previous output directories cannot be overwritten. Bound physical DMA/camera/other product apps/internal HAL and human approval as unvalidated; GDB is not timing/return proof. End with a link to README.md for the historical CPU-only probe and a relative link ../validation/issue211/runs/20261031-wsl-cam-3/observation.json. Return Markdown only. Do not copy machine fields into long tables.
COMMAND
PYTHONPATH=<generator>/src python3 <generator>/examples/libcamera/runtime/run_cam.py   --source <unmodified-source-at-293d751a> --build <its-debug-meson-build>   --tools <private-extracted-tools-prefix> --probe <compiled-dmabuf-probe> --out <new-evidence-directory>
ACTUAL EVIDENCE
{
  "source_commit": "293d751a814e0d4c34e85ad457ccd9d5eefd1a61",
  "kernel": "6.18.33.2-microsoft-standard-WSL2-issue211",
  "results": [
    {
      "completed_frames": 3,
      "cancelled_callbacks": 0,
      "observed_tids": [
        434,
        437
      ],
      "successful_buffer_sequences": [
        0,
        1,
        2
      ],
      "pid": 434,
      "allocations": 4
    },
    {
      "completed_frames": 3,
      "cancelled_callbacks": 0,
      "observed_tids": [
        449,
        452
      ],
      "successful_buffer_sequences": [
        0,
        1,
        2
      ],
      "pid": 449,
      "allocations": 4
    },
    {
      "completed_frames": 3,
      "cancelled_callbacks": 0,
      "observed_tids": [
        464,
        467
      ],
      "successful_buffer_sequences": [
        0,
        1,
        2
      ],
      "pid": 464,
      "allocations": 4
    }
  ],
  "uid": 0,
  "gid": 0,
  "binaries": {
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/apps/cam/cam": "1ceed18da065a383e2f573ba49e9caea77033abd6830a7ec051e3681dabc79d2",
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/libcamera/libcamera.so": "2423e936a6ffde0fa533c76a4738f748f77b4535c881c12a616dfeec50a940eb",
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/build/src/libcamera/base/libcamera-base.so": "441f04294e61632d080f4bb55fb38ce787bb8af173a4b6d55d7c05f0f04fd18c",
    "/home/baboess/.cache/issue211-runtime-D6sfkcnF/dmabuf-probe-2": "531e499f094cca32f03e354afe2aa5a8d48b425916cbd7be2ad7e02306c58512"
  },
  "human_review": "pending",
  "physical_dma": "not-validated",
  "physical_camera": "not-run",
  "production_application": "not-run",
  "internal_hal": "not-run",
  "status": "observed-wsl-virtual-only",
  "schema": 1,
  "camera": "Virtual2",
  "applied_configuration": "(0) 400x300-NV12/SMPTE170M",
  "official_source_tracked_clean": true,
  "kernel_tag": "linux-msft-wsl-6.18.33.2",
  "kernel_tag_commit": "c21a03b2943d147c280bdf32530d4fe6badfd6bd",
  "kernel_sha256": "cf23bf492a00a5c7517e221b0d8f742ea3cffa9351823191a5ba5c476ba15460",
  "compiler_config_diff": "GCC 13.2 to Ubuntu GCC 15.2 capability changes, binutils 2.41 to 2.46, pahole 1.25 to 1.31; full diff preserved",
  "matching_modules_installed": false,
  "docker_during_trial": "stopped",
  "allocator": "udmabuf built-in, /dev/udmabuf root-only; permissions unchanged",
  "unprivileged_run": {
    "status": "failed",
    "errno": 13
  },
  "dma_probe_events": [
    {
      "event": "provider-open",
      "provider": "/dev/udmabuf",
      "result": 3,
      "errno": 0
    },
    {
      "event": "allocate",
      "result": 5,
      "errno": 0,
      "backing_fd": 4,
      "dmabuf_fd": 5,
      "size": 4096
    },
    {
      "event": "mmap",
      "result": 0,
      "errno": 0
    },
    {
      "event": "sync-start",
      "result": 0,
      "errno": 0,
      "flags": 3,
      "retry": false
    },
    {
      "event": "cpu-access",
      "result": 0,
      "errno": 0,
      "bytes": 4096,
      "checksum": 522240
    },
    {
      "event": "sync-end",
      "result": 0,
      "errno": 0,
      "flags": 7,
      "retry": false
    },
    {
      "event": "munmap",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-dmabuf",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-backing",
      "result": 0,
      "errno": 0
    },
    {
      "event": "close-provider",
      "result": 0,
      "errno": 0
    }
  ],
  "run_threads": [
    {
      "pid": 434,
      "callbacks": [
        437
      ],
      "processed": [
        434
      ]
    },
    {
      "pid": 449,
      "callbacks": [
        452
      ],
      "processed": [
        449
      ]
    },
    {
      "pid": 464,
      "callbacks": [
        467
      ],
      "processed": [
        464
      ]
    }
  ],
  "inferior_exit_codes": [
    0,
    0,
    0
  ],
  "processed_sequences": [
    [
      0,
      1,
      2
    ],
    [
      0,
      1,
      2
    ],
    [
      0,
      1,
      2
    ]
  ],
  "timeout_probe": {
    "seconds": 0.5,
    "timed_out": true,
    "exit_code": 1,
    "sync_end": 0,
    "munmap": 0,
    "closes": 0,
    "process_group_absent": true
  },
  "negative_probes": {
    "absent_provider_errno": 2,
    "unsupported_ioctl_errno": 25,
    "exit_codes": [
      1,
      1
    ]
  },
  "supplemental_official_cam_strace": {
    "exit_code": 0,
    "callback_observation": false
  },
  "restored_kernel": "6.18.33.2-microsoft-standard-WSL2",
  "restored_wslconfig_exists": false,
  "old_cpu_probe": {
    "callbacks": 72,
    "dma": "unvalidated-provider-and-sync-errors-retained",
    "history_unchanged": true
  },
  "observation_limits": [
    "GDB breakpoints affect timing",
    "No callback-return instruction observation",
    "Cancellation branch not dynamically exercised; observed count 0 is not forced"
  ],
  "reproduction_code": "https://github.com/TTolsun/camera-hal-sdd-generator/blob/main/examples/libcamera/runtime/run_cam.py",
  "raw_evidence": "https://github.com/TTolsun/camera-hal-sdd-generator/tree/main/examples/libcamera/validation/issue211/runs/20261031-wsl-cam-3",
  "buffer_metadata": [
    [
      {
        "buffer_sequence": 0,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 434,
        "point": "buffer-metadata",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 434
      },
      {
        "buffer_sequence": 1,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 434,
        "point": "buffer-metadata",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 434
      },
      {
        "buffer_sequence": 2,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 434,
        "point": "buffer-metadata",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 434
      }
    ],
    [
      {
        "buffer_sequence": 0,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 449,
        "point": "buffer-metadata",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 449
      },
      {
        "buffer_sequence": 1,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 449,
        "point": "buffer-metadata",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 449
      },
      {
        "buffer_sequence": 2,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 449,
        "point": "buffer-metadata",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 449
      }
    ],
    [
      {
        "buffer_sequence": 0,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 464,
        "point": "buffer-metadata",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 464
      },
      {
        "buffer_sequence": 1,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 464,
        "point": "buffer-metadata",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 464
      },
      {
        "buffer_sequence": 2,
        "buffer_status": 0,
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:503",
        "pid": 464,
        "point": "buffer-metadata",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 464
      }
    ]
  ],
  "pretrial_kernel": "6.18.33.2-microsoft-standard-WSL2",
  "pretrial_udmabuf": false,
  "pretrial_dmabuf_heaps": false,
  "pretrial_provider_devices_present": false,
  "source_unmodified": true,
  "kernel_trial_authorized_by_user": true,
  "request_events": [
    [
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 434,
        "point": "callback-entry",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 437
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 434,
        "point": "callback-entry",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 437
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 434,
        "point": "frame-processed",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 434
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 434,
        "point": "callback-entry",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 437
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 434,
        "point": "frame-processed",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 434
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 434,
        "point": "frame-processed",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 434
      }
    ],
    [
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 449,
        "point": "callback-entry",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 452
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 449,
        "point": "callback-entry",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 452
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 449,
        "point": "frame-processed",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 449
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 449,
        "point": "callback-entry",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 452
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 449,
        "point": "frame-processed",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 449
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 449,
        "point": "frame-processed",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 449
      }
    ],
    [
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 464,
        "point": "callback-entry",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 467
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 464,
        "point": "callback-entry",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 467
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 464,
        "point": "frame-processed",
        "request": "0x5555556794f0",
        "sequence": 0,
        "status": 1,
        "tid": 464
      },
      {
        "cookie": 0,
        "location": "CameraSession::requestComplete",
        "pid": 464,
        "point": "callback-entry",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 467
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 464,
        "point": "frame-processed",
        "request": "0x5555556793b0",
        "sequence": 1,
        "status": 1,
        "tid": 464
      },
      {
        "cookie": 0,
        "location": "/home/baboess/.cache/issue211-runtime-D6sfkcnF/source/src/apps/cam/camera_session.cpp:535",
        "pid": 464,
        "point": "frame-processed",
        "request": "0x555555679450",
        "sequence": 2,
        "status": 1,
        "tid": 464
      }
    ]
  ],
  "main_tid": [
    434,
    449,
    464
  ],
  "observation_points": {
    "callback-entry": "CameraSession::requestComplete entry",
    "frame-processed": "CameraSession::processRequest immediately before captureCount_++",
    "buffer-metadata": "CameraSession::processRequest after reading FrameMetadata"
  }
}

