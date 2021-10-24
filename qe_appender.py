#!/usr/bin/env python3

import argparse
import logging
import os
import re
import sys

import ipynb_util

if (sys.version_info.major, sys.version_info.minor) < (3, 8):
    print('[ERROR] This script requires Python >= 3.8.')
    sys.exit(1)


def main():
    logging.getLogger().setLevel('INFO')
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--source', nargs='*', required=True, help=f'Specify source(s) (ipynb files in separate mode and directories in bundle mode)')
    commandline_options = parser.parse_args()

    paths = []
    for path in sorted(commandline_options.source):
        if os.path.isdir(path):
            dirpath = path
            dirname = os.path.basename(dirpath)
            for nb in sorted(os.listdir(dirpath)):
                if re.fullmatch(fr'({dirname}[-_].*)\.ipynb', nb):
                    paths.append(os.path.join(dirpath, nb))
        else:
            if path.endswith('.ipynb'):
                paths.append(path)

    for path in paths:
        add_question_exists_into_answer_cell(path)


def add_question_exists_into_answer_cell(filepath):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'

    cells, metadata = ipynb_util.load_cells(filepath)
    for i, c in enumerate(cells):
        if c['cell_type'] == 'markdown':
            matches = list(re.finditer(CONTENT_TYPE_REGEX, ''.join(c['source'])))
            if not matches:
                continue
            key = matches[0][1]
            if key == 'ANSWER_CELL_CONTENT' and all('QUESTION_EXISTS = False' not in x for x in cells[i+1]['source']):
                print('Append QUESTION_EXISTS: ', filepath)
                cells[i+1]['source'][0:0] = ['QUESTION_EXISTS = False # 質問がある場合は True にしてコメントに質問を記述\n', '\n']

            if key == 'SYSTEM_TESTCODE' and all('question_exists' not in x for x in cells[i+1]['source']):
                print('Append question_exists: ', filepath)
                cells[i+1]['source'][-1] = cells[i+1]['source'][-1] + '\n'
                cells[i+1]['source'].extend(PRECHECK_QUESTION_EXISTS_TEMPLATE.splitlines(True))

    ipynb_util.save_as_notebook(filepath, cells, metadata)

PRECHECK_QUESTION_EXISTS_TEMPLATE = """
# 得点に影響しないタグ付け
@judge_util.check_method(Precheck)
def question_exists(self):
    try:
        QUESTION_EXISTS
    except NameError:
        pass
    else:
        if QUESTION_EXISTS:
            judge_util.set_ok_tag(self, 'QE')
""".rstrip()


if __name__ == '__main__':
    main()
