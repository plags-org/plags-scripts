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
from typing import Iterable, Tuple

import json
import hashlib
import logging
import itertools

import ipynb_metadata
import ipynb_util
from ipynb_util import CellType, Cell
import judge_setting
from judge_util import JudgeTestStageBase

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
    IGNORED = enum.auto()

FieldKey.WARNING.properties = FieldProperty.IGNORED
FieldKey.DESCRIPTION.properties = FieldProperty.LIST | FieldProperty.MARKDOWN_HEADED
FieldKey.ANSWER_CELL_CONTENT.properties = FieldProperty.SINGLE | FieldProperty.CODE
FieldKey.EXAMPLE_ANSWERS.properties = FieldProperty.LIST | FieldProperty.OPTIONAL
FieldKey.INSTRUCTIVE_TEST.properties = FieldProperty.LIST | FieldProperty.OPTIONAL
FieldKey.SYSTEM_TESTCODE.properties = FieldProperty.LIST | FieldProperty.CODE | FieldProperty.OPTIONAL
FieldKey.PLAYGROUND.properties = FieldProperty.IGNORED

@dataclasses.dataclass
class Exercise:
    key: str        # Key string
    dirpath: str    # Directory path
    version: str    # Version string
    title: str      # Title string
    description: Iterable[Cell]                      # DESCRIPTION field
    answer_cell_content: Cell                        # ANSWER_CELL_CONTENT field
    example_answers: Iterable[Cell]                  # EXAMPLE_ANSWERS field
    instructive_test: Iterable[Cell]                 # INSTRUCTIVE_TEST field
    test_modules: Iterable[Tuple[JudgeTestStageBase,str]] # Iterable of modules, which are of type (Stage class, module content)

    builtin_test_modules = [] # List of module paths

    def answer_cell(self):
        s = ANSWER_CELL_FORMAT.format(exercise_key=self.key, content=self.answer_cell_content.source)
        return ipynb_util.code_cell(s)

    def answer_cell_filled(self):
        s = ANSWER_CELL_FORMAT.format(exercise_key=self.key, content=self.example_answers[0].source if self.example_answers else self.answer_cell_content.source)
        return ipynb_util.code_cell(s)


def interpret_testcode_cells(dirpath, cells):
    dummy_source = """
import sys
sys.path.append('.judge')
import judge_util # モジュール全体をそのままの名前でimport

Dummy = judge_util.teststage()
""".lstrip()
    test_modules = []
    for path in Exercise.builtin_test_modules:
        with open(path, encoding='utf-8') as f:
            test_modules.append(interpret_testcode(os.path.dirname(path), f.read()))
    if cells:
        test_modules.extend(interpret_testcode(dirpath, x.source) for x in cells)
    else:
        test_modules.append(interpret_testcode('.', dummy_source))

    assert len({stage.name for stage, _ in test_modules}) == len(test_modules), f'Stage names conflict: {test_modules}'
    for stage, _ in test_modules:
        # Validation of score
        assert all(s is None or (isinstance(s, int) and s >= 0) for s in (getattr(stage, k) for k in ('score', 'unsuccessful_score')))
        if all(isinstance(getattr(stage, k), int) for k in ('score', 'unsuccessful_score')):
            assert stage.score >= stage.unsuccessful_score

    return test_modules


def interpret_testcode(dirpath, source):
    source = source.strip()
    env = {'__name__': '__main__'}
    path = sys.path[:]
    cwd = os.getcwd()
    os.chdir(dirpath)
    exec(source, env)
    sys.path = path
    os.chdir(cwd)
    file_paths = []
    decls = [(n,v) for n, v in env.items() if isinstance(v, type) and issubclass(v, JudgeTestStageBase)]
    assert len(decls) == 1
    (name, stage), *_ = decls
    if stage.name is None:
        stage.name = name
    return (stage, source + '\n')


