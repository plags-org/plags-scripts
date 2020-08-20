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

import yaml

import ipynb_metadata
import ipynb_util


if (sys.version_info.major, sys.version_info.minor) < (3, 7):
    print('[ERROR] This script requires Python >= 3.7.')
    sys.exit(1)

HOMEDIR = 'exercises'

ALL_TARGET_DIRS = frozenset(('ex1',))

SUBMISSION_CELL_FORMAT = """
##########################################################
##  <[ {exercise_id_str} ]> 解答セル (Answer cell)
##  このコメントの書き変えを禁ず (Never edit this comment)
##########################################################

{content}""".strip()

REDIRECTION_CELL_FORMAT = """
# このセルではなく {redirect_to} を使ってください
# Use {redirect_to} instead of this cell
""".strip()

class Language(enum.Enum):
    JA = enum.auto()
    EN = enum.auto()

COURSE_LANGUAGES = tuple(Language)

MARKDOWN_CELL_CONTENT_ABOVE_STUDENT_TEST_I18N = {
    Language.JA: '提出前に以下のテストセルを実行し、 `True` のみが出力されることを確認してください。',
    Language.EN: 'Before submission, execute the following test cell and check if only `True` is printed.',
}

NOTEBOOK_TITLE_FUNCTION_TYPE_I18N = {
    Language.JA: {
        **{d: f'第{d[3:]}回予習課題' for d in ALL_TARGET_DIRS if d.startswith('pre')},
        **{d: f'第{d[2:]}回本課題'   for d in ALL_TARGET_DIRS if d.startswith('ex')},
        **{'project1': 'ミニプロジェクト（基礎課題）'},
    },
    Language.EN: {
        **{d: f'Preparations {d[3:]}' for d in ALL_TARGET_DIRS if d.startswith('pre')},
        **{d: f'Exercises {d[2:]}'    for d in ALL_TARGET_DIRS if d.startswith('ex')},
        **{'project1': 'Miniproject (Basic exercises)'},
    },
}

COURSE_EXERCISE_INFO = 'course_exercise_info'
COURSE_CONCRETES_DIR = os.path.join(COURSE_EXERCISE_INFO, 'course_concretes')
SETTINGS_DIR = os.path.join(COURSE_EXERCISE_INFO, 'settings')
EXERCISE_CONCRETES_DIR = os.path.join(COURSE_EXERCISE_INFO, 'exercise_concretes')
DOCS_SUBDIR = 'docs'
EXAMPLES_SUBDIR = 'examples'
TESTS_SUBDIR = 'tests'

KEY_WARNING = 'WARNING: NEVER EDIT THE SYSTEM CELLS !!!'
KEY_CONTENT = 'CONTENT'
KEY_STUDENT_CODE_CELL = 'STUDENT_CODE_CELL'
KEY_EXPLANATION = 'EXPLANATION'
KEY_ANSWER_EXAMPLES = 'ANSWER_EXAMPLES'
KEY_STUDENT_TEST_CELL = 'STUDENT_TEST_CELL'
KEY_SYSTEM_TEST_CASES_EXECUTE_CELL = 'SYSTEM_TEST_CASES_EXECUTE_CELL'
KEY_SYSTEM_TEST_CASES = 'SYSTEM_TEST_CASES'
KEY_SYSTEM_TEST_REQUIRE_FILES = 'SYSTEM_TEST_REQUIRE_FILES'
KEY_SYSTEM_TEST_SETTING = 'SYSTEM_TEST_SETTING'

CellType = ipynb_util.NotebookCellType

class PropertyFlag(enum.Flag):
    WARNING = enum.auto()
    LIST = enum.auto()
    OPTIONAL = enum.auto()
    MARKDOWN_HEADED = enum.auto()
    YAML = enum.auto()
    FILE = enum.auto()
    CONTENT = enum.auto()
    SETTING = enum.auto()
    REQUIRE_FILES = enum.auto()

SplitKey = collections.namedtuple('SplitKey', ('name', 'cell_type', 'lang', 'flags'))

