#!/usr/bin/env python3

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
from typing import List, Iterable, Tuple

import json
import hashlib
import logging
import itertools

import ipynb_metadata
import ipynb_util
import judge_setting

if (sys.version_info.major, sys.version_info.minor) < (3, 7):
    print('[ERROR] This script requires Python >= 3.7.')
    sys.exit(1)

INTRODUCTION_FILE = 'intro.ipynb'
DEADLINE_FILE = 'deadline.json'

CONF_DIR = 'autograde'
CONF_SUBDIR_DOCS = 'docs'
CONF_SUBDIR_TESTS = 'tests'

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

class FieldKey(enum.Enum):
    WARNING = enum.auto()
    CONTENT = enum.auto()
    STUDENT_CODE_CELL = enum.auto()
    EXPLANATION = enum.auto()
    ANSWER_EXAMPLES = enum.auto()
    STUDENT_TESTS = enum.auto()
    SYSTEM_TEST_CASES = enum.auto()
    SYSTEM_TEST_CASES_EXECUTE_CELL = enum.auto()
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
    title: str      # Title string
    content: List[Cell]                  # The description of exercise, starts with multiple '#'s
    student_code_cell: Cell              # Code cell
    explanation: List[Cell]              # The explanation of exercise, starts with multiple '#'s
    answer_examples: List[Cell]          # List of (filename, content, original code cell)
    student_tests: List[Cell]            # List of cells
    system_test_cases: List[Tuple[str,str,Cell]] # List of (filename, content, original code cell)
    system_test_setting: object          # JSON generated from Python code

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

    def generate_setting(self):
        setting = copy.deepcopy(self.system_test_setting)
        setting['metadata'] = {'name': self.key, 'version': self.version}
        setting['front']['initial_source'] = self.student_code_cell.source
        return setting

def split_file_code_cell(cell: Cell):
    assert cell.cell_type == CellType.CODE
    lines = cell.source.strip().splitlines(keepends=True)
    first_line_regex = r'#+\s+([^/]{1,255})'
    match = re.fullmatch(first_line_regex, lines[0].strip())
    assert match is not None, f'RegExp pattern `{first_line_regex}` does not match the first line of a file code cell: {lines[0]}'
    return (match[1], ''.join(lines[1:]).strip() + '\n', cell)

def load_system_test_setting(cells: List[Cell]):
    exec(cells[0].source, {'generate_system_test_setting': judge_setting.generate_system_test_setting})
    return judge_setting.output #TODO: schema validation

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
            m = re.fullmatch(first_line_regex, first_line)
            assert m is not None, f'The first content cell does not start with a heading in Markdown: `{first_line}`.'
            if field_key == FieldKey.CONTENT:
                exercise_kwargs['title'] = m.groups()[0]

        exercise_kwargs[field_key.name.lower()] = {
            FieldKey.SYSTEM_TEST_SETTING: lambda: load_system_test_setting(cells),
            FieldKey.SYSTEM_TEST_CASES: lambda: [split_file_code_cell(x) for x in cells],
            FieldKey.STUDENT_CODE_CELL: lambda: cells[0],
        }.get(field_key, lambda: cells)()

    return Exercise(**exercise_kwargs)

def cleanup_exercise_masters(exercises: Iterable[Exercise], commandline_options):
    for exercise in exercises:
        filepath = os.path.join(exercise.dirpath, f'{exercise.key}.ipynb')
        cells, metadata = ipynb_util.load_cells(filepath, True)
        cells_new = [Cell(cell_type, source.strip()).to_ipynb() for cell_type, source in ipynb_util.normalized_cells(cells)]

        if 'judge_master' not in metadata:
            metadata = ipynb_metadata.master_metadata(exercise.key, True, exercise.version, exercise.title)

        if commandline_options.deadline:
            try:
                with open(os.path.join(exercise.dirpath, DEADLINE_FILE), encoding='utf-8') as f:
                    deadline = json.load(f)
            except FileNotFoundError:
                deadline = metadata['judge_master']['deadlines']
            metadata = ipynb_metadata.master_metadata(exercise.key, True, exercise.version, exercise.title, deadline)
        else:
            deadline = metadata['judge_master']['deadlines']

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
            metadata = ipynb_metadata.master_metadata(exercise.key, True, exercise.version, exercise.title, deadline)

        ipynb_util.save_as_notebook(filepath, cells_new, metadata)

