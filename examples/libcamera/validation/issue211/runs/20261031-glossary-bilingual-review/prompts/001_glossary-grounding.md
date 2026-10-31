<!-- system -->
Review glossary definitions for entailment, precision and reader comprehension. No tools. Return JSON.

<!-- user -->
Compare these actual selected-Claude Korean definitions with the primary-source excerpts/URLs. NV12 is a format identifier, not an invented expansion; UDMABUF is a driver, not physical DMA proof; generic VM definition must not imply independent kernels per WSL distribution. Report unsupported claims or misleading definitions. Passing is not human approval.
SOURCES
{
  "GNU": {"url": "https://www.gnu.org/", "acronym_url": "https://www.gnu.org/gnu/pronunciation.html", "excerpt": "GNU is an operating system that is free software. GNU is a recursive acronym for GNU's Not Unix."},
  "GCC": {"url": "https://gcc.gnu.org/", "excerpt": "GCC, the GNU Compiler Collection. The GNU Compiler Collection includes front ends for C, C++"},
  "GDB": {"url": "https://www.sourceware.org/gdb/", "excerpt": "GDB: The GNU Project Debugger. Make your program stop on specified conditions. Examine what has happened, when your program has stopped."},
  "NV12": {"url": "https://docs.kernel.org/userspace-api/media/v4l/pixfmt-yuv-planar.html", "excerpt": "V4L2_PIX_FMT_NV12: 8 bits per component; 4:2:0; chroma order Cb, Cr; contiguous, linear. First plane luma; second interleaved chroma."},
  "PR": {"url": "https://docs.github.com/en/pull-requests/reference/pull-requests", "excerpt": "Pull requests are proposals to merge code changes into a project."},
  "UDMABUF": {"url": "https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/drivers/dma-buf/Kconfig", "excerpt": "userspace dmabuf misc driver. A driver to let userspace turn memfd regions into dma-bufs."},
  "VM": {"url": "https://azure.microsoft.com/en-us/resources/cloud-computing-dictionary/what-is-a-virtual-machine", "summary": "A VM is a software-based computer running its own OS and apps. Virtualized resources come from a physical host, which can be a personal device; the definition is not limited to cloud servers."},
  "WSL": {"url": "https://learn.microsoft.com/en-us/windows/wsl/about", "excerpt": "Windows Subsystem for Linux (WSL) is a feature of Windows that allows you to run a Linux environment on your Windows machine"}
}

DEFINITIONS
{
  "terms": [
    {
      "term": "GNU",
      "full": "GNU's Not Unix",
      "definition": "GNU는 자유 소프트웨어로 이루어진 운영체제입니다. 이름은 재귀적 약어로, GNU's Not Unix를 뜻합니다."
    },
    {
      "term": "GCC",
      "full": "GNU Compiler Collection",
      "definition": "C, C++ 등의 프론트엔드를 포함하는 GNU 컴파일러 모음입니다."
    },
    {
      "term": "GDB",
      "full": "GNU Project Debugger",
      "definition": "지정한 조건에서 프로그램을 멈추게 하고, 멈춘 뒤 실행 상태를 살펴볼 수 있는 GNU 디버거입니다."
    },
    {
      "term": "NV12",
      "full": "NV12",
      "definition": "성분당 8비트를 쓰는 4:2:0 포맷입니다. 첫 번째 평면은 휘도(Y)이고, 두 번째 평면에는 Cb와 Cr 값이 한 개씩 번갈아 저장되는 교차 색차 데이터가 들어 있으며, 전체가 선형으로 연속된 메모리에 놓입니다."
    },
    {
      "term": "PR",
      "full": "Pull Request",
      "definition": "코드 변경 사항을 프로젝트에 병합해 달라고 제안하는 요청입니다."
    },
    {
      "term": "UDMABUF",
      "full": "userspace dmabuf misc driver",
      "definition": "Linux 커널의 드라이버 이름으로, 사용자 공간의 memfd 영역을 dma-buf로 바꿔 주는 드라이버입니다."
    },
    {
      "term": "VM",
      "full": "Virtual Machine (가상 머신)",
      "definition": "가상 머신은 물리 컴퓨터의 자원을 가상화하여 소프트웨어로 구현한 컴퓨터이며, 자체 운영체제와 응용 프로그램을 실행합니다. 클라우드 서버에만 해당하지 않으며 개인용 물리 컴퓨터에서도 만들 수 있습니다."
    },
    {
      "term": "WSL",
      "full": "Windows Subsystem for Linux",
      "definition": "Windows의 기능으로, Windows 컴퓨터에서 Linux 환경을 실행할 수 있게 해 줍니다."
    }
  ]
}