def split_cells_into_fields(field_enum_type, raw_cells: Iterable[dict]):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'
    fields = {}
    current_key = None
    cells = []
    for cell in ipynb_util.normalized_cells(raw_cells):
        logging.debug('[TRACE] %s %s', current_key, repr(cell.source if len(cell.source) <= 64 else cell.source[:64] + ' ...'))
        if cell.source == '':
            continue

        if cell.cell_type in (CellType.CODE, CellType.RAW):
            assert current_key is not None
            cells.append(cell)
            continue
        assert cell.cell_type == CellType.MARKDOWN

        matches = list(re.finditer(CONTENT_TYPE_REGEX, cell.source))
        if len(matches) == 0:
            assert current_key is not None
            cells.append(cell)
            continue
        assert len(matches) == 1, f'Multiple field keys found in cell `{cell.source}`.'

        if current_key is not None:
            fields[current_key] = cells
            cells = []
        current_key = matches[0][1]

    fields[current_key] = cells

    # Validate fields by field_enum_type
    for field_key, cells in fields.items():
        field_enum = getattr(field_enum_type, field_key)
        if FieldProperty.IGNORED in field_enum.properties:
            continue
        logging.debug(f'[TRACE] Validate field `{field_enum}`')

        if (FieldProperty.LIST | FieldProperty.OPTIONAL) in field_enum.properties:
            pass
        elif FieldProperty.OPTIONAL in field_enum.properties:
            assert len(cells) <= 1, f'Field of `{field_enum}` must have at most 1 cell but has {len(cells)}.'
        elif FieldProperty.LIST in field_enum.properties:
            assert len(cells) > 0, f'Field of `{field_enum}` must not be empty.'
        elif FieldProperty.SINGLE in field_enum.properties:
            assert len(cells) == 1, f'Field of `{field_enum}` must have 1 cell.'

        if FieldProperty.CODE in field_enum.properties:
            assert all(x.cell_type == CellType.CODE for x in cells), f'Field of `{field_enum}` must have only code cell(s).'

        if len(cells) > 0 and FieldProperty.MARKDOWN_HEADED in field_enum.properties:
            assert cells[0].cell_type == CellType.MARKDOWN
            first_line_regex = r'#+\s+(.*)'
            first_line = cells[0].source.strip().splitlines()[0]
            m = re.fullmatch(first_line_regex, first_line)
            assert m is not None, f'The first content cell does not start with a heading in Markdown: `{first_line}`.'

        yield field_enum, cells


def load_exercise(dirpath, exercise_key):
    raw_cells, metadata = ipynb_util.load_cells(os.path.join(dirpath, exercise_key + '.ipynb'))
    version = ipynb_metadata.master_metadata_version(metadata)

    fields = dict(split_cells_into_fields(FieldKey, raw_cells))

    heading_regex = r'#+\s+(.*)'
    description_first_line = fields[FieldKey.DESCRIPTION][0].source.strip().splitlines()[0]
    title = re.fullmatch(heading_regex, description_first_line).groups()[0]

    test_modules = interpret_testcode_cells(dirpath, fields.pop(FieldKey.SYSTEM_TESTCODE))

    exercise_kwargs = {
        'key': exercise_key, 'dirpath': dirpath, 'version': version, 'title': title, 'test_modules': test_modules,
        **{f.name.lower(): cs[0] if f == FieldKey.ANSWER_CELL_CONTENT else cs for f, cs in fields.items()},
    }
    return Exercise(**exercise_kwargs)


def create_exercise_configuration(exercise: Exercise):
    tests_dir = os.path.join(CONF_DIR, exercise.key)
    os.makedirs(tests_dir, exist_ok=True)

    cells = [x.to_ipynb() for x in itertools.chain(exercise.description, [exercise.answer_cell_content])]
    _, metadata = ipynb_util.load_cells(os.path.join(exercise.dirpath, exercise.key + '.ipynb'), True)
    ipynb_metadata.extend_master_metadata_for_trial(metadata, exercise.answer_cell_content.source)
    ipynb_util.save_as_notebook(os.path.join(CONF_DIR, exercise.key + '.ipynb'), cells, metadata)

    setting = judge_setting.generate_judge_setting(exercise.key, exercise.version, [stage for stage, _ in exercise.test_modules])
    with open(os.path.join(tests_dir, 'setting.json'), 'w', encoding='utf-8') as f:
        json.dump(setting, f, indent=1, ensure_ascii=False)

    for stage, content in exercise.test_modules:
        with open(os.path.join(tests_dir, f'{stage.name}.py'), 'w', encoding='utf-8', newline='\n') as f:
            print(content, 'judge_util.unittest_main()', sep='\n', file=f)

    for path in itertools.chain(*(stage.required_files for stage, _ in exercise.test_modules)):
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


def create_bundled_form(dirpath, exercises):
    assert all(ex.dirpath == dirpath for ex in exercises)
    body = create_bundled_intro(dirpath)
    for exercise in exercises:
        body.extend(exercise.description)
        body.append(exercise.answer_cell())
        body.extend(exercise.instructive_test)
    key_to_ver = {ex.key: ex.version for ex in exercises}
    metadata = ipynb_metadata.submission_metadata(key_to_ver, True)
    return [c.to_ipynb() for c in body], metadata


def create_bundled_intro(dirpath):
    dirname = os.path.basename(dirpath)
    try:
        raw_cells, _ = ipynb_util.load_cells(os.path.join(dirpath, INTRODUCTION_FILE))
        return list(ipynb_util.normalized_cells(raw_cells))
    except FileNotFoundError:
        return [ipynb_util.markdown_cell(f'# {os.path.basename(dirpath)}')]


