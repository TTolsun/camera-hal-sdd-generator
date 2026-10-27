"""Architectural dependency direction includes imports inside functions."""
import ast
import importlib.util
from pathlib import Path
from graphlib import TopologicalSorter

import pytest


@pytest.mark.parametrize('module', [
    'generate', 'generated_design', 'generated_visuals', 'design_reuse', 'update', 'provenance',
    'design_request', 'design_response', 'design_execution', 'design_compat', 'design_trials',
])
def test_core_metadata_consumers_do_not_import_html_renderers(module):
    path = Path(__file__).resolve().parents[1] / 'src' / 'sdd' / (module + '.py')
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.ImportFrom):
            target = (importlib.util.resolve_name('.' * node.level + (node.module or ''), 'sdd')
                      if node.level else node.module or '')
            assert target not in {'sdd.export_html', 'sdd.export_site'}, (module, node.lineno, target)
            if target == 'sdd':
                assert not {'export_html', 'export_site'} & {alias.name for alias in node.names}
        elif isinstance(node, ast.Import):
            assert not {'sdd.export_html', 'sdd.export_site'} & {alias.name for alias in node.names}


def test_runtime_modules_have_no_import_cycle():
    root = Path(__file__).resolve().parents[1] / 'src' / 'sdd'
    graph = {}
    for path in root.rglob('*.py'):
        module = 'sdd.' + '.'.join(path.relative_to(root).with_suffix('').parts)
        package = module.rpartition('.')[0]
        if path.name == '__init__.py':
            module = package
        tree = ast.parse(path.read_text(encoding='utf-8'))
        # An executable entry point is not a library dependency.
        tree.body = [n for n in tree.body if not (isinstance(n, ast.If) and
                     isinstance(n.test, ast.Compare) and
                     isinstance(n.test.left, ast.Name) and n.test.left.id == '__name__')]
        edges = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = (importlib.util.resolve_name('.' * node.level + (node.module or ''), package)
                          if node.level else node.module or '')
                if target == 'sdd' or target.startswith('sdd.'):
                    edges.add(target)
                    edges.update(target + '.' + a.name for a in node.names)
            elif isinstance(node, ast.Import):
                edges.update(a.name for a in node.names if a.name.startswith('sdd.'))
        graph[module] = edges - {module}
    graph = {module: edges & graph.keys() for module, edges in graph.items()}
    tuple(TopologicalSorter(graph).static_order())


@pytest.mark.parametrize('module', ['design_response', 'design_compat', 'design_reuse'])
def test_design_decisions_do_not_access_external_services_or_outputs(module):
    root = Path(__file__).resolve().parents[1] / 'src' / 'sdd'
    tree = ast.parse((root / (module + '.py')).read_text(encoding='utf-8'))
    forbidden = {'subprocess', 'pathlib', 'urllib', 'http', 'socket', 'os',
                 'llm', 'cli_agent', 'source_git', 'config', 'export_site', 'export_html',
                 'design_execution', 'design_request', 'design_trials', 'answer_cache', 'design_replay'}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not forbidden.intersection((node.module or '').split('.')), (module, node.lineno)
        elif isinstance(node, ast.Import):
            assert not any(forbidden.intersection(a.name.split('.')) for a in node.names), (module, node.lineno)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {'open', '__import__', 'eval', 'exec'}, (module, node.lineno)
            elif isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {'read_text', 'read_bytes', 'write_text', 'write_bytes',
                                              'save', 'load', 'chat'}, (module, node.lineno)


def test_raw_configuration_access_stays_at_documented_boundaries():
    root = Path(__file__).resolve().parents[1] / 'src' / 'sdd'
    # Schema interpretation, identity/snapshot IO, and project-specific schemas.
    # Counts are a ceiling, so new business consumers cannot hide in an allowed file.
    limits = {'config': 7, 'trial_workspace': 6, 'localization_cli': 1,
              'automation': 2, 'idle_review': 1, 'site_build': 1,
              'evaluate_pipeline': 1, 'evaluate_reader': 2, 'compdb': 2}
    for path in root.glob('*.py'):
        accesses = [n for n in ast.walk(ast.parse(path.read_text(encoding='utf-8')))
                    if isinstance(n, ast.Attribute) and n.attr == 'raw'
                    and isinstance(n.value, ast.Name) and n.value.id in {'cfg', 'config', 'trial', 'self'}]
        assert len(accesses) <= limits.get(path.stem, 0), (path.name, [n.lineno for n in accesses])


def test_generation_core_does_not_interpret_comparison_or_replay_storage():
    root = Path(__file__).resolve().parents[1] / 'src' / 'sdd'
    for module in ('generated_design', 'design_execution', 'design_request', 'design_response'):
        tree = ast.parse((root / (module + '.py')).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {'answer_cache', 'design_replay', 'call_records', 'response_bundle'}
