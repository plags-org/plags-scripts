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
from typing import List, Iterable, Tuple, Callable

import json
import hashlib
import logging
import itertools

import ipynb_metadata
import ipynb_util
import judge_setting

if (sys.version_info.major, sys.version_info.minor) < (3, 8):
    print('[ERROR] This script requires Python >= 3.8.')
    sys.exit(1)

INTRODUCTION_FILE = 'intro.ipynb'

CONF_DIR = 'autograde'

ANSWER_CELL_FORMAT = """
##########################################################
##  <[ {exercise_key} ]> 解答セル (Answer cell)
##  このコメントの書き変えを禁ず (Never edit this comment)
##########################################################

{content}""".strip()

class FieldKey(enum.Enum):
    WARNING = enum.auto()
    DESCRIPTION = enum.auto()
    ANSWER_CELL_CONTENT = enum.auto()
    COMMENTARY = enum.auto()
    EXAMPLE_ANSWERS = enum.auto()
    INSTRUCTIVE_TEST = enum.auto()
    SYSTEM_TESTCODE = enum.auto()
    PLAYGROUND = enum.auto()

class FieldProperty(enum.Flag):
    SINGLE = enum.auto()
    LIST = enum.auto()
    OPTIONAL = enum.auto()
    MARKDOWN_HEADED = enum.auto()
    CODE = enum.auto()

FieldKey.WARNING.properties = FieldProperty(0)
FieldKey.DESCRIPTION.properties = FieldProperty.LIST | FieldProperty.MARKDOWN_HEADED
FieldKey.ANSWER_CELL_CONTENT.properties = FieldProperty.SINGLE | FieldProperty.CODE
FieldKey.COMMENTARY.properties = FieldProperty.LIST | FieldProperty.MARKDOWN_HEADED | FieldProperty.OPTIONAL
FieldKey.EXAMPLE_ANSWERS.properties = FieldProperty.LIST | FieldProperty.OPTIONAL
FieldKey.INSTRUCTIVE_TEST.properties = FieldProperty.LIST | FieldProperty.OPTIONAL
FieldKey.SYSTEM_TESTCODE.properties = FieldProperty.LIST | FieldProperty.CODE | FieldProperty.OPTIONAL
FieldKey.PLAYGROUND.properties = FieldProperty.SINGLE | FieldProperty.CODE

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
    description: List[Cell]                      # DESCRIPTION field
    answer_cell_content: Cell                    # ANSWER_CELL_CONTENT field
    commentary: List[Cell]                       # COMMENTARY field
    example_answers: List[Cell]                  # EXAMPLE_ANSWERS field
    instructive_test: List[Cell]                 # INSTRUCTIVE_TEST field
    test_modules: List[Tuple[str,List[str],str]] # List of (name, required file paths, content)

    def answer_cell(self):
        s = ANSWER_CELL_FORMAT.format(exercise_key=self.key, content=self.answer_cell_content.source)
        return Cell(CellType.CODE, s)

    def answer_cell_filled(self):
        s = ANSWER_CELL_FORMAT.format(exercise_key=self.key, content=self.example_answers[0].source if self.example_answers else self.answer_cell_content.source)
        return Cell(CellType.CODE, s)

    def generate_setting(self):
        test_stages  = [(name, paths) for name, paths, _ in self.test_modules]
        return judge_setting.generate_judge_setting(self.key, self.version, self.answer_cell_content.source, test_stages)


def split_testcode_cells(cells):
    dummy_source = """
## _dummy
# .judge/judge_util.py

import sys
sys.path.append('.judge')
import judge_util # モジュール全体をそのままの名前でimport
""".lstrip()
    if cells:
        return [split_testcode_cell(x) for x in cells]
    else:
        return [split_testcode_cell(Cell(CellType.CODE, dummy_source))]