SPLIT_KEYS = (
    SplitKey(KEY_WARNING, CellType.CODE, None, PropertyFlag.WARNING),
    *(SplitKey(f'{KEY_CONTENT}_{lang.name}', None, lang, PropertyFlag.LIST | PropertyFlag.MARKDOWN_HEADED) for lang in COURSE_LANGUAGES),
    SplitKey(KEY_STUDENT_CODE_CELL, CellType.CODE, None, PropertyFlag(0)),
    *(SplitKey(f'{KEY_EXPLANATION}_{lang.name}', None, lang, PropertyFlag.LIST | PropertyFlag.MARKDOWN_HEADED | PropertyFlag.OPTIONAL) for lang in [Language.JA]),
    SplitKey(KEY_ANSWER_EXAMPLES, CellType.CODE, None, PropertyFlag.LIST | PropertyFlag.FILE),
    SplitKey(KEY_STUDENT_TEST_CELL, CellType.CODE, None, PropertyFlag(0)),
    SplitKey(KEY_SYSTEM_TEST_CASES_EXECUTE_CELL, CellType.CODE, None, PropertyFlag(0)),
    SplitKey(KEY_SYSTEM_TEST_CASES, CellType.CODE, None, PropertyFlag.LIST | PropertyFlag.FILE),
    SplitKey(KEY_SYSTEM_TEST_REQUIRE_FILES, CellType.RAW, None, PropertyFlag.YAML | PropertyFlag.REQUIRE_FILES | PropertyFlag.OPTIONAL),
    SplitKey(KEY_SYSTEM_TEST_SETTING, CellType.RAW, None, PropertyFlag.YAML | PropertyFlag.SETTING),
)
assert len(SPLIT_KEYS) == len({x.name for x in SPLIT_KEYS}), 'The elements of `SPLIT_KEYS` must be distinct by the `name` attribute.'

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
    id_str: str     # id string
    dirname: str    # directory name
    pseudo: bool    # if a pseudo exercise only of which the content is used
    version: str    # version str
    content: Dict[Language, List[Cell]]     # The description of exercise, starts with multiple '#'s and exercise title in lang
    student_code_cell: Cell                 # Code cell
    explanation: Dict[Language, List[Cell]] # The explanation of exercise, starts with multiple '#'s and exercise title in lang
    answer_examples: List[Tuple[Tuple[str,str],Cell]] # list of (filename, content, original code cell)
    student_test_cell: Cell                 # Code cell
    system_test_cases_execute_cell: Cell    # Code cell
    system_test_cases: List[Tuple[str,str,Cell]] # list of (filename, content, original code cell)
    system_test_require_files: List[List[str]] # List of paths, each of which is of List[str]; from yaml in raw cell (optional)
    system_test_setting: object             # From yaml in raw cell

    def submission_redirection(self):
        m = re.match(r'#[ \t]*redirect-to[ \t]*:[ \t]*(\S+?\.ipynb)', self.student_code_cell.source)
        return m[1] if m else None

    def submission_cell(self):
        redirect_to = self.submission_redirection()
        if redirect_to:
            s = REDIRECTION_CELL_FORMAT.format(redirect_to=redirect_to)
        else:
            s = SUBMISSION_CELL_FORMAT.format(exercise_id_str=self.id_str, content=self.student_code_cell.source)
        return Cell(CellType.CODE, s)


def validate_header_markdown_cell(cell: Cell):
    assert cell.cell_type == CellType.MARKDOWN
    first_line_regex = r'#+\s+(.*)'
    first_line = cell.source.strip().splitlines()[0]
    assert re.fullmatch(first_line_regex, first_line) is not None, \
        f'The first content cell does not start with a heading in Markdown: `{first_line}`.'

def split_file_code_cell(cell: Cell):
    assert cell.cell_type == CellType.CODE
    lines = cell.source.strip().splitlines(keepends=True)
    first_line_regex = r'#+\s+([^/]{1,255})'
    match = re.fullmatch(first_line_regex, lines[0].strip())
    assert match is not None, f'RegExp pattern `{first_line_regex}` does not match the first line of a file code cell: {lines[0]}'
    return (match[1], ''.join(lines[1:]).strip() + '\n', cell)

