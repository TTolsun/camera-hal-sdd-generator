"""Linux driver for the bounded libcamera-base scheduling experiment."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

proof=json.loads(Path(sys.argv[1]).read_bytes())
cpp,out=Path(sys.argv[2]),Path(sys.argv[3])
source,build=Path(proof['source']),Path(proof['build'])
library=build/'src/libcamera/base/libcamera-base.so'
git=lambda *args:subprocess.check_output(['git','-C',str(source),*args])
assert git('rev-parse','HEAD').decode().strip()==proof['source_commit']
assert not git('status','--porcelain=v1','--untracked-files=all')
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
library_sha=sha(library)
assert library_sha==proof['outputs']['libcamera_base']['sha256']
assert library.resolve()==Path(proof['outputs']['libcamera_base']['path']).resolve()
argv=['g++','-std=c++20','-pthread','-DLIBCAMERA_BASE_PRIVATE','-I'+str(source/'include'),'-I'+str(build/'include'),
      str(cpp),'-L'+str(library.parent),'-lcamera-base','-Wl,-rpath,'+str(library.parent),
      '-o',str(out/'signal-before-return')]
compiled=subprocess.run(argv,capture_output=True)
(out/'compile.stdout').write_bytes(compiled.stdout)
(out/'compile.stderr').write_bytes(compiled.stderr)
result=dict(schema=1,source_commit=proof['source_commit'],command=argv,
    build_proof_sha256=sha(Path(sys.argv[1])),compile_exit_code=compiled.returncode,source_cpp_sha256=sha(cpp),driver_sha256=sha(Path(__file__)),linked_library_sha256=library_sha,
    scope='Public-source libcamera-base internal Thread/Signal scheduling only; no camera, pointer-lifetime fault injection or hardware capture. A synchronous second slot keeps emit active until the receiver-body marker; it does not observe the receiver function return instruction.')
if compiled.returncode==0:
    env=dict(os.environ,LD_LIBRARY_PATH=str(library.parent))
    resolved=subprocess.run(['ldd',str(out/'signal-before-return')],capture_output=True,env=env)
    (out/'ldd.stdout').write_bytes(resolved.stdout)
    (out/'ldd.stderr').write_bytes(resolved.stderr)
    lines=[line for line in resolved.stdout.decode().splitlines() if 'libcamera-base.so' in line and '=>' in line]
    assert resolved.returncode==0 and len(lines)==1
    loaded=Path(lines[0].split('=>',1)[1].strip().split(' (',1)[0]).resolve()
    assert loaded==library.resolve() and sha(loaded)==library_sha
    result['resolved_runtime_library']=str(loaded)
    executed=subprocess.run([str(out/'signal-before-return')],capture_output=True,timeout=30,env=env)
    (out/'run.stdout').write_bytes(executed.stdout)
    (out/'run.stderr').write_bytes(executed.stderr)
    result.update(run_exit_code=executed.returncode,binary_sha256=sha(out/'signal-before-return'),
        observations=[json.loads(line) for line in executed.stdout.decode().splitlines() if line.startswith('{')])
    result['status']='passed' if executed.returncode==0 and len(result['observations'])==3 and all(row['passed'] for row in result['observations']) else 'failed'
else:
    result['status']='failed'
result['source_clean_after']=not git('status','--porcelain=v1','--untracked-files=all')
result['linked_library_unchanged']=sha(library)==library_sha
if not result['source_clean_after'] or not result['linked_library_unchanged']:
    result['status']='failed'
(out/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
sys.exit(0 if result['status']=='passed' else 1)
