"""Run the source-bound Signal experiment in WSL; retain every attempt."""
import argparse
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
WORK=HERE.parents[3]/'build/issue252'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',required=True,type=int)
    parser.add_argument('--build-proof',type=Path,default=WORK/'build-provenance-signal.json')
    args=parser.parse_args()
    out=WORK/f'signal-probe-{args.attempt:02d}'
    out.mkdir()
    def wslpath(path):
        return subprocess.check_output(['wsl.exe','-d','Ubuntu','--exec','wslpath','-u',path.as_posix()],text=True,encoding='utf-8').strip()
    argv=['wsl.exe','-d','Ubuntu','--exec','python3',wslpath(HERE/'signal_probe_driver.py'),
          wslpath(args.build_proof.resolve()),wslpath(HERE/'signal_before_return.cpp'),wslpath(out)]
    executed=subprocess.run(argv,capture_output=True)
    (out/'driver.stdout').write_bytes(executed.stdout)
    (out/'driver.stderr').write_bytes(executed.stderr)
    print(executed.stdout.decode('utf-8',errors='replace'))
    print(executed.stderr.decode('utf-8',errors='replace'))
    raise SystemExit(executed.returncode)


if __name__=='__main__':main()