def bundle_exercises(exercises: List[Exercise], is_answer: bool):
    dirpath = exercises[0].dirpath
    assert all(dirpath == e.dirpath for e in exercises)
    try:
        raw_cells, _ = ipynb_util.load_cells(os.path.join(dirpath, INTRODUCTION_FILE))
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
    is_not_decorator_line = lambda x: not x.startswith('@judge_util.')
    for _, src, _ in exercise.system_test_cases:
        contents.extend(filter(is_not_decorator_line, itertools.dropwhile(is_not_decorator_line, src.splitlines())))
        contents.append('')
    contents.pop()
    return Cell(CellType.CODE, '\n'.join(contents))

def create_autograde_source(exercise: Exercise):
    docs_dir, tests_dir = [os.path.join(CONF_DIR, exercise.key, d) for d in (CONF_SUBDIR_DOCS, CONF_SUBDIR_TESTS)]
    os.makedirs(docs_dir, exist_ok=True)
    os.makedirs(tests_dir, exist_ok=True)

    cells = [x.to_ipynb() for x in exercise.content]
    ipynb_util.save_as_notebook(os.path.join(docs_dir, 'ja.ipynb'), cells, ipynb_metadata.COMMON_METADATA)
    with open(os.path.join(tests_dir, 'setting.json'), 'w', encoding='utf-8') as f:
        json.dump(exercise.generate_setting(), f, indent=1, ensure_ascii=False)
    for name, content, _ in exercise.system_test_cases:
        with open(os.path.join(tests_dir, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)

    require_files = set()
    for x in exercise.system_test_setting['judge']['evaluation_dag']['states'].values():
        require_files.update(x['require_files'])
    for path in require_files:
        dest = os.path.join(tests_dir, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(exercise.dirpath, path), dest)

def create_configuration_zip(exercises: Iterable[Exercise]):
    shutil.rmtree(CONF_DIR, ignore_errors=True)
    for exercise in exercises:
        logging.info(f'[INFO] Creating autograde source for `{exercise.key}` ...')
        create_autograde_source(exercise)

    logging.info(f'[INFO] Creating configuration zip `{CONF_DIR}.zip` ...')
    with zipfile.ZipFile(CONF_DIR + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for exercise in exercises:
            zipf.write(os.path.join(exercise.dirpath, exercise.key + '.ipynb'), exercise.key + '.ipynb')
            for dirpath, _, files in os.walk(os.path.join(CONF_DIR, exercise.key)):
                arcdirpath = dirpath[len(os.path.join(CONF_DIR, '')):]
                for fname in files:
                    zipf.write(os.path.join(dirpath, fname), os.path.join(arcdirpath, fname))

def create_exercise_bundles(exercises: Iterable[Exercise]):
    bundle_index = collections.defaultdict(list)
    for exercise in exercises:
        bundle_index[exercise.dirpath].append(exercise)
    for dirpath, exercises in bundle_index.items():
        dirname = os.path.basename(dirpath)
        for is_answer in (False, True):
            cells = [c.to_ipynb() for c in bundle_exercises(exercises, is_answer)]
            if is_answer:
                filepath = os.path.join(dirpath, f'ans_{dirname}.ipynb')
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
            filepath = os.path.join(e.dirpath, redirect_to)
            cells, _ = ipynb_util.load_cells(filepath, True)
            assert any(re.search(rf'<\[ {e.key} \]>', line)
                       for c in cells if c['cell_type'] == CellType.CODE.value for line in c['source']), \
                f'{redirect_to} has no answer cell for {e.key}.'
            ipynb_util.save_as_notebook(filepath, cells, metadata)

def create_single_forms(exercises: Iterable[Exercise]):
    for ex in exercises:
        # Create answer
        cells = itertools.chain(ex.content, ex.answer_examples, [summarize_testcases(ex)], ex.explanation)
        filepath = os.path.join(ex.dirpath, f'ans_{ex.key}.ipynb')
        metadata = ipynb_metadata.COMMON_METADATA
        ipynb_util.save_as_notebook(filepath, [c.to_ipynb() for c in cells], metadata)

        # Create form
        cells = itertools.chain(ex.content, [ex.submission_cell()], ex.student_tests)
        redirect_to = ex.submission_redirection()
        if redirect_to is None:
            filepath = os.path.join(ex.dirpath, f'form_{ex.key}.ipynb')
            metadata =  ipynb_metadata.submission_metadata({ex.key: ex.version}, True)
        else:
            filepath = os.path.join(ex.dirpath, f'pseudo-form_{ex.key}.ipynb')
            metadata = ipynb_metadata.COMMON_METADATA
        ipynb_util.save_as_notebook(filepath, [c.to_ipynb() for c in cells], metadata)

        if redirect_to is not None:
            # Create redirected form
            filepath = os.path.join(ex.dirpath, redirect_to)
            cells, _ = ipynb_util.load_cells(filepath, True)
            assert any(re.search(rf'<\[ {ex.key} \]>', line)
                       for c in cells if c['cell_type'] == CellType.CODE.value for line in c['source']), \
                f'{redirect_to} has no answer cell for {ex.key}.'
            metadata = ipynb_metadata.submission_metadata({ex.key: ex.version}, True)
            ipynb_util.save_as_notebook(filepath, cells, metadata)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose option')
    parser.add_argument('-b', '--bundle', action='store_true', help='Bundle mode option')
    parser.add_argument('-d', '--deadline', action='store_true', help='Set deadlines to exercises')
    parser.add_argument('-c', '--configuration', action='store_true', help='Dump configuration zip')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, metavar='VERSION', help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-t', '--targets', nargs='*', required=True, metavar='TARGET', help=f'Specify targets (ipynb files in separate mode and directories in bundle mode)')
    commandline_options = parser.parse_args()
    if commandline_options.verbose:
        logging.getLogger().setLevel('DEBUG')
    else:
        logging.getLogger().setLevel('INFO')

    exercises = []
    existing_keys = {}
    if commandline_options.bundle:
        for dirpath in sorted(commandline_options.targets):
            if not os.path.isdir(dirpath):
                logging.info(f'[INFO] Skip {dirpath}')
                continue
            dirname = os.path.basename(dirpath)
            for nb in sorted(os.listdir(dirpath)):
                match = re.fullmatch(fr'({dirname}[-_].*)\.ipynb', nb)
                if match is None:
                    continue
                exercise_key = match.groups()[0]
                assert exercise_key not in existing_keys, \
                    f'[ERROR] Exercise key conflicts between `{dirpath}/{nb}` and `{existing_keys[exercise_key]}`.'
                existing_keys[exercise_key] = os.path.join(dirpath, nb)
                exercises.append(load_exercise(dirpath, exercise_key))
                logging.info(f'[INFO] Loaded `{dirpath}/{nb}`')
    else:
        for filepath in sorted(commandline_options.targets):
            if not filepath.endswith('.ipynb'):
                logging.info(f'[INFO] Skip {filepath}')
                continue
            dirpath, filename = os.path.split(filepath)
            exercise_key, _ = os.path.splitext(filename)
            assert exercise_key not in existing_keys, \
                f'[ERROR] Exercise key conflicts between `{filepath}` and `{existing_keys[exercise_key]}`.'
            existing_keys[exercise_key] = filepath
            exercises.append(load_exercise(dirpath, exercise_key))
            logging.info(f'[INFO] Loaded `{filepath}`')

    logging.info('[INFO] Cleaning up exercise masters...')
    cleanup_exercise_masters(exercises, commandline_options)

    if commandline_options.bundle:
        logging.info('[INFO] Creating bundled forms...')
        create_exercise_bundles(exercises)
    else:
        logging.info('[INFO] Creating separate forms...')
        create_single_forms(exercises)

    if commandline_options.configuration:
        logging.info('[INFO] Creating configuration zip...')
        create_configuration_zip(exercises)

if __name__ == '__main__':
    main()
