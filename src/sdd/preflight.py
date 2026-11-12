"""Local setup checks shared by the CLI and the first-run plan."""

from pathlib import Path
import shutil
from urllib.parse import urlsplit

from . import cli_agent, compdb, extract
from .config import load
from .llm import Agent, AgentError


def doctor(cfg, headers, *, check_endpoint=False):
    ready = True

    def check(label, good, detail):
        nonlocal ready
        ready = ready and good
        print(f"[{'OK' if good else '!!'}] {label}: {detail}")

    check('소스 루트', cfg.source_root.is_dir(), cfg.source_root.as_posix())
    head = extract.git_head(cfg.source_root)
    check('git 소스 커밋', bool(head), head or 'Git과 분석용 체크아웃을 확인하세요.')
    for name, path in [('섹션 설정', cfg.sections_file), ('프롬프트', cfg.prompts_dir),
                       ('템플릿', cfg.templates_dir), ('집필 규칙', cfg.style_dir)]:
        check(name, path.exists(), path.as_posix())
    try:
        from clang.cindex import Index, LibclangError
    except ImportError:
        check('libclang', False, '설치와 라이브러리 버전을 확인하세요.')
    else:
        try:
            Index.create()
            check('libclang', True, '라이브러리 로드 성공. 헤더 파싱은 extract에서 확인합니다.')
        except (OSError, LibclangError):
            check('libclang', False, '설치와 라이브러리 버전을 확인하세요.')
    print(f'[OK] 구조 추출 도구: {extract.structure_backend(cfg)}')
    try:
        if not cfg.compile_commands.is_file():
            remedy = ('sdd compdb를 실행하세요.' if compdb.can_generate(cfg) else
                      '제품 빌드에서 DB와 생성 헤더를 만든 뒤 source.compile_commands를 지정하세요.')
            check('compile DB', False, f'{cfg.compile_commands} ({remedy})')
        else:
            entries = compdb.load_entries(cfg.compile_commands)
            warnings = compdb.check(entries)
            check('compile DB', not warnings, f'{cfg.compile_commands} (TU {len(entries)}개)')
            for warning in warnings:
                print(f'[!!] compile DB: {warning}')
    except (OSError, ValueError, AttributeError, TypeError):
        check('compile DB', False, '빌드에서 만든 JSON 배열과 각 TU의 경로·명령을 확인하세요.')
    if cfg.ndk_build.get('enabled'):
        path = shutil.which('ndk-build')
        project = Path(cfg.ndk_build.get('project_dir') or cfg.source_root)
        check('NDK 빌드 프로젝트', project.is_dir(), str(project))
        if cfg.compile_commands.is_file() and not path:
            print('[..] ndk-build: 설치되지 않았습니다. DB를 다시 만들 때 필요합니다.')
        else:
            check('ndk-build', bool(path), path or 'PATH에 NDK 도구를 추가하세요.')
    for header in headers:
        path = Path(header).resolve()
        check('생성 헤더', path.is_file(), str(path) if path.is_file() else
              f'{path} (제품 빌드에서 헤더를 생성하고 compile DB의 include 경로를 확인하세요.)')
    if not headers:
        print('[..] 생성 헤더: --header로 필요한 파일을 확인하고 extract로 파싱을 확인하세요.')

    def profile(label, agent):
        print(f'[설정] {label}: {agent.label}')
        if agent.kind == 'cli':
            try:
                argv = cli_agent.command(agent)
                # A custom wrapper has no guaranteed non-inference version command.
                detail = ('설정한 실행 파일 확인. wrapper의 동작은 별도 확인하세요.' if agent.command
                          else cli_agent.check(agent))
                check(label + ' 실행 파일', True, f'{Path(argv[0]).name}, {detail}')
            except (OSError, ValueError, RuntimeError):
                check(label + ' 실행 파일', False, 'agent.command, PATH, CLI 설치를 확인하세요.')
            print(f'[..] {label} 외부 접근: 인증·네트워크·모델 권한은 미확인입니다.')
        elif check_endpoint and agent.kind in ('ollama', 'openai-compatible'):
            try:
                check(label + ' 모델 목록', True, Agent(agent).ping())
            except AgentError:
                check(label + ' 모델 목록', False, '엔드포인트, 네트워크, CLI 또는 API 인증 설정을 확인하세요.')
        else:
            print(f'[..] {label} 외부 접근: 확인하지 않았습니다.')

    profile('생성', cfg.agent)
    if path := cfg.paths.get('consistency_profile'):
        profile('독립 검토', load(path).agent)
    elif cfg.paths.get('consistency_file'):
        print('[..] 독립 검토: 별도 paths.consistency_profile이 없습니다. 대조에 기본 에이전트를 사용합니다.')
    else:
        print('[..] 독립 검토: paths.consistency_file과 검토용 CLI 프로필을 지정하세요.')
    print('[설정] 생성·검토 인자와 실행 한도는 generate --plan-only의 로컬 계획에서 확인하세요.')

    from .source_links import source_link_template
    site = cfg.site
    try:
        source_link_template(site)
        link = urlsplit(site.source_url)
        if link.scheme and link.netloc:
            print('[설정] 코드 링크: 형식 확인. 실제 소스 열람과 인증은 미확인입니다.')
        else:
            print('[..] 코드 링크: site.source_url에 코드 열람 주소를 지정하세요.')
    except (RuntimeError, ValueError):
        check('코드 링크', False, 'site.source_link 또는 site.source_link_template을 확인하세요.')
    if site.mermaid:
        print('[..] Mermaid: 지정한 자산을 사용합니다. 실제 로딩은 로컬 미리보기에서 확인하세요.')
    elif site.mermaid_dir:
        from .mermaid_assets import ENTRY
        assets = cfg.root / site.mermaid_dir
        present = (assets / ENTRY).is_file() and (assets / 'chunks').is_dir()
        print('[OK] Mermaid: 동봉 파일 확인.' if present else
              '[..] Mermaid: 로컬 미리보기 전 fetch-mermaid --tarball 또는 사내 미러로 준비하세요.')
    else:
        print('[..] Mermaid: 기본 CDN 설정입니다. 사내 자산을 쓰려면 site.mermaid_dir 또는 site.mermaid를 지정하세요.')
    print('[설정] 게시: doctor에서 수행하지 않습니다. 로컬 확인은 export-site와 verify-site를 사용하세요.')
    print('로컬 필수 항목 확인 완료.' if ready else '표시된 로컬 필수 항목을 수정한 뒤 doctor를 다시 실행하세요.')
    return 0 if ready else 1