ACTUAL ENGLISH CATALOGUE PAIRS (also check translation equivalence)
{
  "GNU": [
    {
      "ko": "GNU는 자유 소프트웨어로 이루어진 운영체제입니다. 이름은 재귀적 약어로, GNU's Not Unix를 뜻합니다.",
      "en": "GNU is an operating system made of free software. Its name is a recursive acronym meaning GNU's Not Unix."
    },
    {
      "ko": "{{0}} (GNU's Not Unix): GNU는 자유 소프트웨어로 이루어진 운영체제입니다. 이름은 재귀적 약어로, GNU's Not Unix를 뜻합니다.",
      "en": "{{0}} (GNU's Not Unix): GNU is an operating system made up of free software. The name is a recursive acronym that stands for GNU's Not Unix."
    }
  ],
  "GCC": [
    {
      "ko": "C, C++ 등의 프론트엔드를 포함하는 GNU 컴파일러 모음입니다.",
      "en": "This is a GNU compiler collection that includes front ends for C, C++, and others."
    },
    {
      "ko": "{{0}} (GNU Compiler Collection): C, C++ 등의 프론트엔드를 포함하는 GNU 컴파일러 모음입니다.",
      "en": "{{0}} (GNU Compiler Collection): A collection of GNU compilers that includes front ends for C, C++, and others."
    }
  ],
  "GDB": [
    {
      "ko": "{{0}} (GNU Project Debugger): 지정한 조건에서 프로그램을 멈추게 하고, 멈춘 뒤 실행 상태를 살펴볼 수 있는 GNU 디버거입니다.",
      "en": "{{0}} (GNU Project Debugger): A GNU debugger that stops a program under specified conditions and lets you examine its execution state after it stops."
    },
    {
      "ko": "지정한 조건에서 프로그램을 멈추게 하고, 멈춘 뒤 실행 상태를 살펴볼 수 있는 GNU 디버거입니다.",
      "en": "A GNU debugger that stops a program under specified conditions and allows inspection of the execution state after it has stopped."
    }
  ],
  "NV12": [
    {
      "ko": "{{0}} (NV12): 성분당 8비트를 쓰는 4:2:0 포맷입니다. 첫 번째 평면은 휘도(Y)이고, 두 번째 평면에는 Cb와 Cr 값이 한 개씩 번갈아 저장되는 교차 색차 데이터가 들어 있으며, 전체가 선형으로 연속된 메모리에 놓입니다.",
      "en": "{{0}} (NV12): The format is 4:2:0 and uses 8 bits per component. The first plane is luminance (Y), and the second plane contains interleaved chroma data in which Cb and Cr values are stored alternately, one at a time, and the whole is placed in linearly contiguous memory."
    },
    {
      "ko": "성분당 8비트를 쓰는 4:2:0 포맷입니다. 첫 번째 평면은 휘도(Y)이고, 두 번째 평면에는 Cb와 Cr 값이 한 개씩 번갈아 저장되는 교차 색차 데이터가 들어 있으며, 전체가 선형으로 연속된 메모리에 놓입니다.",
      "en": "The format is 4:2:0 and uses 8 bits per component. The first plane is luminance (Y), and the second plane contains interleaved chroma data in which Cb and Cr values are stored alternately, one at a time, and the whole is placed in linearly contiguous memory."
    }
  ],
  "PR": [
    {
      "ko": "{{0}} (Pull Request): 코드 변경 사항을 프로젝트에 병합해 달라고 제안하는 요청입니다.",
      "en": "{{0}} (Pull Request): A request proposing that code changes be merged into a project."
    },
    {
      "ko": "코드 변경 사항을 프로젝트에 병합해 달라고 제안하는 요청입니다.",
      "en": "This is a request that proposes merging the code changes into the project."
    }
  ],
  "UDMABUF": [
    {
      "ko": "Linux 커널의 드라이버 이름으로, 사용자 공간의 memfd 영역을 dma-buf로 바꿔 주는 드라이버입니다.",
      "en": "This is the name of a Linux kernel driver that converts memfd regions in user space into dma-buf."
    },
    {
      "ko": "{{0}} (userspace dmabuf misc driver): Linux 커널의 드라이버 이름으로, 사용자 공간의 memfd 영역을 dma-buf로 바꿔 주는 드라이버입니다.",
      "en": "{{0}} (userspace dmabuf misc driver): The name of a Linux kernel driver that converts a memfd region in user space into a dma-buf."
    }
  ],
  "VM": [
    {
      "ko": "{{0}} (Virtual Machine (가상 머신)): 가상 머신은 물리 컴퓨터의 자원을 가상화하여 소프트웨어로 구현한 컴퓨터이며, 자체 운영체제와 응용 프로그램을 실행합니다. 클라우드 서버에만 해당하지 않으며 개인용 물리 컴퓨터에서도 만들 수 있습니다.",
      "en": "{{0}} (Virtual Machine): A virtual machine is a computer implemented in software by virtualizing the resources of a physical computer, and it runs its own operating system and applications. This is not limited to cloud servers, and it can also be created on a personal physical computer."
    },
    {
      "ko": "가상 머신은 물리 컴퓨터의 자원을 가상화하여 소프트웨어로 구현한 컴퓨터이며, 자체 운영체제와 응용 프로그램을 실행합니다. 클라우드 서버에만 해당하지 않으며 개인용 물리 컴퓨터에서도 만들 수 있습니다.",
      "en": "A virtual machine is a computer implemented in software by virtualizing the resources of a physical computer, and it runs its own operating system and applications. This is not limited to cloud servers, and it can also be created on a personal physical computer."
    }
  ],
  "WSL": [
    {
      "ko": "Windows의 기능으로, Windows 컴퓨터에서 Linux 환경을 실행할 수 있게 해 줍니다.",
      "en": "A Windows feature that lets you run a Linux environment on a Windows computer."
    },
    {
      "ko": "{{0}} (Windows Subsystem for Linux): Windows의 기능으로, Windows 컴퓨터에서 Linux 환경을 실행할 수 있게 해 줍니다.",
      "en": "{{0}} (Windows Subsystem for Linux): A Windows feature that allows a Linux environment to run on a Windows computer."
    }
  ]
}

