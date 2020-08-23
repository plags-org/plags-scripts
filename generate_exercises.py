import os
import re
import sys
import enum
import shutil
import zipfile
import argparse
import dataclasses
import collections
import copy
from typing import List, Dict, Iterable, Tuple

import json
import hashlib
import logging
logging.getLogger().setLevel('INFO')

import yaml

import ipynb_metadata
import ipynb_util


if (sys.version_info.major, sys.version_info.minor) < (3, 7):
    print('[ERROR] This script requires Python >= 3.7.')
    sys.exit(1)

HOMEDIR = 'exercises'
INTRODCTION_FILE = 'intro.ipynb'

SUBMISSION_CELL_FORMAT = """
##########################################################
##  <[ {exercise_key} ]> 解答セル (Answer cell)
##  このコメントの書き変えを禁ず (Never edit this comment)
##########################################################

{content}""".strip()

REDIRECTION_CELL_FORMAT = """
# このセルではなく {redirect_to} を使ってください
# Use {redirect_to} instead of this cell
""".strip()

AUTOGRADE_DIR = 'autograde'
DOCS_SUBDIR = 'docs'
TESTS_SUBDIR = 'tests'

class FieldKey(enum.Enum):
    WARNING = enum.auto()
    CONTENT = enum.auto()
    STUDENT_CODE_CELL = enum.auto()
    EXPLANATION = enum.auto()
    ANSWER_EXAMPLES = enum.auto()
    STUDENT_TESTS = enum.auto()
    SYSTEM_TEST_CASES_EXECUTE_CELL = enum.auto()
    SYSTEM_TEST_CASES = enum.auto()
    SYSTEM_TEST_REQUIRE_FILES = enum.auto()
    SYSTEM_TEST_SETTING = enum.auto()

class FieldProperty(enum.Flag):
    SINGLE = enum.auto()
    LIST = enum.auto()
    OPTIONAL = enum.auto()
    MARKDOWN_HEADED = enum.auto()
    FILE = enum.auto()
    CODE = enum.auto()

FIELD_PROPERTIES = {
    FieldKey.WARNING: FieldProperty(0),
    FieldKey.CONTENT: FieldProperty.LIST | FieldProperty.MARKDOWN_HEADED,
    FieldKey.STUDENT_CODE_CELL: FieldProperty.SINGLE | FieldProperty.CODE,
    FieldKey.EXPLANATION: FieldProperty.LIST | FieldProperty.MARKDOWN_HEADED | FieldProperty.OPTIONAL,
    FieldKey.ANSWER_EXAMPLES: FieldProperty.LIST | FieldProperty.OPTIONAL,
    FieldKey.STUDENT_TESTS: FieldProperty.LIST | FieldProperty.OPTIONAL,
    FieldKey.SYSTEM_TEST_CASES: FieldProperty.LIST | FieldProperty.FILE,
    FieldKey.SYSTEM_TEST_CASES_EXECUTE_CELL: FieldProperty.SINGLE | FieldProperty.CODE,
    FieldKey.SYSTEM_TEST_REQUIRE_FILES: FieldProperty.CODE | FieldProperty.OPTIONAL,
    FieldKey.SYSTEM_TEST_SETTING: FieldProperty.SINGLE,
}

CellType = ipynb_util.NotebookCellType

class Cell(collections.namedtuple('Cell', ('cell_type', 'source'))):
    def to_ipynb(self):
        if self.cell_type == CellType.CODE:
            return {'cell_type': self.cell_type.value,
                    'execution_count': None,
                    'metadata': {},
                    'outputs': [],
                    'source': self.source.splitlines(True)}
        else:
            return {'cell_type': self.cell_type.value,
                    'metadata': {},
                    'source': self.source.splitlines(True)}

@dataclasses.dataclass
class Exercise:
    key: str        # Key string
    dirpath: str    # Directory path
    version: str    # Version string
    content: List[Cell]                  # The description of exercise, starts with multiple '#'s
    student_code_cell: Cell              # Code cell
    explanation: List[Cell]              # The explanation of exercise, starts with multiple '#'s
    answer_examples: List[Cell]          # List of (filename, content, original code cell)
    student_tests: List[Cell]            # List of cells
    system_test_cases: List[Tuple[str,str,Cell]] # List of (filename, content, original code cell)
    system_test_require_files: List[str] # List of relative paths from dirpath
    system_test_setting: object          # From yaml in raw cell

    def submission_redirection(self):
        m = re.match(r'#[ \t]*redirect-to[ \t]*:[ \t]*(\S+?\.ipynb)', self.student_code_cell.source)
        return m[1] if m else None

    def submission_cell(self):
        redirect_to = self.submission_redirection()
        if redirect_to:
            s = REDIRECTION_CELL_FORMAT.format(redirect_to=redirect_to)
        else:
            s = SUBMISSION_CELL_FORMAT.format(exercise_key=self.key, content=self.student_code_cell.source)
        return Cell(CellType.CODE, s)