def split_testcode_cell(cell: Cell):
    assert cell.cell_type == CellType.CODE
    lines = cell.source.strip().splitlines(keepends=True)
    first_line_regex = r'#+\s+([^/]{1,255})'
    match = re.fullmatch(first_line_regex, lines[0].strip())
    assert match is not None, f'The first line of a test-code cell does not specify a module name of RegExp `{first_line_regex}`: {lines[0]}'
    module_file = match[1]
    file_paths = []
    i = 1
    while (match := re.fullmatch(r'#+\s+(.*)', lines[i].strip())) is not None:
        file_paths.append(match[1])
        i += 1
    return (module_file, file_paths, ''.join(lines[i:]).strip() + '\n')


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
        assert len(matches) == 1, f'Multiple field keys found in cell `{source}`.'

        if current_key is not None:
            results[current_key] = cells
            cells = []
        current_key = matches[0][1]

    results[current_key] = cells
    return results

def load_exercise(dirpath, exercise_key):
    raw_cells, metadata = ipynb_util.load_cells(os.path.join(dirpath, exercise_key + '.ipynb'))
    version = ipynb_metadata.master_metadata_version(metadata)
    exercise_kwargs = {'key': exercise_key, 'dirpath': dirpath, 'version': version}
    for field_key, cells in split_cells(raw_cells).items():
        field_enum = getattr(FieldKey, field_key)
        if field_enum in (FieldKey.WARNING, FieldKey.PLAYGROUND):
            continue
        logging.debug(f'[TRACE] Validate field `{field_key}`')

        if (FieldProperty.OPTIONAL | FieldProperty.OPTIONAL) in field_enum.properties:
            pass
        elif (FieldProperty.OPTIONAL) in field_enum.properties:
            assert len(cells) <= 1, f'Field of `{field_key}` must have at most 1 cell but has {len(cells)}.'
        elif FieldProperty.LIST in field_enum.properties:
            assert len(cells) > 0, f'Field of `{field_key}` must not be empty.'
        elif FieldProperty.SINGLE in field_enum.properties:
            assert len(cells) == 1, f'Field of `{field_key}` must have 1 cell.'

        if FieldProperty.CODE in field_enum.properties:
            assert all(x.cell_type == CellType.CODE for x in cells), f'Field of `{field_key}` must have only code cell(s).'

        if len(cells) > 0 and FieldProperty.MARKDOWN_HEADED in field_enum.properties:
            assert cells[0].cell_type == CellType.MARKDOWN
            first_line_regex = r'#+\s+(.*)'
            first_line = cells[0].source.strip().splitlines()[0]
            m = re.fullmatch(first_line_regex, first_line)
            assert m is not None, f'The first content cell does not start with a heading in Markdown: `{first_line}`.'
            if field_enum == FieldKey.DESCRIPTION:
                exercise_kwargs['title'] = m.groups()[0]

        if field_enum == FieldKey.SYSTEM_TESTCODE:
            exercise_kwargs['test_modules'] = split_testcode_cells(cells)
        elif field_enum == FieldKey.ANSWER_CELL_CONTENT:
            exercise_kwargs[field_key.lower()] = cells[0]
        else:
            exercise_kwargs[field_key.lower()] = cells

    return Exercise(**exercise_kwargs)

def summarize_testcases(exercise: Exercise):
    contents = []
    is_not_decorator_line = lambda x: not x.startswith('@judge_util.')
    for _, _, src in exercise.test_modules:
        contents.extend(filter(is_not_decorator_line, itertools.dropwhile(is_not_decorator_line, src.splitlines())))
        contents.append('')
    return Cell(CellType.CODE, '\n'.join(contents).rstrip())

