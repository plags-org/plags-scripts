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
import judge_util
from judge_util import JudgeTestStageBase

if (sys.version_info.major, sys.version_info.minor) < (3, 8):
    print('[ERROR] This script requires Python >= 3.8.')
    sys.exit(1)

INTRODUCTION_FILE = 'intro.ipynb'

CONF_DIR = 'formatted'

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
    path: str       # File path
    title: str      # Title string
    description: Iterable[Cell]                      # DESCRIPTION field
    answer_cell_content: str                         # ANSWER_CELL_CONTENT field
    example_answers: Iterable[Cell]                  # EXAMPLE_ANSWERS field
    instructive_test: Iterable[Cell]                 # INSTRUCTIVE_TEST field
    test_modules: Iterable[Tuple[JudgeTestStageBase,str,str]] # Iterable of modules, which are of type (Stage class, module content, directory path)

    builtin_test_modules = [] # List of module paths

    @classmethod
    def load_builtin_test_modules(cls, paths):
        for path in paths:
            path = os.path.abspath(path)
            with open(path, encoding='utf-8') as f:
                cls.builtin_test_modules.append(interpret_testcode(os.path.dirname(path), f.read()))

    def answer_cell(self):
        s = ANSWER_CELL_FORMAT.format(exercise_key=self.key, content=self.answer_cell_content)
        return ipynb_util.code_cell(s)

    def answer_cell_filled(self):
        s = ANSWER_CELL_FORMAT.format(exercise_key=self.key, content=self.example_answers[0].source if self.example_answers else self.answer_cell_content)
        return ipynb_util.code_cell(s)


def interpret_testcode_cells(dirpath, cells):
    test_modules = list(Exercise.builtin_test_modules)
    test_modules.extend(interpret_testcode(os.path.abspath(dirpath), x.source) for x in cells)
    assert test_modules, f'No stage found: {[x.source for x in cells]}'
    assert len({stage.name for stage, _, _ in test_modules}) == len(test_modules), f'Stage names conflict: {test_modules}'
    for stage, _, _ in test_modules:
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
    return (stage, source + '\n', dirpath)


def split_cells_into_fields(field_enum_type, raw_cells: Iterable[dict]):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'
    fields = {}
    current_key = None
    cells = []
    for cell in ipynb_util.normalized_cells(raw_cells):
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
    path = os.path.abspath(os.path.join(dirpath, exercise_key + '.ipynb'))
    raw_cells, _ = ipynb_util.load_cells(path)
    fields = dict(split_cells_into_fields(FieldKey, raw_cells))

    heading_regex = r'#+\s+(.*)'
    description_first_line = fields[FieldKey.DESCRIPTION][0].source.strip().splitlines()[0]
    title = re.fullmatch(heading_regex, description_first_line).groups()[0]

    test_modules = interpret_testcode_cells(dirpath, fields.pop(FieldKey.SYSTEM_TESTCODE))
    answer_cell_content = fields.pop(FieldKey.ANSWER_CELL_CONTENT)[0].source
    exercise_kwargs = {
        'key': exercise_key, 'path': path, 'title': title, 'test_modules': test_modules, 'answer_cell_content': answer_cell_content,
        **{f.name.lower(): cs for f, cs in fields.items()},
    }
    return Exercise(**exercise_kwargs)