def split_file_code_cell(cell: Cell):
    assert cell.cell_type == CellType.CODE
    lines = cell.source.strip().splitlines(keepends=True)
    first_line_regex = r'#+\s+([^/]{1,255})'
    match = re.fullmatch(first_line_regex, lines[0].strip())
    assert match is not None, f'RegExp pattern `{first_line_regex}` does not match the first line of a file code cell: {lines[0]}'
    return (match[1], ''.join(lines[1:]).strip() + '\n', cell)

def load_system_test_require_files(cells: List[Cell]):
    """
    A single code cell containing a Python expression to return a list.
    """
    if not cells:
        return []
    assert len(cells) == 1
    assert cells[0].cell_type == CellType.CODE
    require_files = eval(cells[0].source) if cells[0].source.strip() else []
    assert isinstance(require_files, list)
    assert all(isinstance(x, str) for x in require_files)
    return require_files

def load_system_test_setting(cells: List[Cell]):
    #TODO: more precise validation
    return yaml.safe_load(cells[0].source)

def split_cells(raw_cells: Iterable[dict]):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'
    results = {}
    current_key = None
    cells = []
    for cell_type, source in ipynb_util.normalized_cells(raw_cells):
        logging.debug('[TRACE] %s %s', current_key, repr(source if len(source) <= 64 else source[:64] + ' ...'))
        if source.strip() == '':
            continue

        if cell_type in (CellType.CODE, CellType.RAW):
            assert current_key is not None
            cells.append(Cell(cell_type, source))
            continue
        assert cell_type == CellType.MARKDOWN

        matches = list(re.finditer(CONTENT_TYPE_REGEX, source))
        if len(matches) == 0:
            assert current_key is not None
            cells.append(Cell(cell_type, source))
            continue
        assert len(matches) == 1, f'Multiple FieldKey found in cell `{source}`.'

        if current_key is None:
            current_key = getattr(FieldKey, matches[0][1])
        else:
            results[current_key] = cells
            current_key = getattr(FieldKey, matches[0][1])
            cells = []
    results[current_key] = cells
    return results

def load_exercise(dirpath, exercise_key):
    raw_cells, metadata = ipynb_util.load_cells(os.path.join(dirpath, exercise_key + '.ipynb'))
    dirname = os.path.basename(dirpath)
    version = metadata.get('judge_master', {}).get('version', '')
    exercise_kwargs = {'key': exercise_key, 'dirpath': dirpath, 'version': version}
    for field_key, cells in split_cells(raw_cells).items():
        if field_key in (FieldKey.WARNING, FieldKey.SYSTEM_TEST_CASES_EXECUTE_CELL):
            continue
        logging.debug(f'[TRACE] Validate FieldKey `{field_key.name}`')

        prop = FIELD_PROPERTIES[field_key]
        if (FieldProperty.OPTIONAL | FieldProperty.OPTIONAL) in prop:
            pass
        elif (FieldProperty.OPTIONAL) in prop:
            assert len(cells) <= 1, f'FieldKey `{field_key.name}` must have at most 1 cell but has {len(cells)}.'
        elif FieldProperty.LIST in prop:
            assert len(cells) > 0, f'FieldKey `{field_key.name}` must not be empty.'
        elif FieldProperty.SINGLE in prop:
            assert len(cells) == 1, f'FieldKey `{field_key.name}` must have 1 cell.'

        if FieldProperty.CODE in prop:
            assert all(x.cell_type == CellType.CODE for x in cells), f'FieldKey `{field_key.name}` must have only code cell(s).'

        if len(cells) > 0 and FieldProperty.MARKDOWN_HEADED in prop:
            assert cells[0].cell_type == CellType.MARKDOWN
            first_line_regex = r'#+\s+(.*)'
            first_line = cells[0].source.strip().splitlines()[0]
            assert re.fullmatch(first_line_regex, first_line) is not None, \
                f'The first content cell does not start with a heading in Markdown: `{first_line}`.'

        exercise_kwargs[field_key.name.lower()] = {
            FieldKey.SYSTEM_TEST_SETTING: lambda: load_system_test_setting(cells),
            FieldKey.SYSTEM_TEST_REQUIRE_FILES: lambda: load_system_test_require_files(cells),
            FieldKey.SYSTEM_TEST_CASES: lambda: [split_file_code_cell(x) for x in cells],
            FieldKey.STUDENT_CODE_CELL: lambda: cells[0],
        }.get(field_key, lambda: cells)()

    return Exercise(**exercise_kwargs)

