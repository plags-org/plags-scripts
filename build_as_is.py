#!/usr/bin/env python3

import os
import re
import sys
import shutil
import zipfile
import argparse
import dataclasses
from typing import Iterable, Tuple

import json
import hashlib
import logging
import contextlib
import io

import ipynb_metadata
import ipynb_util
import judge_util
from judge_util import JudgeTestStageBase
import judge_setting
import testcase_translator


if (sys.version_info.major, sys.version_info.minor) < (3, 8):
    print('[ERROR] This script requires Python >= 3.8.')
    sys.exit(1)


CONF_DIR = 'conf'


@dataclasses.dataclass
class Exercise:
    key: str        # Key string
    path: str       # File path
    title: str      # Title string
    answer_cell_content: str = ''
    test_modules: Iterable[Tuple[JudgeTestStageBase,str,str]] = dataclasses.field(default_factory=list)  # Iterable of modules, which are of type (Stage class, module content, directory path)

    def load_test_modules(self, test_module_paths):
        test_modules = []
        for path in test_module_paths:
            with contextlib.suppress(FileNotFoundError):
                test_modules.append(interpret_test_module(path))
        assert test_modules, f'No stage found: {test_module_paths}'
        assert len({stage.name for stage, _, _ in test_modules}) == len(test_modules), f'Stage names conflict: {test_modules}'
        self.test_modules = test_modules


def interpret_test_module(path):
    with open(path, encoding='utf-8') as f:
        source = f.read()
    path = os.path.abspath(path)
    dirpath, basename = os.path.split(path)
    modname, _ = os.path.splitext(basename)

    lines = source.splitlines()
    if lines and lines[0].startswith('#!'):
        shebang_cmd = lines[0][len('#!'):].split()
        cmd_name = f'{testcase_translator.__name__}.py'
        cmd_index = max(-1, min(i for i, c in enumerate(shebang_cmd) if os.path.basename(c) == cmd_name))
        if cmd_index >= 0:
            stdin = sys.stdin
            sys.stdin = io.StringIO(source)
            source = testcase_translator.main(shebang_cmd[cmd_index+1:])
            sys.stdin = stdin

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
        stage.name = modname
    return (stage, source + '\n', dirpath)


def extract_first_heading(cells):
    for cell_type, source in ipynb_util.normalized_cells(cells):
        if cell_type == ipynb_util.CellType.MARKDOWN:
            m = re.search(r'^#+\s+(.*)$', source, re.MULTILINE)
            if m:
                return m.groups()[0]
    return None


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


def create_exercise_configuration(exercise: Exercise):
    tests_dir = os.path.join(CONF_DIR, exercise.key)
    os.makedirs(tests_dir, exist_ok=True)

    cells, metadata = ipynb_util.load_cells(exercise.path, True)
    if exercise.answer_cell_content:
        cells.append(ipynb_util.code_cell(exercise.answer_cell_content).to_ipynb())
    ipynb_util.save_as_notebook(os.path.join(CONF_DIR, f'{exercise.key}.ipynb'), cells, metadata)

    if not exercise.test_modules:
        return

    version = ipynb_metadata.master_metadata_version(metadata)
    setting = judge_setting.generate_judge_setting(exercise.key, version, [stage for stage, _, _ in exercise.test_modules], judge_util.ExerciseStyle.AS_IS)
    with open(os.path.join(tests_dir, 'setting.json'), 'w', encoding='utf-8') as f:
        json.dump(setting, f, indent=1, ensure_ascii=False)

    for stage, content, _ in exercise.test_modules:
        with open(os.path.join(tests_dir, f'{stage.name}.py'), 'w', encoding='utf-8', newline='\n') as f:
            print(content, 'judge_util.unittest_main()', sep='\n', file=f)

    for stage, _, dirpath in exercise.test_modules:
        shutil.copy2(judge_util.__file__, tests_dir)
        for suffix in stage.required_files:
            dest = os.path.join(tests_dir, suffix)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(os.path.join(dirpath, suffix), dest)


def load_sources(source_paths: Iterable[str]):
    exercises = []
    existing_keys = {}
    for path in sorted(source_paths):
        exercise_key, ext = os.path.splitext(os.path.basename(path))
        if ext != '.ipynb':
            logging.info(f'[INFO] Skip {path}')
            continue
        assert exercise_key not in existing_keys, \
            f'[ERROR] Exercise key conflicts between `{path}` and `{existing_keys[exercise_key]}`.'
        existing_keys[exercise_key] = path

        raw_cells, metadata = ipynb_util.load_cells(path)
        title = extract_first_heading(raw_cells) or exercise_key
        exercises.append(Exercise(key=exercise_key, path=path, title=title))
        logging.info(f'[INFO] Loaded `{path}`')
    return exercises


