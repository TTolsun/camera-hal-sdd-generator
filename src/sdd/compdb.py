"""compile_commands.json 확보와 해석.

NDK-build 환경에서는 `ndk-build compile_commands.json` 이 compile DB 를 만든다.
여기서 나온 -I / -D / --sysroot 가 clang-uml 과 libclang 의 #ifdef 해석 기준이 된다.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import Config

# shlex 가 posix=False 로 나눈 토큰을 감싸고 있을 수 있는 따옴표 (큰따옴표, 작은따옴표)
_QUOTE_CHARS = "\x22\x27"
# NDK_CCACHE 등으로 실제 컴파일러 앞에 붙는 실행 파일
_WRAPPERS = {"ccache", "sccache", "distcc", "icecc"}
# compile DB 에서 꺼낸 컴파일러를 실행해도 되는 이름: clang, clang++, clang-18, clang++.exe 등
_CLANG_NAME = re.compile(r"^clang(\+\+)?(-\d+)?(\.exe)?$", re.IGNORECASE)


def load_entries(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: compile DB 는 JSON 배열이어야 합니다.")
    return data


def generate_with_ndk(cfg: Config) -> Path:
    ndk = cfg.ndk_build
    if not ndk.get("enabled"):
        raise RuntimeError("source.ndk_build.enabled 가 false 이고 compile DB 도 없습니다.")
    project_dir = Path(ndk.get("project_dir") or cfg.source_root)
    cmd = ["ndk-build", "compile_commands.json", *[str(a) for a in (ndk.get("args") or [])]]
    subprocess.run(cmd, cwd=project_dir, check=True)
    return normalize_ndk(cfg)


def normalize_ndk(cfg: Config, raw: Path | None = None) -> Path:
    """ndk-build 가 쓴 DB(raw, 생략하면 방금 ndk-build 가 쓴 자리)를 정규화한 파일 경로를 돌려준다.

    ndk-build 는 LOCAL_PATH 기준 상대 -I 와 상대 file 을 쓰고, pip libclang 에는 NDK clang 의
    내장 헤더(stddef.h 등)가 없다. 그대로 넘기면 Meson DB 때처럼 모든 TU 가 파싱에 실패한다.
    원본은 고치지 않는다. 원본이 소스 저장소에 있으면 작업 트리가 바뀌어 `sdd update` 가 멈추기 때문이다.
    """
    if raw is None:
        project_dir = Path(cfg.ndk_build.get("project_dir") or cfg.source_root)
        # ndk-build 는 NDK_PROJECT_PATH 아래에 compile_commands.json 을 쓴다.
        raw = next((c for c in (project_dir / "compile_commands.json", cfg.compile_commands) if c.exists()), None)
        if raw is None:
            raise FileNotFoundError("ndk-build 를 실행했지만 compile_commands.json 을 찾지 못했습니다.")
    entries = load_entries(raw)
    if not entries:
        raise RuntimeError(f"{raw}: ndk-build 가 만든 compile DB 가 비어 있습니다.")
    normalized = normalize(entries, clang_resource_dir(_trusted_clang(cfg, entries[0])))
    out = cfg.compile_commands
    if raw.resolve() == out.resolve():
        out = _generated_compdb(cfg)
        if raw.resolve() == out.resolve():
            raise RuntimeError(f"source.compile_commands 가 정규화본을 쓰는 자리({out})를 가리킵니다. "
                               "원본을 덮어쓰지 않도록 ndk-build 원본 DB 는 다른 경로에 두세요.")
    _write_atomic(out, json.dumps(normalized, ensure_ascii=False, indent=1))
    return out


def _generated_compdb(cfg: Config) -> Path:
    """원본 대신 정규화본을 둘 자리. clang-uml 은 지정한 디렉터리의 compile_commands.json 만 읽는다."""
    directory = cfg.build_dir / "compdb"
    # 저장소에 build/compdb 가 다른 곳을 가리키는 symlink 로 들어 있으면 그 너머의 파일을 덮게 된다.
    if directory.exists() and directory.resolve().parent != cfg.build_dir.resolve():
        raise RuntimeError(f"정규화한 compile DB 를 쓸 디렉터리가 build 디렉터리 밖을 가리킵니다: {directory}")
    return directory / "compile_commands.json"


def _trusted_clang(cfg: Config, entry: dict[str, Any]) -> str:
    """내장 헤더 위치를 물을 clang. DB 에 적힌 실행 파일은 이름이 clang 일 때만 실행한다."""
    if cfg.ndk_build.get("clang"):
        return str(cfg.ndk_build["clang"])
    compiler = compiler_of(entry)
    if not _CLANG_NAME.match(Path(compiler).name):
        raise RuntimeError(f"compile DB 의 컴파일러가 clang 이 아니라 실행하지 않습니다: {compiler}. "
                           "NDK clang 경로를 source.ndk_build.clang 으로 지정하세요.")
    return compiler


def _write_atomic(path: Path, text: str) -> None:
    # 고정된 .tmp 이름은 미리 놓인 symlink 를 따라 다른 파일을 덮을 수 있어, 같은 디렉터리에 새 이름으로 만든다.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def generate_simple(cfg: Config) -> Path:
    """ndk-build 없이 compile DB 를 만든다. source.simple_compdb.flags 를 모든 .cpp 에 같은 플래그로 적용한다.

    NDK 트리가 아닌 디렉터리(예: AOSP 에서 떼어 낸 HAL, examples/)를 돌릴 때 쓴다.
    -D 와 -I 를 사람이 적어야 하므로 실제 빌드 구성과 어긋날 수 있다. 가능하면 ndk-build 경로를 쓴다.
    """
    simple = (cfg.raw.get("source", {}) or {}).get("simple_compdb") or {}
    compiler = str(simple.get("compiler", "clang++"))
    root = cfg.source_root.resolve()
    # -I / -isystem 뒤의 상대 경로는 소스 루트 기준으로 절대 경로로 바꾼다. libclang 은 directory 로 chdir 하지 않는다.
    flags: list[str] = []
    raw_flags = [str(f) for f in (simple.get("flags") or [])]
    for i, tok in enumerate(raw_flags):
        prev = raw_flags[i - 1] if i else ""
        if prev in ("-I", "-isystem", "-iquote") and not Path(tok).is_absolute():
            tok = (root / tok).resolve().as_posix()
        elif tok.startswith("-I") and len(tok) > 2 and not Path(tok[2:]).is_absolute():
            tok = "-I" + (root / tok[2:]).resolve().as_posix()
        flags.append(tok)
    entries = []
    for src in sorted(root.rglob("*")):
        if src.suffix.lower() not in (".cpp", ".cc", ".c") or any(p in ("build", "obj", "libs") for p in src.relative_to(root).parts):
            continue
        entries.append({
            "directory": root.as_posix(),
            "file": src.as_posix(),
            "arguments": [compiler, *flags, "-I" + root.as_posix(), "-c", src.as_posix()],
        })
    cfg.compile_commands.parent.mkdir(parents=True, exist_ok=True)
    cfg.compile_commands.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg.compile_commands


def _absolute_paths(argv: list[str], directory: Path) -> list[str]:
    """컴파일 인자의 상대 경로를 entry 의 directory 기준 절대 경로로 바꾼다.

    libclang 은 compile DB 의 directory 로 chdir 하지 않으므로, 상대 -I 가 남아 있으면
    다른 디렉터리에서 실행할 때 헤더를 찾지 못한다 (libcamera 실측: TU 171 개 전부 파싱 실패).
    """
    options = ("-include-pch", "-isystem", "-iquote", "-idirafter", "-imacros", "-include",
               "-isysroot", "-I", "-F")

    def resolve(value: str) -> str:
        path = Path(value)
        return str((directory / path).resolve()) if not path.is_absolute() else value

    result: list[str] = []
    pending = False
    for token in argv:
        if pending:
            result.append(resolve(token))
            pending = False
        elif token in options:
            result.append(token)
            pending = True
        elif token.startswith("--sysroot="):
            result.append("--sysroot=" + resolve(token.split("=", 1)[1]))
        elif token.startswith("@"):
            raise RuntimeError("응답 파일(@...)을 먼저 풀어야 compile DB 를 정규화할 수 있습니다.")
        else:
            for option in options:
                if token.startswith(option) and len(token) > len(option):
                    result.append(option + resolve(token[len(option):]))
                    break
            else:
                result.append(token)
    if pending:
        raise RuntimeError("컴파일 옵션 뒤에 와야 할 경로가 없습니다.")
    return result


def clang_resource_dir(clang: str = "clang") -> Path:
    """clang 내장 헤더 디렉터리. pip libclang 휠에는 stddef.h 같은 내장 헤더가 없다."""
    try:
        output = subprocess.check_output([clang, "-print-resource-dir"], text=True)
    except (OSError, subprocess.CalledProcessError) as e:
        raise RuntimeError(f"clang 내장 헤더 위치를 확인하지 못했습니다 ({clang}): {e}. "
                           "NDK clang 경로를 source.ndk_build.clang 으로 지정하세요.") from e
    resource = Path(output.strip()).resolve()
    if not (resource / "include" / "stddef.h").is_file():
        raise RuntimeError(f"clang 내장 헤더가 없습니다: {resource}")
    return resource


def _strip_wrappers(argv: list[str]) -> list[str]:
    """ccache 같은 컴파일러 wrapper 를 앞에서 뗀다. 남겨 두면 실제 컴파일러가 입력 파일로 해석된다."""
    i = 0
    while i < len(argv) - 1 and Path(argv[i]).stem.lower() in _WRAPPERS:
        i += 1
    return argv[i:]


def compiler_of(entry: dict[str, Any]) -> str:
    argv = _strip_wrappers(_argv(entry))
    if not argv:
        raise RuntimeError("compile DB 항목에 컴파일러가 없습니다.")
    return argv[0]


def normalize(entries: list[dict[str, Any]], resource_dir: Path | None = None) -> list[dict[str, Any]]:
    """빌드 시스템이 만든 compile DB 를 libclang 이 어디서든 읽을 수 있는 형태로 바꾼다.

    Meson·Soong·CMake 가 만든 DB 공통으로 필요한 두 가지 조정이다.
    1. 상대 경로를 절대 경로로 바꾸고 -working-directory 를 채운다.
    2. resource_dir 가 있으면 -resource-dir 를 채운다 (pip libclang 의 내장 헤더 부재 대응).
    원본 목록은 바꾸지 않고 새 목록을 돌려준다.
    """
    out: list[dict[str, Any]] = []
    for entry in entries:
        directory = Path(str(entry.get("directory", ".")))
        if not directory.is_absolute():
            directory = Path.cwd() / directory
        directory = directory.resolve()
        source = Path(str(entry.get("file", "")))
        if not source.is_absolute():
            source = directory / source
        # 이미 정규화한 DB 를 다시 넘겨도 같은 결과가 나오도록 앞서 채운 값은 지운다.
        # 새 resource_dir 가 없으면 기존 -resource-dir 를 남긴다. 지우면 내장 헤더를 잃는다.
        argv = _absolute_paths(_strip_wrappers(_argv(entry)), directory)
        previous = [a for a in argv if a.startswith("-resource-dir=")]
        argv = [a for a in argv if not a.startswith(("-working-directory=", "-resource-dir="))]
        argv.append(f"-working-directory={directory}")
        if resource_dir is not None:
            argv.append(f"-resource-dir={resource_dir}")
        elif previous:
            argv.append(previous[-1])
        out.append({"directory": str(directory), "file": str(source.resolve()), "arguments": argv})
    return out


def is_normalized(entries: list[dict[str, Any]]) -> bool:
    """모든 항목에 작업 디렉터리와 clang 내장 헤더 위치가 채워져 있는가."""
    def done(argv: list[str]) -> bool:
        return (any(a.startswith("-working-directory=") for a in argv)
                and any(a.startswith("-resource-dir=") for a in argv))
    return bool(entries) and all(done(_argv(e)) for e in entries)


def ensure(cfg: Config, regenerate: bool = False) -> Path:
    if cfg.compile_commands.exists() and not regenerate:
        # 사람이나 CI 가 ndk-build 로 만든 원본 DB 를 그대로 가리키는 경우도 정규화한다.
        if cfg.ndk_build.get("enabled") and not is_normalized(load_entries(cfg.compile_commands)):
            return normalize_ndk(cfg, cfg.compile_commands)
        return cfg.compile_commands
    if (cfg.raw.get("source", {}) or {}).get("simple_compdb"):
        return generate_simple(cfg)
    return generate_with_ndk(cfg)


def _argv(entry: dict[str, Any]) -> list[str]:
    if isinstance(entry.get("arguments"), list):
        return [str(a) for a in entry["arguments"]]
    cmd = str(entry.get("command", ""))
    # Windows 경로의 백슬래시를 보존하기 위해 posix=False 로 나누고 따옴표만 벗긴다.
    posix = os.name != "nt"
    toks = shlex.split(cmd, posix=posix)
    if not posix:
        toks = [
            t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in _QUOTE_CHARS else t
            for t in toks
        ]
    return toks


def _flag_values(argv: list[str], flags: tuple[str, ...]) -> list[str]:
    """-DFOO, -D FOO, -Ipath, -I path, -isystem path, --sysroot=path 형태를 모두 모은다."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        for fl in flags:
            if tok == fl and i + 1 < len(argv):
                out.append(argv[i + 1])
                i += 1
                break
            if tok.startswith(fl) and len(tok) > len(fl):
                rest = tok[len(fl):]
                out.append(rest[1:] if rest.startswith("=") else rest)
                break
        i += 1
    return out


