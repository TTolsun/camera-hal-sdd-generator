"""빌드 시스템이 만든 compile DB 를 libclang 이 읽을 수 있게 정규화하는 규칙."""

from pathlib import Path

import pytest

from sdd import compdb


def test_상대_경로를_directory_기준_절대_경로로_바꾼다(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    entries = [{
        "directory": str(build),
        "file": "../src/camera.cpp",
        "command": "clang++ -I../include -isystem subdir -DFOO=1 -c ../src/camera.cpp",
    }]
    out = compdb.normalize(entries)
    argv = out[0]["arguments"]
    assert out[0]["file"] == str((build / "../src/camera.cpp").resolve())
    assert "-I" + str((build / "../include").resolve()) in argv
    index = argv.index("-isystem")
    assert argv[index + 1] == str((build / "subdir").resolve())
    assert "-DFOO=1" in argv
    assert f"-working-directory={build.resolve()}" in argv
    assert not any(a.startswith("-resource-dir") for a in argv)   # clang 없이도 경로 정규화는 된다
    assert entries[0]["command"].startswith("clang++")            # 원본은 바꾸지 않는다


def test_resource_dir_를_지정하면_인자에_채운다(tmp_path):
    entries = [{"directory": str(tmp_path), "file": "a.cpp", "arguments": ["clang++", "-c", "a.cpp"]}]
    out = compdb.normalize(entries, resource_dir=Path("/opt/clang/lib/clang/18"))
    assert any(a.startswith("-resource-dir=") for a in out[0]["arguments"])


def test_응답_파일은_정규화를_거부한다(tmp_path):
    entries = [{"directory": str(tmp_path), "file": "a.cpp", "arguments": ["clang++", "@flags.rsp", "a.cpp"]}]
    with pytest.raises(RuntimeError, match="응답 파일"):
        compdb.normalize(entries)


def test_sysroot_등호_형식도_절대_경로가_된다(tmp_path):
    entries = [{"directory": str(tmp_path), "file": "a.cpp",
                "arguments": ["clang++", "--sysroot=ndk/sysroot", "-c", "a.cpp"]}]
    out = compdb.normalize(entries)
    assert "--sysroot=" + str((tmp_path / "ndk/sysroot").resolve()) in out[0]["arguments"]


def test_ccache_wrapper_를_떼고_실제_컴파일러를_남긴다(tmp_path):
    entries = [{"directory": str(tmp_path), "file": "jni/a.cpp",
                "command": "ccache /ndk/bin/clang++ -Ijni -c jni/a.cpp"}]
    out = compdb.normalize(entries)
    assert out[0]["arguments"][0] == "/ndk/bin/clang++"
    assert compdb.compiler_of(entries[0]) == "/ndk/bin/clang++"


def test_정규화를_반복해도_인자가_늘지_않는다(tmp_path):
    entries = [{"directory": str(tmp_path), "file": "a.cpp", "arguments": ["clang++", "-Iinc", "-c", "a.cpp"]}]
    once = compdb.normalize(entries, resource_dir=Path("/opt/clang/lib/clang/18"))
    twice = compdb.normalize(once, resource_dir=Path("/opt/clang/lib/clang/18"))
    assert once == twice
    assert compdb.is_normalized(once) and not compdb.is_normalized(entries)


def test_clang_을_실행하지_못하면_설정할_항목을_알린다():
    with pytest.raises(RuntimeError, match="source.ndk_build.clang"):
        compdb.clang_resource_dir("no-such-clang-for-sdd-test")