def cleanup_exercise_master_metadata(exercise, new_version=None):
    cells, metadata = ipynb_util.load_cells(exercise.path, True)
    version = ipynb_metadata.master_metadata_version(metadata)

    if new_version is None:
        new_version = version
    elif new_version == hashlib.sha1:
        m = hashlib.sha1()
        m.update(json.dumps(cells).encode())
        new_version = m.hexdigest()
    else:
        assert isinstance(new_version, str)

    if new_version != version:
        logging.info(f'[INFO] Renew version of {exercise.key}')

    deadlines = ipynb_metadata.master_metadata_deadlines(metadata)
    drive = ipynb_metadata.master_metadata_drive(metadata)
    metadata_new = ipynb_metadata.master_metadata(exercise.key, bool(exercise.test_modules), new_version, exercise.title, deadlines, drive)
    ipynb_util.save_as_notebook(exercise.path, cells, metadata_new)


def update_exercise_master_metadata(exercises, new_deadlines, new_drive):
    for ex in exercises:
        cells, metadata = ipynb_util.load_cells(ex.path)
        deadlines_cur = ipynb_metadata.master_metadata_deadlines(metadata)
        deadlines = new_deadlines.get(ex.key, deadlines_cur)
        if deadlines != deadlines_cur:
            logging.info(f'[INFO] Renew deadline of {ex.key}')
        drive_cur = ipynb_metadata.master_metadata_drive(metadata)
        drive = new_drive.get(ex.key, drive_cur)
        if drive != drive_cur:
            logging.info(f'[INFO] Renew Google Drive ID/URL of {ex.key}')
        version = ipynb_metadata.master_metadata_version(metadata)
        metadata = ipynb_metadata.master_metadata(ex.key,  bool(ex.test_modules), version, ex.title, deadlines, drive)
        ipynb_util.save_as_notebook(ex.path, cells, metadata)


def append_answer_cell(cells, content):
    body = {
        'cell_type': 'code',
        'execution_count': None,
        'metadata': judge_util.answer_cell_metadata(),
        'outputs': [],
        'source': content.strip().splitlines(True),
    }
    header = {
        'cell_type': 'markdown',
        'metadata': {'editable': False},
        'source': ['## 解答（セルの複製削除不可）'],
    }
    cells.extend((header, body))


def append_question_cell(cells):
    body = {
        'cell_type': 'markdown',
        'metadata': judge_util.question_cell_metadata(),
        'source': [],
    }
    header = {
        'cell_type': 'markdown',
        'metadata': {'editable': False},
        'source': ['## 質問（セルの複製削除不可）'],
    }
    cells.extend((header, body))


def append_test_results(cells, exercise):
    results = run_test(exercise)
    body = [{
        'cell_type': 'code',
        'execution_count': None,
        'metadata': {},
        'outputs': [
            {
                'data': {
                    'text/html': html.data.splitlines(True),
                    'text/plain': str(html).splitlines(True),
                },
                'execution_count': None,
                'metadata': {},
                'output_type': 'execute_result',
            }
        ],
        'source': source.splitlines(True),
    } for html, source in results]
    header = {
        'cell_type': 'markdown',
        'metadata': {},
        'source': ['## テストコードとその実行結果'],
    }
    cells.append(header)
    cells.extend(body)