def load_system_test_require_files(cells: List[Cell]):
    """
    `require_files` must match the following structure:
    `{'require_files': List[Union[str, List[str]]]}`
    """
    if not cells:
        return []
    assert cells[0].cell_type == CellType.RAW
    yaml_data = yaml.safe_load(cells[0].source)
    assert len(yaml_data) == 1 and 'require_files' in yaml_data and isinstance(yaml_data['require_files'], list)
    require_files = [x if isinstance(x, list) else [x] for x in yaml_data['require_files']]
    assert all(map(bool, require_files)) and all(isinstance(s, str) for path in require_files for s in path)
    return require_files

def split_cells(raw_cells: Iterable[dict]):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'
    results = {}
    current_split_key_idx = -1
    cells = []
    for cell_type, source in ipynb_util.normalized_cells(raw_cells):
        if commandline_options.verbose:
            print('[TRACE]', SPLIT_KEYS[current_split_key_idx].name if current_split_key_idx > 0 else None,
                  repr(source if len(source) <= 64 else source[:64] + ' ...'))
        if source.strip() == '':
            continue

        if cell_type in (CellType.CODE, CellType.RAW):
            cells.append(Cell(cell_type, source))
            continue
        assert cell_type == CellType.MARKDOWN

        matches = list(re.finditer(CONTENT_TYPE_REGEX, source))
        if len(matches) == 0:
            cells.append(Cell(cell_type, source))
            continue
        assert len(matches) == 1, f'Multiple split keys found in cell `{source}`.'

        if current_split_key_idx >= 0:
            results[SPLIT_KEYS[current_split_key_idx]] = cells
            cells = []

        current_split_key_idx += 1
        assert matches[0][1] == SPLIT_KEYS[current_split_key_idx].name, \
            f'Split key `{SPLIT_KEYS[current_split_key_idx].name}` expected but {matches[0][1]} found.'
        assert SPLIT_KEYS[current_split_key_idx] not in results, \
            f'Duplicated split key `{matches[0][1]}`.'

    if current_split_key_idx < len(SPLIT_KEYS):
        results[SPLIT_KEYS[current_split_key_idx]] = cells

    return results

def load_exercise(dirname, exercise_id_str):
    raw_cells, metadata = ipynb_util.load_cells(os.path.join(HOMEDIR, dirname, exercise_id_str + '.ipynb'))
    pseudo = re.fullmatch(rf'{dirname}-(\d+)-.+?', exercise_id_str)[1] == '0'
    version = metadata['exercise_version']
    exercise_kwargs = {'id_str': exercise_id_str, 'dirname': dirname, 'pseudo': pseudo, 'version': version}
    for split_key, cells in split_cells(raw_cells).items():
        if PropertyFlag.WARNING in split_key.flags:
            continue
        if commandline_options.verbose:
            print('[TRACE]', f'Validate split key `{split_key.name}`')

        mask = (PropertyFlag.LIST | PropertyFlag.OPTIONAL) & split_key.flags
        if mask == PropertyFlag.LIST:
            assert len(cells) != 0, f'Split key `{split_key.name}` must not be empty.'
        elif mask == PropertyFlag.OPTIONAL:
            assert len(cells) <= 1, f'Split key `{split_key.name}` must have at most 1 cell but has {len(cells)}.'
        elif mask == PropertyFlag(0):
            assert len(cells) == 1, f'Split key `{split_key.name}` must have exactly 1 cell but has {len(cells)}.'

        if len(cells) > 0 and PropertyFlag.MARKDOWN_HEADED in split_key.flags:
            validate_header_markdown_cell(cells[0])

        if PropertyFlag.SETTING in split_key.flags:
            assert cells[0].cell_type == CellType.RAW
            value = yaml.safe_load(cells[0].source) #TODO: more precise validation
        elif PropertyFlag.REQUIRE_FILES in split_key.flags:
            value = load_system_test_require_files(cells)
        elif PropertyFlag.FILE in split_key.flags:
            value = [split_file_code_cell(x) for x in cells]
        else:
            assert split_key.cell_type == None or all(x.cell_type == split_key.cell_type for x in cells), \
                'Cell of type {cell.cell_type} does not match split key `{split_key.name}`.'
            value = cells[0] if mask == PropertyFlag(0) else cells

        if split_key.lang:
            key = split_key.name.rsplit('_', maxsplit=1)[0].lower()
            value_i18n = exercise_kwargs.setdefault(key, {})
            value_i18n[split_key.lang] = value
            assert all(len(value) == len(x) for x in value_i18n.values()), \
                'The number of content cells in `{split_key.lang}` does not match with that in other languages.'
        else:
            exercise_kwargs[split_key.name.lower()] = value

    return Exercise(**exercise_kwargs)