def create_exercise_configuration(exercise: Exercise):
    tests_dir = os.path.join(CONF_DIR, exercise.key)
    os.makedirs(tests_dir, exist_ok=True)

    cells = [x.to_ipynb() for x in itertools.chain(exercise.description, [ipynb_util.code_cell(exercise.answer_cell_content)])]
    _, metadata = ipynb_util.load_cells(exercise.path, True)
    ipynb_metadata.extend_master_metadata_for_trial(metadata, exercise.answer_cell_content)
    ipynb_util.save_as_notebook(os.path.join(CONF_DIR, exercise.key + '.ipynb'), cells, metadata)

    version = ipynb_metadata.master_metadata_version(metadata)
    setting = judge_setting.generate_judge_setting(exercise.key, version, [stage for stage, _, _ in exercise.test_modules], judge_util.ExerciseStyle.FORMATTED)
    with open(os.path.join(tests_dir, 'setting.json'), 'w', encoding='utf-8') as f:
        json.dump(setting, f, indent=1, ensure_ascii=False)

    for stage, content, _ in exercise.test_modules:
        with open(os.path.join(tests_dir, f'{stage.name}.py'), 'w', encoding='utf-8', newline='\n') as f:
            print(content, 'judge_util.unittest_main()', sep='\n', file=f)

    shutil.copy2(judge_util.__file__, tests_dir)
    for stage, _, dirpath in exercise.test_modules:
        for suffix in stage.required_files:
            dest = os.path.join(tests_dir, suffix)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(os.path.join(dirpath, suffix), dest)

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
    assert all(os.path.dirname(ex.path) == os.path.abspath(dirpath) for ex in exercises)
    body = create_bundled_intro(dirpath)
    for exercise in exercises:
        body.extend(exercise.description)
        body.append(exercise.answer_cell())
        body.extend(exercise.instructive_test)
    key_to_ver = {ex.key: ipynb_metadata.master_metadata_version(filepath=ex.path) for ex in exercises}
    metadata = ipynb_metadata.submission_metadata(key_to_ver, True)
    return [c.to_ipynb() for c in body], metadata


def create_bundled_intro(dirpath):
    dirname = os.path.basename(dirpath)
    try:
        raw_cells, _ = ipynb_util.load_cells(os.path.join(dirpath, INTRODUCTION_FILE))
        return list(ipynb_util.normalized_cells(raw_cells))
    except FileNotFoundError:
        return [ipynb_util.markdown_cell(f'# {os.path.basename(dirpath)}')]


def create_single_form(exercise):
    version = ipynb_metadata.master_metadata_version(filepath=exercise.path)
    cells = itertools.chain(exercise.description, [exercise.answer_cell()], exercise.instructive_test)
    metadata =  ipynb_metadata.submission_metadata({exercise.key: version}, True)
    return [c.to_ipynb() for c in cells], metadata


def create_filled_form(exercises):
    key_to_ver = {ex.key: ipynb_metadata.master_metadata_version(filepath=ex.path) for ex in exercises}
    metadata =  ipynb_metadata.submission_metadata(key_to_ver, True)
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
    cells, metadata = ipynb_util.load_cells(exercise.path, True)
    cells_new = [x.to_ipynb() for x in ipynb_util.normalized_cells(cells)]
    version = ipynb_metadata.master_metadata_version(metadata)

    if new_version is None:
        new_version = version
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

    if new_version != version:
        logging.info(f'[INFO] Renew version of {exercise.key}')

    deadlines = ipynb_metadata.master_metadata_deadlines(metadata)
    drive = ipynb_metadata.master_metadata_drive(metadata)
    metadata_new = ipynb_metadata.master_metadata(exercise.key, True, new_version, exercise.title, deadlines, drive)
    ipynb_util.save_as_notebook(exercise.path, cells_new, metadata_new)


