"""Ubuntu: configure a new UVC build and bind generated libclang inputs."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
WORK = ROOT/'build/issue252'
COMMIT = '293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
REQUIRED = dict(pipelines=['uvcvideo'],ipas=[],gstreamer='disabled',test=False,
                cam='enabled',qcam='disabled',documentation='disabled',**{'lc-compliance':'disabled'})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_source(source):
    sha = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    assert sha==COMMIT
    dirty = subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=all'],text=True)
    assert not dirty, 'Source checkout must be clean, including untracked non-ignored files.'
    return sha


def verify_inputs(source,build):
    verify_source(source)
    info = json.loads((build/'meson-info/meson-info.json').read_bytes())
    assert Path(info['directories']['source']).resolve()==source.resolve()
    assert Path(info['directories']['build']).resolve()==build.resolve()
    options = {r['name']:r['value'] for r in json.loads((build/'meson-info/intro-buildoptions.json').read_bytes())}
    assert all(options.get(k)==v for k,v in REQUIRED.items())


def generated_inputs(build):
    suffixes = {'.h','.hpp','.hxx','.inc','.c','.cc','.cpp','.cxx'}
    return {p.relative_to(build).as_posix():digest(p) for p in sorted(build.rglob('*'))
            if p.is_file() and p.suffix in suffixes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',default='fresh')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9-]+',args.attempt)
    source = Path.home()/'work/issue252-libcamera'
    build = source.parent/('issue252-build-'+args.attempt)
    out = WORK/('build-inputs-'+args.attempt)
    record_path = WORK/('build-provenance-'+args.attempt+'.json')
    if build.exists() or out.exists() or record_path.exists():
        raise ValueError('A fresh build and evidence destination are required; preserve prior runs.')
    verify_source(source)
    setup = ['meson','setup',str(build),str(source),'--wrap-mode=nofallback',
             '-Dpipelines=uvcvideo','-Dipas=[]','-Dgstreamer=disabled','-Dtest=false',
             '-Dcam=enabled','-Dqcam=disabled','-Ddocumentation=disabled','-Dlc-compliance=disabled']
    out.mkdir()
    configured = subprocess.run(setup,capture_output=True,text=True)
    (out/'meson.stdout.txt').write_text(configured.stdout,encoding='utf-8')
    (out/'meson.stderr.txt').write_text(configured.stderr,encoding='utf-8')
    assert configured.returncode==0, configured.stderr
    verify_inputs(source,build)
    command = ['ninja','-C',str(build),'-j','4']
    result = subprocess.run(command,capture_output=True,text=True)
    (out/'ninja.stdout.txt').write_text(result.stdout,encoding='utf-8')
    (out/'ninja.stderr.txt').write_text(result.stderr,encoding='utf-8')
    assert result.returncode==0, result.stderr
    verify_inputs(source,build)
    files = dict(compile_commands=build/'compile_commands.json',
                 buildoptions=build/'meson-info/intro-buildoptions.json',
                 meson_info=build/'meson-info/meson-info.json',
                 project_info=build/'meson-info/intro-projectinfo.json',
                 meson_log=build/'meson-logs/meson-log.txt')
    bindings = {}
    for key,path in files.items():
        target = out/(key+path.suffix)
        target.write_bytes(path.read_bytes())
        bindings[key] = dict(file=target.relative_to(WORK).as_posix(),sha256=digest(target))
    generated = generated_inputs(build)
    for rel,sha in generated.items():
        target = out/'generated'/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((build/rel).read_bytes())
        assert digest(target)==sha
    library=build/'src/libcamera/base/libcamera-base.so'
    outputs=dict(libcamera_base=dict(path=str(library.resolve()),sha256=digest(library)))
    record = dict(outputs=outputs,schema=1,status='passed',source_commit=COMMIT,source=str(source.resolve()),build=str(build.resolve()),
                  required_options=REQUIRED,inputs=bindings,generated_inputs=generated,command=command,exit_code=result.returncode,
                  source_clean_before_and_after=True,captured_at=datetime.now(timezone.utc).isoformat(),
                  setup_command=setup,setup_exit_code=configured.returncode,fresh_configuration=True,full_rebuild=True,
                  scope='Fresh source-pinned UVC build; auxiliary lc-compliance disabled. No physical camera, DMA correctness or internal HAL validation.')
    record_path.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record),flush=True)


if __name__=='__main__':
    main()