def create_exercise_configuration(exercise: Exercise):
    tests_dir = os.path.join(CONF_DIR, exercise.key)
    os.makedirs(tests_dir, exist_ok=True)

    cells = [x.to_ipynb() for x in itertools.chain(exercise.description, [exercise.answer_cell_content])]
    _, metadata = ipynb_util.load_cells(os.path.join(exercise.dirpath, exercise.key + '.ipynb'), True)
    ipynb_util.save_as_notebook(os.path.join(CONF_DIR, exercise.key + '.ipynb'), cells, metadata)
    setting = exercise.generate_setting()
    with open(os.path.join(tests_dir, 'setting.json'), 'w', encoding='utf-8') as f:
        json.dump(setting, f, indent=1, ensure_ascii=False)

    for name, _, content in exercise.test_modules:
        with open(os.path.join(tests_dir, f'{name}.py'), 'w', encoding='utf-8', newline='\n') as f:
            print(content, 'judge_util.unittest_main()', sep='\n', file=f)

    for path in itertools.chain(*(paths for _, paths, _ in exercise.test_modules)):
        dest = os.path.join(tests_dir, path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(os.path.join(exercise.dirpath, path), dest)

def create_configuration(exercises: Iterable[Exercise]):
    shutil.rmtree(CONF_DIR, ignore_errors=True)
    for exercise in exercises:
        logging.info(f'[INFO] Creating configuration for `{exercise.key}` ...')
        create_exercise_configuration(exercise)

    logging.info(f'[INFO] Creating configuration zip `{CONF_DIR}.zip` ...')
    with zipfile.ZipFile(CONF_DIR + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
        for dirpath, _, files in os.walk(CONF_DIR):
            arcdirpath = dirpath[len(os.path.join(CONF_DIR, '')):]
            for fname in files:
                zipf.write(os.path.join(dirpath, fname), os.path.join(arcdirpath, fname))

def create_bundled_forms(exercise_bundles):
    for dirpath, exercises in exercise_bundles.items():
        dirname = os.path.basename(dirpath)
        try:
            raw_cells, _ = ipynb_util.load_cells(os.path.join(dirpath, INTRODUCTION_FILE))
            intro = [Cell(t, s) for t, s in ipynb_util.normalized_cells(raw_cells)]
        except FileNotFoundError:
            intro = [Cell(CellType.MARKDOWN, f'# {os.path.basename(dirpath)}')]

        # Create answer
        body = []
        for exercise in exercises:
            body.extend(exercise.description)
            body.extend(exercise.example_answers)
            body.append(summarize_testcases(exercise))
            body.extend(exercise.commentary)
        filepath = os.path.join(dirpath, f'ans_{dirname}.ipynb')
        metadata = ipynb_metadata.COMMON_METADATA
        ipynb_util.save_as_notebook(filepath, [c.to_ipynb() for c in itertools.chain(intro, body)], metadata)

        # Create form
        body = []
        for exercise in exercises:
            body.extend(exercise.description)
            body.append(exercise.answer_cell())
            body.extend(exercise.instructive_test)
        filepath = os.path.join(dirpath, f'form_{dirname}.ipynb')
        key_to_ver = {ex.key: ex.version for ex in exercises}
        metadata = ipynb_metadata.submission_metadata(key_to_ver, True)
        ipynb_util.save_as_notebook(filepath, [c.to_ipynb() for c in itertools.chain(intro, body)], metadata)

def create_single_forms(exercises: Iterable[Exercise]):
    for ex in exercises:
        # Create answer
        cells = itertools.chain(ex.description, ex.example_answers, [summarize_testcases(ex)], ex.commentary)
        filepath = os.path.join(ex.dirpath, f'ans_{ex.key}.ipynb')
        metadata = ipynb_metadata.COMMON_METADATA
        ipynb_util.save_as_notebook(filepath, [c.to_ipynb() for c in cells], metadata)

        # Create form
        cells = itertools.chain(ex.description, [ex.answer_cell()], ex.instructive_test)
        filepath = os.path.join(ex.dirpath, f'form_{ex.key}.ipynb')
        metadata =  ipynb_metadata.submission_metadata({ex.key: ex.version}, True)
        ipynb_util.save_as_notebook(filepath, [c.to_ipynb() for c in cells], metadata)

def create_filled_form(exercises: Iterable[Exercise], filepath):
    metadata =  ipynb_metadata.submission_metadata({ex.key: ex.version for ex in exercises}, True)
    ipynb_util.save_as_notebook(filepath, [ex.answer_cell_filled().to_ipynb() for ex in exercises], metadata)

def load_sources(source_paths: Iterable[str], *, master_loader=load_exercise):
    exercises = []
    bundles = collections.defaultdict(list)
    existing_keys = {}
    for path in sorted(source_paths):
        if os.path.isdir(path):
            dirpath = path
            dirname = os.path.basename(dirpath)
            logging.info(f'[INFO] Loading `{dirpath}`...')
            for nb in sorted(os.listdir(dirpath)):
                match = re.fullmatch(fr'({dirname}[-_].*)\.ipynb', nb)
                if match is None:
                    continue
                exercise_key = match.groups()[0]
                assert exercise_key not in existing_keys, \
                    f'[ERROR] Exercise key conflicts between `{dirpath}/{nb}` and `{existing_keys[exercise_key]}`.'
                existing_keys[exercise_key] = os.path.join(dirpath, nb)
                bundles[dirpath].append(master_loader(dirpath, exercise_key))
                logging.info(f'[INFO] Loaded `{dirpath}/{nb}`')
        else:
            filepath = path
            if not filepath.endswith('.ipynb'):
                logging.info(f'[INFO] Skip {filepath}')
                continue
            dirpath, filename = os.path.split(filepath)
            exercise_key, _ = os.path.splitext(filename)
            assert exercise_key not in existing_keys, \
                f'[ERROR] Exercise key conflicts between `{filepath}` and `{existing_keys[exercise_key]}`.'
            existing_keys[exercise_key] = filepath
            exercises.append(master_loader(dirpath, exercise_key))
            logging.info(f'[INFO] Loaded `{filepath}`')
    return exercises, bundles


def cleanup_exercise_master(exercise, new_version=None):
    filepath = os.path.join(exercise.dirpath, f'{exercise.key}.ipynb')
    cells, metadata = ipynb_util.load_cells(filepath, True)
    cells_new = [Cell(cell_type, source.strip()).to_ipynb() for cell_type, source in ipynb_util.normalized_cells(cells)]

    if new_version is None:
        new_version = exercise.version
    elif new_version == hashlib.sha1:
        exercise_definition = {
            'description': [x.to_ipynb() for x in exercise.description],
            'answer_cell': exercise.answer_cell().to_ipynb(),
            'instructive_test': [x.to_ipynb() for x in exercise.instructive_test],
        }
        m = hashlib.sha1()
        m.update(json.dumps(exercise_definition).encode())
        new_version = m.hexdigest()
    else:
        assert isinstance(new_version, str)

    if new_version != exercise.version:
        logging.info(f'[INFO] Renew version of {exercise.key}')
        exercise.version = new_version

    deadlines = ipynb_metadata.master_metadata_deadlines(metadata)
    drive = ipynb_metadata.master_metadata_drive(metadata)
    metadata_new = ipynb_metadata.master_metadata(exercise.key, True, exercise.version, exercise.title, deadlines, drive)
    ipynb_util.save_as_notebook(filepath, cells_new, metadata_new)


def update_exercise_master_metadata_formwise(separates, bundles, new_deadlines, new_drive):
    for exercise in separates:
        filepath = os.path.join(exercise.dirpath, f'{exercise.key}.ipynb')
        cells, metadata = ipynb_util.load_cells(filepath)
        deadlines_cur = ipynb_metadata.master_metadata_deadlines(metadata)
        deadlines = new_deadlines.get(exercise.key, deadlines_cur)
        if deadlines != deadlines_cur:
            logging.info(f'[INFO] Renew deadline of {exercise.key}')
        drive_cur = ipynb_metadata.master_metadata_drive(metadata)
        drive = new_drive.get(exercise.key, drive_cur)
        if drive != drive_cur:
            logging.info(f'[INFO] Renew Google Drive ID/URL of {exercise.key}')
        metadata = ipynb_metadata.master_metadata(exercise.key, True, exercise.version, exercise.title, deadlines, drive)
        ipynb_util.save_as_notebook(filepath, cells, metadata)

    for dirpath, exercises in bundles.items():
        dirname = os.path.basename(dirpath)
        for exercise in exercises:
            filepath = os.path.join(exercise.dirpath, f'{exercise.key}.ipynb')
            cells, metadata = ipynb_util.load_cells(filepath)
            deadlines_cur = ipynb_metadata.master_metadata_deadlines(metadata)
            deadlines = new_deadlines.get(f'{dirname}/', deadlines_cur)
            if deadlines != deadlines_cur:
                logging.info(f'[INFO] Renew deadline of bundle {dirname}/{exercise.key}')
            drive_cur = ipynb_metadata.master_metadata_drive(metadata)
            drive = new_drive.get(f'{dirname}/', drive_cur)
            if drive != drive_cur:
                logging.info(f'[INFO] Renew Google Drive ID/URL of bundle {dirname}/{exercise.key}')
            metadata = ipynb_metadata.master_metadata(exercise.key, True, exercise.version, exercise.title, deadlines, drive)
            ipynb_util.save_as_notebook(filepath, cells, metadata)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose option')
    parser.add_argument('-d', '--deadlines', metavar='DEADLINES_JSON', help='Specify a JSON file of deadline settings.')
    parser.add_argument('-c', '--configuration', metavar='JUDGE_ENV_JSON', help='Create configuration with environmental parameters specified in JSON.')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, metavar='VERSION', help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-s', '--source', nargs='*', required=True, help=f'Specify source(s) (ipynb files in separate mode and directories in bundle mode)')
    parser.add_argument('-gd', '--google_drive', nargs='?', const='DRIVE_JSON', help='Specify a JSON file of the Google Drive IDs/URLs of distributed forms.')
    parser.add_argument('-ff', '--filled_form', nargs='?', const='form_filled_all.ipynb', help='Generate an all-filled form (default: form_filled_all.ipynb)')
    parser.add_argument('-lp', '--library_placement', nargs='?', metavar='LIBDIR', const='.judge', help='Place judge_util.py for each exercise into LIBDIR (default: .judge).')
    commandline_options = parser.parse_args()
    if commandline_options.verbose:
        logging.getLogger().setLevel('DEBUG')
    else:
        logging.getLogger().setLevel('INFO')

    separates, bundles = load_sources(commandline_options.source)
    exercises = list(itertools.chain(*bundles.values(), separates))

    logging.info('[INFO] Cleaning up exercise masters...')
    for ex in exercises:
        cleanup_exercise_master(ex, commandline_options.renew_version)

    deadlines = {}
    if commandline_options.deadlines:
        with open(commandline_options.deadlines, encoding='utf-8') as f:
            deadlines = json.load(f)
    drive = {}
    if commandline_options.google_drive:
        with open(commandline_options.google_drive, encoding='utf-8') as f:
            drive = json.load(f)
    if deadlines or drive:
        update_exercise_master_metadata_formwise(separates, bundles, deadlines, drive)

    logging.info('[INFO] Creating bundled forms...')
    create_bundled_forms(bundles)
    logging.info('[INFO] Creating separate forms...')
    create_single_forms(separates)

    if commandline_options.library_placement:
        import judge_util
        for dirpath in {ex.dirpath for ex in exercises}:
            dst = os.path.join(dirpath, commandline_options.library_placement)
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(judge_util.__file__, dst)
            logging.info(f'[INFO] Placed `{dst}/judge_util.py`')

    if commandline_options.configuration:
        judge_setting.load_judge_parameters(commandline_options.configuration)
        logging.info(f'[INFO] Creating configuration with `{repr(judge_setting.judge_parameters)}` ...')
        create_configuration(exercises)

    if commandline_options.filled_form:
        logging.info(f'[INFO] Creating filled form `{commandline_options.filled_form}` ...')
        create_filled_form(exercises, commandline_options.filled_form)

if __name__ == '__main__':
    main()