def cleanup_exercise(exercises: Iterable[Exercise]):
    for exercise in exercises:
        filepath = os.path.join(exercise.dirpath, f'{exercise.key}.ipynb')
        cells, metadata = ipynb_util.load_cells(filepath, True)
        cells_new = [Cell(cell_type, source.strip()).to_ipynb() for cell_type, source in ipynb_util.normalized_cells(cells)]
        if commandline_options.renew_version:
            logging.info(f'[INFO] Renew version of {exercise.key}')
            if commandline_options.renew_version == hashlib.sha1:
                exercise_definition = {
                    'content': [x.to_ipynb() for x in exercise.content],
                    'submission_cell': exercise.submission_cell().to_ipynb(),
                    'student_tests': [x.to_ipynb() for x in exercise.student_tests],
                }
                m = hashlib.sha1()
                m.update(json.dumps(exercise_definition).encode())
                exercise.version = m.hexdigest()
            else:
                assert isinstance(commandline_options.renew_version, str)
                exercise.version = commandline_options.renew_version
            metadata = ipynb_metadata.master_metadata(exercise.key, True, exercise.version)
        ipynb_util.save_as_notebook(filepath, cells_new, metadata)

def create_notebook_cells(dirpath: str, is_answer: bool, exercises: Iterable[Exercise]):
    try:
        raw_cells, _ = ipynb_util.load_cells(os.path.join(dirpath, INTRODCTION_FILE))
        cells = [Cell(t, s) for t, s in ipynb_util.normalized_cells(raw_cells)]
    except FileNotFoundError:
        cells = [Cell(CellType.MARKDOWN, f'# {os.path.basename(dirpath)}')]
    for exercise in exercises:
        cells.extend(exercise.content)
        if is_answer:
            cells.extend(exercise.answer_examples)
            cells.append(summarize_testcases(exercise))
            cells.extend(exercise.explanation)
        else:
            cells.append(exercise.submission_cell())
            cells.extend(exercise.student_tests)
    return cells

def summarize_testcases(exercise: Exercise):
    contents = []
    decorator_prefix = '@judge_util.'
    for _, src, _ in exercise.system_test_cases:
        lines = iter(src.splitlines())
        for x in lines:
            if x.startswith(decorator_prefix):
                break
        contents.extend(x for x in lines if not x.startswith(decorator_prefix))
        contents.append('')
    contents.pop()
    return Cell(CellType.CODE, '\n'.join(contents))

