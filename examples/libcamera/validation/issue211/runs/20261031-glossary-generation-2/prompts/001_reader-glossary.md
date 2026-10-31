<!-- system -->
Write short, clear Korean glossary definitions using only the supplied primary evidence. No tools. # 개발자 가이드 집필 규칙

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


<!-- user -->
Define every supplied term exactly once. One sentence per definition, ending 합니다/입니다. No product support/performance or isolation guarantees. Full is the expansion; NV12 is a format identifier and need not have an invented acronym expansion. UDMABUF is a Linux driver name, not a physical DMA validation claim. NV12 has 8 bits PER COMPONENT, not 8 bits per pixel; state 성분당 8비트 explicitly. VM is a general virtual-machine definition, not a claim that WSL distributions have separate kernels. WSL covers the Windows Linux environment; WSL2 has its existing separate entry.
{"GNU": {"url": "https://www.gnu.org/gnu/about-gnu.html", "excerpt": "GNU is an operating system that is free software. GNU is a recursive acronym for GNU's Not Unix."}, "GCC": {"url": "https://gcc.gnu.org/", "excerpt": "GCC, the GNU Compiler Collection. The GNU Compiler Collection includes front ends for C, C++"}, "GDB": {"url": "https://www.sourceware.org/gdb/", "excerpt": "GDB: The GNU Project Debugger. Make your program stop on specified conditions. Examine what has happened, when your program has stopped."}, "NV12": {"url": "https://docs.kernel.org/userspace-api/media/v4l/pixfmt-yuv-planar.html", "excerpt": "V4L2_PIX_FMT_NV12: 8 bits per component; 4:2:0; chroma order Cb, Cr; contiguous, linear. First plane luma; second interleaved chroma."}, "PR": {"url": "https://docs.github.com/en/pull-requests/reference/pull-requests", "excerpt": "Pull requests are proposals to merge code changes into a project."}, "UDMABUF": {"url": "https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/drivers/dma-buf/Kconfig", "excerpt": "userspace dmabuf misc driver. A driver to let userspace turn memfd regions into dma-bufs."}, "VM": {"url": "https://azure.microsoft.com/en-us/resources/cloud-computing-dictionary/what-is-a-virtual-machine", "excerpt": "A cloud virtual machine is a software-based computer running its own OS and apps on physical servers."}, "WSL": {"url": "https://learn.microsoft.com/en-us/windows/wsl/about", "excerpt": "Windows Subsystem for Linux (WSL) is a feature of Windows that allows you to run a Linux environment on your Windows machine"}}
