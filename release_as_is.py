#!/usr/bin/env python3

import argparse
import os
import shutil
import zipfile
import json
import hashlib
import logging
import re

import ipynb_metadata
import ipynb_util

ARCHIVE = 'as-is_masters'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--deadline', metavar='DEADLINE_JSON', help='Specify a JSON file of deadline configuration.')
    parser.add_argument('-c', '--compress', action='store_true', help='Create a zip archive of masters.')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, metavar='VERSION', help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-t', '--targets', nargs='*', required=True, default=[], metavar='TARGET', help='Specify paths to exercise ipynb files.')
    commandline_args = parser.parse_args()

    logging.info(f'[INFO] Creating master ipynb...')
    if commandline_args.deadline:
        with open(commandline_args.deadline, encoding='utf-8') as f:
            deadline = json.load(f)
    else:
        deadline = None
    masters = {}
    for filepath in commandline_args.targets:
        key, ext = os.path.splitext(os.path.basename(filepath))
        assert ext == '.ipynb', f'Not ipynb target: {filepath}'
        cells, metadata = ipynb_util.load_cells(filepath, True)
        assert key not in masters

        if commandline_args.renew_version:
            logging.info(f'[INFO] Renew version of {filepath}')
            if commandline_args.renew_version == hashlib.sha1:
                m = hashlib.sha1()
                m.update(json.dumps(cells).encode())
                version = m.hexdigest()
            else:
                assert isinstance(commandline_args.renew_version, str)
                version = commandline_args.renew_version
        else:
            version = metadata.get('judge_master', {}).get('version', '')

        title = extract_first_heading(cells)
        metadata = ipynb_metadata.master_metadata(key, False, version, title, deadline)
        ipynb_util.save_as_notebook(filepath, cells, metadata)
        logging.info(f'[INFO] Released {filepath}')
        masters[key] = (cells, version, filepath)

    if commandline_args.compress:
        with zipfile.ZipFile(ARCHIVE + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
            logging.info(f'[INFO] Creating zip archive {zipf.filename} of released masters...')
            for filepath in commandline_args.targets:
                zipf.write(filepath, os.path.basename(filepath))
        logging.info(f'[INFO] Released {ARCHIVE}.zip')

    logging.info(f'[INFO] Creating form ipynb...')
    for key, (cells, version, filepath) in masters.items():
        metadata = ipynb_metadata.submission_metadata({key: version}, False)
        ipynb_util.save_as_notebook(os.path.join(os.path.dirname(filepath), f'form_{key}.ipynb'), cells, metadata)

def extract_first_heading(cells):
    for cell_type, source in ipynb_util.normalized_cells(cells):
        if cell_type == ipynb_util.NotebookCellType.MARKDOWN:
            m = re.search(r'^#+\s+(.*)$', source, re.MULTILINE)
            if m:
                return m.groups()[0]
    return None

if __name__ == '__main__':
    logging.getLogger().setLevel('INFO')
    main()
