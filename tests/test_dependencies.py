"""Architectural dependency direction includes imports inside functions."""
import ast
import importlib.util
from pathlib import Path
from graphlib import TopologicalSorter

import pytest


@pytest.mark.parametrize('module', [
    'generate', 'generated_design', 'generated_visuals', 'design_reuse', 'update', 'provenance',
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