def run_test(exercise):
    path = sys.path
    cwd = os.getcwd()

    results = []
    test_mod_name = '_test_mod'
    for stage, content, dirpath in exercise.test_modules:
        os.chdir(dirpath)
        sys.path = [os.getcwd()] + path

        with open(f'{test_mod_name}.py', 'w', encoding='utf-8') as f:
            print(content, file=f)
        import importlib
        if test_mod_name in sys.modules:
            test_mod = sys.modules[test_mod_name]
            for name in dir(test_mod):
                if not name.startswith('__'):
                    delattr(test_mod, name)
            test_mod = importlib.reload(test_mod)
        else:
            test_mod = importlib.import_module(test_mod_name)

        cells = []
        append_answer_cell(cells, exercise.answer_cell_content)
        ipynb_util.save_as_notebook(judge_util.ExerciseStyle.AS_IS.submission_filename(), cells, {})

        html = judge_util.unittest_main(on_ipynb=True, module=test_mod)
        results.append((html, content))

        os.remove(judge_util.ExerciseStyle.AS_IS.submission_filename())
        os.remove(f'{test_mod_name}.py')

    os.chdir(cwd)
    sys.path = path
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('src', nargs='+', help=f'Specify source ipynb file(s).')
    parser.add_argument('-d', '--deadlines', metavar='DEADLINES_JSON', help='Specify a JSON file of deadline settings.')
    parser.add_argument('-c', '--configuration', nargs='?', const='', metavar='JUDGE_ENV_JSON', help='Create configuration with environmental parameters specified in JSON.')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, metavar='VERSION', help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-f', '--form_dir', nargs='?', help='Specify a target directory of form generation (defualt: the same as the directory of each master).')
    parser.add_argument('-gd', '--google_drive', nargs='?', metavar='DRIVE_JSON', help='Specify a JSON file of the Google Drive IDs/URLs of distributed forms.')
    parser.add_argument('-ag', '--autograde', nargs='?', const='', metavar='TEST_MOD_JSON', help='Enable auto tests, optionally taking a JSON file to specify test modules (default: test_${exercise_key}.py).')
    parser.add_argument('-bt', '--builtin_teststage', nargs='*', default=['rawcheck_as_is.py'], help='Specify module files of builtin test stages (default: rawcheck_as_is.py), enabled if -ag/--autograde is also specified.')
    parser.add_argument('-ac', '--answer_cell', nargs='?', const='',  metavar='PREFILL_CONTENT_JSON', help='Append an answer cell to each form, optionally taking a JSON file to specify prefill answer content (default: ${exercise_key}.py if exists).')
    parser.add_argument('-qc', '--question_cell', action='store_true', help='Append a qustion cell to each form.')
    parser.add_argument('-t', '--run_test', nargs='?', const='', metavar='RESULT_DIR', help='Run tests for all the exercises, optionally taking a target directory of result generation (defualt: the same as the directory of each master).')
    commandline_options = parser.parse_args()

    exercises = load_sources(commandline_options.src)

    if commandline_options.autograde is not None:
        mod_dict = {}
        if commandline_options.autograde != '':
            with open(commandline_options.autograde, encoding='utf-8') as f:
                mod_dict = json.load(f)
        for ex in exercises:
            builtin_paths = commandline_options.builtin_teststage
            mod_paths = mod_dict.get(ex.key, [os.path.join(os.path.dirname(ex.path), f'test_{ex.key}.py')])
            ex.load_test_modules(builtin_paths + mod_paths)

    if commandline_options.answer_cell is not None:
        ans_dict = {}
        if commandline_options.answer_cell != '':
            with open(commandline_options.answer_cell, encoding='utf-8') as f:
                ans_dict = json.load(f)
        for ex in exercises:
            path = ans_dict.get(ex.key, os.path.join(os.path.dirname(ex.path), f'{ex.key}.py'))
            with contextlib.suppress(FileNotFoundError), open(path, encoding='utf-8') as f:
                ex.answer_cell_content = f.read()

    logging.info('[INFO] Cleaning up exercise master metadata...')
    for ex in exercises:
        cleanup_exercise_master_metadata(ex, commandline_options.renew_version)

    deadlines = {}
    if commandline_options.deadlines:
        with open(commandline_options.deadlines, encoding='utf-8') as f:
            deadlines = json.load(f)
    drive = {}
    if commandline_options.google_drive:
        with open(commandline_options.google_drive, encoding='utf-8') as f:
            drive = json.load(f)
    if deadlines or drive:
        update_exercise_master_metadata(exercises, deadlines, drive)

    logging.info('[INFO] Creating forms...')
    for ex in exercises:
        cells, metadata = ipynb_util.load_cells(ex.path, True)
        version = ipynb_metadata.master_metadata_version(metadata)
        submission_metadata =  ipynb_metadata.submission_metadata({ex.key: version}, False)
        if commandline_options.form_dir:
            filepath = os.path.join(commandline_options.form_dir, f'{ex.key}.ipynb')
        else:
            filepath = os.path.join(os.path.dirname(ex.path), f'form_{ex.key}.ipynb')
        if commandline_options.answer_cell is not None:
            append_answer_cell(cells, ex.answer_cell_content)
        if commandline_options.question_cell:
            append_question_cell(cells)
        ipynb_util.save_as_notebook(filepath, cells, submission_metadata)
        logging.info(f'[INFO] Generated `{filepath}`')

    if commandline_options.run_test is not None:
        logging.info('[INFO] Creating test results...')
        for ex in exercises:
            cells, metadata = ipynb_util.load_cells(ex.path, True)
            version = ipynb_metadata.master_metadata_version(metadata)
            submission_metadata =  ipynb_metadata.submission_metadata({ex.key: version}, False)
            if commandline_options.run_test:
                filepath = os.path.join(commandline_options.run_test, f'{ex.key}.ipynb')
            else:
                filepath = os.path.join(ex.dirpath, f'result_{ex.key}.ipynb')
            append_answer_cell(cells, ex.answer_cell_content)
            append_test_results(cells, ex)
            ipynb_util.save_as_notebook(filepath, cells, submission_metadata)
            logging.info(f'[INFO] Generated `{filepath}`')

    if commandline_options.configuration is not None:
        if commandline_options.configuration:
            assert commandline_options.autograde is not None
            judge_setting.load_judge_parameters(commandline_options.configuration)
            logging.info(f'[INFO] Creating configuration with `{repr(judge_setting.judge_parameters)}` ...')
        else:
            assert commandline_options.autograde is None
            logging.info(f'[INFO] Creating configuration with no autograde ...')
        create_configuration(exercises)


if __name__ == '__main__':
    logging.getLogger().setLevel('INFO')
    main()
