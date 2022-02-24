#!/usr/bin/env python3

import argparse
import os
import re
import sys

import ipynb_util


def main():
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
        print('Convert:', path)
        convert_master(path)


def convert_master(filepath):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'

    cells, metadata = ipynb_util.load_cells(filepath)
    for i, c in enumerate(cells):
        if c['cell_type'] == 'markdown':
            matches = list(re.finditer(CONTENT_TYPE_REGEX, ''.join(c['source'])))
            if not matches:
                continue
            key = matches[0][1]
            if key in REWRITE_RULES:
                c['source'] = REWRITE_RULES[key].splitlines(True)
            if key == 'PLAYGROUND':
                cells[i+1]['source'] = ['judge_util.unittest_main()']

    new_cells = []
    deleting = False
    for c in cells:
        if c['cell_type'] == 'markdown':
            matches = list(re.finditer(CONTENT_TYPE_REGEX, ''.join(c['source'])))
            if matches:
                deleting = False
                if matches[0][1] in DELETED_FIELDS:
                    deleting = True
        if not deleting:
            new_cells.append(c)

    ipynb_util.save_as_notebook(filepath, new_cells, metadata)


DELETED_FIELDS = {
    'COMMENTARY',
}

REWRITE_RULES = {
    'SYSTEM_TESTCODE': """
***CONTENT_TYPE: SYSTEM_TESTCODE***  
次の点に留意して自動評価に使われるテストコードを記述してください．

* **1つのコードセルが1つの独立したモジュール**になります．
* 1つのモジュールが1つのstageとして扱われ，セルの出現順で実行されます．
* 各セルに `judge_util.teststage` が返すクラスを，**グローバルに1つ**定義してください．

複数セル可，省略可．
""".strip(),
}


if __name__ == '__main__':
    main()
