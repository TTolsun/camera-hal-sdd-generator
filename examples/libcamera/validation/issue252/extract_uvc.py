"""Run in Ubuntu against the fresh UVC build; retain its facts separately."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import yaml
from capture_build import verify_inputs, digest, generated_inputs

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'src'))
from sdd.config import load
from sdd import compdb, extract
from sdd.facts.model import KnowledgeModel


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',choices=['initial','gcc-extension','verified','verified-clean','final'],default='final')
    args = parser.parse_args()
    work = ROOT/'build/issue252'
    out = work/('uvc-extraction' if args.attempt=='initial' else 'uvc-extraction-'+args.attempt)
    out.mkdir(exist_ok=False)
    source = Path.home()/'work/issue252-libcamera'
    provenance_bytes = (work/'build-provenance-fresh.json').read_bytes()
    provenance = json.loads(provenance_bytes)
    build = Path(provenance['build'])
    assert provenance['status']=='passed' and provenance['source_commit']=='293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
    assert provenance['full_rebuild'] and provenance['fresh_configuration'] and provenance['setup_exit_code']==0
    assert Path(provenance['source']).resolve()==source.resolve()
    verify_inputs(source,build)
    assert digest(build/'compile_commands.json')==provenance['inputs']['compile_commands']['sha256']
    assert digest(build/'meson-info/intro-buildoptions.json')==provenance['inputs']['buildoptions']['sha256']
    assert generated_inputs(build)==provenance['generated_inputs']
    sha = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    assert sha=='293d751a814e0d4c34e85ad457ccd9d5eefd1a61'
    entries = compdb.load_entries(build/'compile_commands.json')
    normalized = compdb.normalize(entries,compdb.clang_resource_dir('clang'))
    adjustments = []
    if args.attempt in ['gcc-extension','verified','verified-clean','final']:
        for entry in normalized:
            if Path(entry['file']).name=='controls.cpp':
                entry['arguments'].append('-Wno-error=c99-designator')
                adjustments.append(dict(file=entry['file'],flag='-Wno-error=c99-designator',
                    reason='The actual GCC build accepts GNU C++ array designators; libclang reports the supported extension as a warning promoted by -Werror. Preserve that warning and all other parse errors.'))
    (out/'compile_commands.json').write_text(json.dumps(normalized),encoding='utf-8')
    cfg = dict(source=dict(root=str(source),compile_commands=str(out/'compile_commands.json'),
                           exclude=['subprojects/**','test/**','build/**'],ndk_build=dict(enabled=False)),
               output=dict(facts_dir=str(out/'facts'),sdd_dir=str(out/'unused-manuscripts')),
               paths=dict(sections_file=str(out/'sections.yaml'),scenarios_file=str(out/'scenarios.yaml')),
               facts=dict(package_depth=3),tools=dict(clang_uml='none'))
    (out/'sections.yaml').write_text('sections: []\n')
    (out/'scenarios.yaml').write_text('scenarios: []\n')
    (out/'extract.yaml').write_text(yaml.safe_dump(cfg),encoding='utf-8')
    extract.run(load(out/'extract.yaml'))
    verify_inputs(source,build)
    assert digest(build/'compile_commands.json')==provenance['inputs']['compile_commands']['sha256']
    assert generated_inputs(build)==provenance['generated_inputs']
    model = KnowledgeModel.load(out/'facts/facts.json')
    assert model.meta['source_commit']==sha
    assert model.meta['translation_units']==len(normalized)==135
    assert model.meta['comments']['tus']==135 and model.meta['comments']['errors']==0
    expected = ['libcamera::Camera','libcamera::Request','libcamera::PipelineHandler',
                'libcamera::V4L2Device','libcamera::V4L2VideoDevice','libcamera::PipelineHandlerUVC']
    assert all(name in model.classes for name in expected)
    report = dict(translation_units=model.meta['translation_units'],parse_stats=model.meta['comments'],source_commit=sha,compile_db_sha256=hashlib.sha256((out/'compile_commands.json').read_bytes()).hexdigest(),
                  analysis_only_adjustments=adjustments,
                  build_provenance_sha256=hashlib.sha256(provenance_bytes).hexdigest(),source_clean_before_and_after=True,
                  facts_sha256=hashlib.sha256((out/'facts/facts.json').read_bytes()).hexdigest(),
                  classes=len(model.classes),functions=len(model.functions),required_classes=expected,
                  scope='Fresh UVC-only structural extraction; does not replace the retained full-build publication facts.',
                  hardware_execution=False,human_review='pending')
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
