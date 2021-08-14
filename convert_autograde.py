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
        correct_typos_master(path)


def correct_typos_master(filepath):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'

    cells, metadata = ipynb_util.load_cells(filepath)
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
    'SYSTEM_TEST_SETTING',
}


if __name__ == '__main__':
    main()
