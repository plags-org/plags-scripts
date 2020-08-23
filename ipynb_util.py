import enum
import json
import sys
from typing import List

from ipynb_metadata import COMMON_METADATA

if (sys.version_info.major, sys.version_info.minor) < (3, 7):
    print('[ERROR] This script requires Python >= 3.7.')
    sys.exit(1)

class NotebookCellType(enum.Enum):
    RAW = 'raw'
    CODE = 'code'
    MARKDOWN = 'markdown'

def normalized_cells(cells):
    for c in cells:
        assert 'cell_type' in c, f"Invalid notebook: above cell in {notebook_path} has no 'cell_type' property."
        assert any(x.value == c['cell_type'] for x in NotebookCellType), \
            f"Invalid notebook: above cell in {notebook_path} has invalid 'cell_type' property: {c['cell_type']}"
        assert 'source' in c, f"Invalid notebook: above cell in {notebook_path} has no 'source' property."
        yield (NotebookCellType(c['cell_type']), ''.join(c['source']))

def load_cells(notebook_path: str, outputs_dropped=False):
    with open(notebook_path, encoding='utf-8') as f:
        data = json.load(f)
    assert 'metadata' in data, f"Invalid notebook: {notebook_path} has no 'metadata' property."
    assert 'cells' in data, f"Invalid notebook: {notebook_path} has no 'cells' property."
    if outputs_dropped:
        for c in data['cells']:
            assert 'cell_type' in c, f"Invalid notebook: above cell in {notebook_path} has no 'cell_type' property."
            assert any(x.value == c['cell_type'] for x in NotebookCellType), \
                f"Invalid notebook: above cell in {notebook_path} has invalid 'cell_type' property: {c['cell_type']}"
            if c['cell_type'] == NotebookCellType.CODE:
                c['execution_count'] = None
                c['outputs'] = []
    return data['cells'], data['metadata']

def save_as_notebook(notebook_path: str, cells: List[dict], metadata: dict):
    ipynb = {
        'cells': cells,
        'metadata': metadata,
        'nbformat': 4,
        'nbformat_minor': 4
    }
    with open(notebook_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(ipynb, f, indent=1, ensure_ascii=False)
        f.write('\n')

def save_markdown_as_ipynb(notebook_path: str, markdown_lines: List[str]):
    cells = [{
        'cell_type': 'markdown',
        'metadata': {},
        'source': markdown_lines
    }]
    save_as_notebook(notebook_path, cells, COMMON_METADATA)