def create_exercise_concrete(exercise: Exercise):
    docs_dir, tests_dir = [os.path.join(AUTOGRADE_DIR, exercise.key, d) for d in (DOCS_SUBDIR, TESTS_SUBDIR)]
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(tests_dir, exist_ok=True)

    content_md = ({CellType.MARKDOWN: lambda x: x,
                   CellType.CODE: lambda x: f'---\n\n```python\n{x.strip()}\n```\n\n---'}[c.cell_type](c.source)
                  for c in exercise.content if c.cell_type != CellType.RAW)
    with open(os.path.join(docs_dir, 'ja.md'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n\n'.join(content_md))

    system_test_setting = copy.deepcopy(exercise.system_test_setting)
    system_test_setting['editor']['initial_source'] = exercise.student_code_cell.source
    system_test_setting['editor']['exercise_version'] = exercise.version
    with open(os.path.join(tests_dir, 'setting.yml'), 'w', encoding='utf-8') as f:
        yaml.dump(system_test_setting, stream=f, sort_keys=False)
    for name, content, _ in exercise.system_test_cases:
        with open(os.path.join(tests_dir, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)

    for path in exercise.system_test_require_files:
        dest = os.path.join(tests_dir, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(exercise.dirpath, path), dest)

def create_system_settings(exercises: Iterable[Exercise]):
    shutil.rmtree(AUTOGRADE_DIR, ignore_errors=True)
    for exercise in exercises:
        logging.info(f'[INFO] creating system settings for `{exercise.key}` ...')
        create_exercise_concrete(exercise)

    for exercise_dir in os.listdir(AUTOGRADE_DIR):
        with zipfile.ZipFile(os.path.join(AUTOGRADE_DIR, exercise_dir + '.zip'), 'w', zipfile.ZIP_DEFLATED) as zipf:
            target_dir = os.path.join(AUTOGRADE_DIR, exercise_dir)
            for dirpath, _, files in os.walk(os.path.join(target_dir)):
                arcdirpath = dirpath[len(os.path.join(target_dir, '')):]
                for fname in files:
                    zipf.write(os.path.join(dirpath, fname), os.path.join(arcdirpath, fname))

    logging.info(f'[INFO] creating system settings zip file `{AUTOGRADE_DIR}.zip` ...')
    with zipfile.ZipFile(AUTOGRADE_DIR + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for exercise in exercises:
            zipf.write(os.path.join(exercise.dirpath, exercise.key + '.ipynb'), exercise.key + '.ipynb')
        for fname in os.listdir(AUTOGRADE_DIR):
            if fname.endswith('.zip'):
                zipf.write(os.path.join(AUTOGRADE_DIR, fname), fname)

def generate_artifacts(exercises: Iterable[Exercise]):
    artifact_index = collections.defaultdict(list)
    for exercise in exercises:
        artifact_index[exercise.dirpath].append(exercise)
    for dirpath, exercises in artifact_index.items():
        dirname = os.path.basename(dirpath)
        for is_answer in (False, True):
            cells = [c.to_ipynb() for c in create_notebook_cells(dirpath, is_answer, exercises)]
            if is_answer:
                filepath = os.path.join(dirpath, f'{dirname}.ans.ipynb')
                metadata = ipynb_metadata.COMMON_METADATA
            else:
                filepath = os.path.join(dirpath, f'{dirname}.ipynb')
                key_to_ver = {e.key: e.version for e in exercises if e.submission_redirection() is None}
                metadata = ipynb_metadata.submission_metadata(key_to_ver, True)
            ipynb_util.save_as_notebook(filepath, cells, metadata)
        for e in exercises:
            redirect_to = e.submission_redirection()
            if redirect_to is None:
                continue
            metadata = ipynb_metadata.submission_metadata({e.key: e.version}, True)
            filepath = os.path.join(HOMEDIR, dirname, redirect_to)
            cells, _ = ipynb_util.load_cells(filepath, True)
            assert any(re.search(rf'<\[ {e.key} \]>', line)
                       for c in cells if c['cell_type'] == CellType.CODE.value for line in c['source']), \
                f'{redirect_to} has no answer cell for {e.key}.'
            ipynb_util.save_as_notebook(filepath, cells, metadata)

def main():
    exercises = []
    targets = commandline_options.targets if commandline_options.targets else [os.path.join(HOMEDIR, x) for x in os.listdir(HOMEDIR)]
    target_dirs = [x if os.path.basename(x) else os.path.dirname(x) for x in targets if os.path.isdir(x)]
    for dirpath in sorted(target_dirs):
        exercise_name_index = {}
        dirname = os.path.basename(dirpath)
        for nb in sorted(os.listdir(dirpath)):
            match = re.fullmatch(fr'({dirname}([-_].*))\.ipynb', nb)
            if match is None or nb.endswith('.ans.ipynb'):
                continue
            exercise_key, exercise_subkey = match.groups()
            assert exercise_key not in exercise_name_index, \
                f'[ERROR] Exercise master `{exercise_key}` conflicts with exercise `{exercise_name_index[exercise_key]}`.'
            exercise_name_index[exercise_key] = os.path.join(dirpath, exercise_key)
            logging.info(f'[INFO] Load {dirpath}/{nb}')
            exercises.append(load_exercise(dirpath, exercise_key))

    if commandline_options.dry_run:
        logging.info('[INFO] Dry run')
        for exercise in exercises:
            logging.info(f'[INFO]     - {exercise.key}.ipynb')
        return

    logging.info('[INFO] Start to clean up master notebooks')
    cleanup_exercise(exercises)

    logging.info('[INFO] Start to generate notebooks')
    generate_artifacts(exercises)

    if commandline_options.dump_setting_zip:
        logging.info('[INFO] Start to generate judge system settings')
        create_system_settings(exercises)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose option')
    parser.add_argument('-d', '--dry_run', action='store_true', help='Dry-run option')
    parser.add_argument('-s', '--dump_setting_zip', action='store_true', help='Dump setting zip')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-t', '--targets', nargs='*', default=None, help=f'Specify target directories (default: {HOMEDIR}/*)')
    commandline_options = parser.parse_args()
    if commandline_options.verbose:
        logging.getLogger().setLevel('DEBUG')
    main()