def update_exercise_master_metadata_formwise(singles, bundles, new_deadlines, new_drive):
    for exercise in itertools.chain(*bundles.values(), singles):
        cells, metadata = ipynb_util.load_cells(exercise.path)
        deadlines_cur = ipynb_metadata.master_metadata_deadlines(metadata)
        deadlines = new_deadlines.get(exercise.key, deadlines_cur)
        if deadlines != deadlines_cur:
            logging.info(f'[INFO] Renew deadline of {exercise.key}')
        drive_cur = ipynb_metadata.master_metadata_drive(metadata)
        drive = new_drive.get(exercise.key, drive_cur)
        if drive != drive_cur:
            logging.info(f'[INFO] Renew Google Drive ID/URL of {exercise.key}')
        version = ipynb_metadata.master_metadata_version(metadata)
        metadata = ipynb_metadata.master_metadata(exercise.key, True, version, exercise.title, deadlines, drive)
        ipynb_util.save_as_notebook(exercise.path, cells, metadata)

    for dirpath, exercises in bundles.items():
        dirname = os.path.basename(dirpath)
        for exercise in exercises:
            cells, metadata = ipynb_util.load_cells(exercise.path)
            deadlines_cur = ipynb_metadata.master_metadata_deadlines(metadata)
            deadlines = new_deadlines.get(f'{dirname}/', deadlines_cur)
            if deadlines != deadlines_cur:
                logging.info(f'[INFO] Renew deadline of bundle {dirname}/{exercise.key}')
            drive_cur = ipynb_metadata.master_metadata_drive(metadata)
            drive = new_drive.get(f'{dirname}/', drive_cur)
            if drive != drive_cur:
                logging.info(f'[INFO] Renew Google Drive ID/URL of bundle {dirname}/{exercise.key}')
            version = ipynb_metadata.master_metadata_version(metadata)
            metadata = ipynb_metadata.master_metadata(exercise.key, True, version, exercise.title, deadlines, drive)
            ipynb_util.save_as_notebook(exercise.path, cells, metadata)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('src', nargs='+', help=f'Specify source(s) (ipynb files in single mode and directories in bundle mode)')
    parser.add_argument('-d', '--deadlines', metavar='DEADLINES_JSON', help='Specify a JSON file of deadline settings.')
    parser.add_argument('-c', '--configuration', metavar='JUDGE_ENV_JSON', help='Create configuration with environmental parameters specified in JSON.')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, metavar='VERSION', help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-f', '--form_dir', help='Specify a target directory of form generation (defualt: the same as the directory of each master).')
    parser.add_argument('-gd', '--google_drive', metavar='DRIVE_JSON', help='Specify a JSON file of the Google Drive IDs/URLs of distributed forms.')
    parser.add_argument('-ff', '--filled_form', nargs='?', const='form_filled_all.ipynb', help='Generate an all-filled form (default: form_filled_all.ipynb)')
    parser.add_argument('-bt', '--builtin_teststage', nargs='*', default=['rawcheck.py'], help='Specify module files of builtin test stages (default: rawcheck.py)')
    commandline_options = parser.parse_args()

    Exercise.load_builtin_test_modules(commandline_options.builtin_teststage)

    singles, bundles = load_sources(commandline_options.src)
    all_exercises = list(itertools.chain(*bundles.values(), singles))

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
        update_exercise_master_metadata_formwise(singles, bundles, deadlines, drive)

    logging.info('[INFO] Creating bundled forms...')
    for dirpath, exercises in bundles.items():
        cells, metadata = create_bundled_form(dirpath, exercises)
        if commandline_options.form_dir:
            filepath = os.path.join(commandline_options.form_dir, f'{os.path.basename(dirpath)}.ipynb')
        else:
            filepath = os.path.join(dirpath, f'form_{os.path.basename(dirpath)}.ipynb')
        ipynb_util.save_as_notebook(filepath, cells, metadata)
        logging.info(f'[INFO] Generated `{filepath}`')

    logging.info('[INFO] Creating single forms...')
    for exercise in singles:
        cells, metadata = create_single_form(exercise)
        if commandline_options.form_dir:
            filepath = os.path.join(commandline_options.form_dir, f'{exercise.key}.ipynb')
        else:
            filepath = os.path.join(os.path.dirname(exercise.path), f'form_{exercise.key}.ipynb')
        ipynb_util.save_as_notebook(filepath, cells, metadata)
        logging.info(f'[INFO] Generated `{filepath}`')

    for dirpath in {os.path.dirname(ex.path) for ex in all_exercises}:
        shutil.copy2(judge_util.__file__, dirpath)
        logging.info(f'[INFO] Placed `{dirpath}/{judge_util.__name__}.py`')

    if commandline_options.configuration:
        judge_setting.load_judge_parameters(commandline_options.configuration)
        logging.info(f'[INFO] Creating configuration with `{repr(judge_setting.judge_parameters)}` ...')
        create_configuration(all_exercises)

    if commandline_options.filled_form:
        logging.info(f'[INFO] Creating filled form `{commandline_options.filled_form}` ...')
        cells, metadata = create_filled_form(all_exercises)
        ipynb_util.save_as_notebook(commandline_options.filled_form, cells, metadata)


if __name__ == '__main__':
    logging.getLogger().setLevel('INFO')
    main()