def defines(entries: list[dict[str, Any]]) -> dict[str, str]:
    """-D 매크로를 이름 -> 값 으로 모은다. 값이 없으면 "1"."""
    out: dict[str, str] = {}
    for e in entries:
        for d in _flag_values(_argv(e), ("-D",)):
            name, _, value = d.partition("=")
            if name and name not in out:
                out[name] = value or "1"
    return out


def include_dirs(entries: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for e in entries:
        for inc in _flag_values(_argv(e), ("-I", "-isystem", "-iquote")):
            seen.setdefault(inc, None)
    return list(seen)


def sysroots(entries: list[dict[str, Any]]) -> list[str]:
    seen: dict[str, None] = {}
    for e in entries:
        for s in _flag_values(_argv(e), ("--sysroot", "-isysroot")):
            seen.setdefault(s, None)
    return list(seen)


def translation_units(entries: list[dict[str, Any]]) -> list[Path]:
    out: list[Path] = []
    for e in entries:
        f = Path(str(e.get("file", "")))
        if not f.is_absolute():
            f = Path(str(e.get("directory", "."))) / f
        out.append(f)
    return out


def check(entries: list[dict[str, Any]]) -> list[str]:
    """clang-uml 실행 전에 잡을 수 있는 문제를 경고 문자열로 돌려준다."""
    warnings: list[str] = []
    if not entries:
        warnings.append("compile DB 가 비어 있습니다.")
        return warnings
    for s in sysroots(entries):
        if not Path(s).exists():
            warnings.append(f"sysroot 경로가 없습니다: {s} (NDK 가 이 머신에 설치되어 있는지 확인)")
    missing = [str(p) for p in translation_units(entries) if not p.exists()]
    if missing:
        warnings.append(f"compile DB 의 소스 {len(missing)} 개가 존재하지 않습니다. 예: {missing[0]}")
    return warnings