def cleanup_exercise(exercises: Iterable[Exercise]):
    for exercise in exercises:
        filename = os.path.join(HOMEDIR, exercise.dirname, f'{exercise.id_str}.ipynb')
        cells, metadata = ipynb_util.load_cells(filename, True)
        cells_new = [Cell(cell_type, source.strip()).to_ipynb() for cell_type, source in ipynb_util.normalized_cells(cells)]
        if commandline_options.renew_version:
            print(f'[INFO] Renew version of {exercise.id_str}')
            metadata = ipynb_metadata.EXERCISE_METADATA
            exercise.version = ipynb_metadata.EXERCISE_METADATA['exercise_version']
        ipynb_util.save_as_notebook(filename, cells, metadata)

def create_notebook_cells(dirname: str, lang: Language, is_answer: bool, exercises: Iterable[Exercise]):
    cells = [Cell(CellType.MARKDOWN, '# ' + NOTEBOOK_TITLE_FUNCTION_TYPE_I18N[lang][dirname])]
    for exercise in exercises:
        cells.extend(exercise.content[lang])
        if exercise.pseudo:
            continue
        if is_answer:
            cells.extend(c for _, _, c in exercise.answer_examples)
            cells.append(summarize_testcases(exercise))
            cells.extend(exercise.explanation.get(lang, []))
        else:
            cells.append(exercise.submission_cell())
            cells.append(Cell(CellType.MARKDOWN, MARKDOWN_CELL_CONTENT_ABOVE_STUDENT_TEST_I18N[lang]))
            cells.append(exercise.student_test_cell)
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
    basedir = os.path.join(EXERCISE_CONCRETES_DIR, exercise.id_str)
    docs_dir, examples_dir, tests_dir = [os.path.join(basedir, d) for d in (DOCS_SUBDIR, EXAMPLES_SUBDIR, TESTS_SUBDIR)]
    for path in (docs_dir, examples_dir, tests_dir):
        os.makedirs(path, exist_ok=True)

    for lang, content_cells in exercise.content.items():
        content_md = ({CellType.MARKDOWN: lambda x: x,
                       CellType.CODE: lambda x: f'---\n\n```python\n{x.strip()}\n```\n\n---'}[c.cell_type](c.source)
                      for c in content_cells if c.cell_type != CellType.RAW)
        with open(os.path.join(docs_dir, f'{lang.name.lower()}.md'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n\n'.join(content_md))

    for name, content, _ in exercise.answer_examples:
        with open(os.path.join(examples_dir, name), 'w', encoding='utf_8', newline='\n') as f:
            f.write(content)

    system_test_setting = copy.deepcopy(exercise.system_test_setting)
    system_test_setting['editor']['initial_source'] = exercise.student_code_cell.source
    system_test_setting['editor']['exercise_version'] = exercise.version
    with open(os.path.join(tests_dir, 'setting.yml'), 'w', encoding='utf_8') as f:
        yaml.dump(system_test_setting, stream=f, sort_keys=False)
    for name, content, _ in exercise.system_test_cases:
        with open(os.path.join(tests_dir, name), 'w', encoding='utf_8', newline='\n') as f:
            f.write(content)

    for path in exercise.system_test_require_files:
        dstdir = os.path.join(tests_dir, *path[:-1])
        if len(path) > 1:
            os.makedirs(dstdir, exist_ok=True)
        shutil.copyfile(os.path.join(HOMEDIR, exercise.dirname, *path), os.path.join(dstdir, path[-1]))

def create_system_settings(exercises: Iterable[Exercise]):
    # Prepare directories
    for path in (COURSE_CONCRETES_DIR, SETTINGS_DIR):
        if os.path.exists(path):
            assert os.path.isdir(path)
        else:
            os.makedirs(path)

    # Clean up directory
    shutil.rmtree(EXERCISE_CONCRETES_DIR, ignore_errors=True)
    for exercise in exercises:
        print(f'[INFO] creating system settings for `{exercise.id_str}` ...')
        create_exercise_concrete(exercise)
        #TODO: validation as an exercise_concrete

    print(f'[INFO] creating system settings zip file `{COURSE_EXERCISE_INFO}.zip` ...')
    with zipfile.ZipFile(COURSE_EXERCISE_INFO + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(COURSE_EXERCISE_INFO):
            for file in files:
                zipf.write(os.path.join(root, file))

def generate_artifacts(exercises: Iterable[Exercise]):
    artifact_index = collections.defaultdict(list)
    for exercise in exercises:
        artifact_index[exercise.dirname].append(exercise)
    for dirname, exercises in artifact_index.items():
        for lang in COURSE_LANGUAGES:
            for is_answer in (False, True):
                cells = [c.to_ipynb() for c in create_notebook_cells(dirname, lang, is_answer, exercises)]
                suffix = '-ans' if is_answer else ''
                filepath = os.path.join(HOMEDIR, dirname, f'{dirname}{lang.name.lower()}{suffix}.ipynb')
                if is_answer:
                    metadata = ipynb_metadata.MATERIALS_METADATA
                else:
                    id_to_ver = {e.id_str: e.version for e in exercises if not e.pseudo and e.submission_redirection() is None}
                    metadata = ipynb_metadata.submission_metadata(id_to_ver, True)
                ipynb_util.save_as_notebook(filepath, cells, metadata)
        for e in exercises:
            redirect_to = e.submission_redirection()
            if redirect_to is None:
                continue
            metadata = ipynb_metadata.submission_metadata({e.id_str: e.version}, True)
            filepath = os.path.join(HOMEDIR, dirname, redirect_to)
            cells, _ = ipynb_util.load_cells(filepath, True)
            assert any(re.search(rf'<\[ {e.id_str} \]>', line)
                       for c in cells if c['cell_type'] == CellType.CODE.value for line in c['source']), \
                f'{redirect_to} has no answer cell for {e.id_str}.'
            ipynb_util.save_as_notebook(filepath, cells, metadata)

def main():
    exercises = []
    for dirname in sorted(x for x in os.listdir(HOMEDIR) if x in set(commandline_options.targets)):
        exercise_name_index = {}
        for nb in sorted(os.listdir(os.path.join(HOMEDIR, dirname))):
            match = re.fullmatch(r'((pre\d|ex\d|project\d)-(\d+)-.+?)\.ipynb', nb)
            if match is None:
                continue
            exercise_id_str, exercise_prefix, exercise_sub_id = match.groups()
            assert dirname == exercise_prefix, \
                f'[ERROR] Exercise master `{exercise_id_str}` exists in an unexpected directory `{dirname}`.'
            assert (dirname, exercise_sub_id) not in exercise_name_index, \
                f'[ERROR] Exercise master `{exercise_id_str}` conflicts with exercise `{exercise_name_index[(dirname, exercise_sub_id)]}`.'
            exercise_name_index[exercise_sub_id] = exercise_id_str
            print('[INFO] Load', f'{dirname}/{nb}')
            exercises.append(load_exercise(dirname, exercise_id_str))

    if commandline_options.dry_run:
        print('[INFO] Dry run')
        for exercise in exercises:
            print(f'[INFO]     - {exercise.id_str}.ipynb')
        return

    print('[INFO] Start to clean up master notebooks')
    cleanup_exercise(exercises)

    print('[INFO] Start to generate notebooks')
    generate_artifacts(exercises)

    if commandline_options.dump_setting_zip:
        print('[INFO] Start to generate judge system settings')
        create_system_settings(exercises)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose option')
    parser.add_argument('-d', '--dry_run', action='store_true', help='dry-run option')
    parser.add_argument('-s', '--dump_setting_zip', action='store_true', help='dump setting zip')
    parser.add_argument('-n', '--renew_version', action='store_true', help='renew the version of exercises')
    parser.add_argument('-t', '--targets', nargs='*', default=ALL_TARGET_DIRS, help='specify target assignments')
    commandline_options = parser.parse_args()
    main()