def create_separate_form(exercise):
    cells = itertools.chain(exercise.description, [exercise.answer_cell()], exercise.instructive_test)
    metadata =  ipynb_metadata.submission_metadata({exercise.key: exercise.version}, True)
    return [c.to_ipynb() for c in cells], metadata


def create_filled_form(exercises):
    metadata =  ipynb_metadata.submission_metadata({ex.key: ex.version for ex in exercises}, True)
    return [ex.answer_cell_filled().to_ipynb() for ex in exercises], metadata


def load_sources(source_paths: Iterable[str], *, master_loader=load_exercise):
    exercises = []
    bundles = collections.defaultdict(list)
    existing_keys = {}
    for path in sorted(source_paths):
        if os.path.isdir(path):
            dirpath = path
            parent, dirname = os.path.split(dirpath)
            dirname = dirname if dirname else os.path.basename(parent)
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
    cells_new = [x.to_ipynb() for x in ipynb_util.normalized_cells(cells)]

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
    for exercise in itertools.chain(*bundles.values(), separates):
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
    parser.add_argument('-f', '--form_dir', nargs='?', const='DIR', help='Specify a target directory of form generation (defualt: the same as the directory of each master).')
    parser.add_argument('-s', '--source', nargs='*', required=True, help=f'Specify source(s) (ipynb files in separate mode and directories in bundle mode)')
    parser.add_argument('-gd', '--google_drive', nargs='?', const='DRIVE_JSON', help='Specify a JSON file of the Google Drive IDs/URLs of distributed forms.')
    parser.add_argument('-ff', '--filled_form', nargs='?', const='form_filled_all.ipynb', help='Generate an all-filled form (default: form_filled_all.ipynb)')
    parser.add_argument('-lp', '--library_placement', nargs='?', metavar='LIBDIR', const='.judge', help='Place judge_util.py for each exercise into LIBDIR (default: .judge).')
    parser.add_argument('-bt', '--builtin_teststage', nargs='*', default=['rawcheck.py'], help='Specify module files of builtin test stages (default: rawcheck.py)')
    commandline_options = parser.parse_args()
    if commandline_options.verbose:
        logging.getLogger().setLevel('DEBUG')
    else:
        logging.getLogger().setLevel('INFO')

    Exercise.builtin_test_modules.extend(os.path.abspath(x) for x in commandline_options.builtin_teststage)

    separates, bundles = load_sources(commandline_options.source)
    all_exercises = list(itertools.chain(*bundles.values(), separates))

    logging.info('[INFO] Cleaning up exercise masters...')
    for ex in all_exercises:
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
    for dirpath, exercises in bundles.items():
        cells, metadata = create_bundled_form(dirpath, exercises)
        if commandline_options.form_dir:
            filepath = os.path.join(commandline_options.form_dir, f'{os.path.basename(dirpath)}.ipynb')
        else:
            filepath = os.path.join(dirpath, f'form_{os.path.basename(dirpath)}.ipynb')
        ipynb_util.save_as_notebook(filepath, cells, metadata)
        logging.info(f'[INFO] Generated `{filepath}`')

    logging.info('[INFO] Creating separate forms...')
    for exercise in separates:
        cells, metadata = create_separate_form(exercise)
        if commandline_options.form_dir:
            filepath = os.path.join(commandline_options.form_dir, f'{exercise.key}.ipynb')
        else:
            filepath = os.path.join(exercise.dirpath, f'form_{exercise.key}.ipynb')
        ipynb_util.save_as_notebook(filepath, cells, metadata)
        logging.info(f'[INFO] Generated `{filepath}`')

    if commandline_options.library_placement:
        import judge_util
        for dirpath in {ex.dirpath for ex in all_exercises}:
            dst = os.path.join(dirpath, commandline_options.library_placement)
            os.makedirs(dst, exist_ok=True)
            shutil.copy2(judge_util.__file__, dst)
            logging.info(f'[INFO] Placed `{dst}/judge_util.py`')

    if commandline_options.configuration:
        judge_setting.load_judge_parameters(commandline_options.configuration)
        logging.info(f'[INFO] Creating configuration with `{repr(judge_setting.judge_parameters)}` ...')
        create_configuration(all_exercises)

    if commandline_options.filled_form:
        logging.info(f'[INFO] Creating filled form `{commandline_options.filled_form}` ...')
        cells, metadata = create_filled_form(all_exercises)
        ipynb_util.save_as_notebook(commandline_options.filled_form, cells, metadata)


if __name__ == '__main__':
    main()
