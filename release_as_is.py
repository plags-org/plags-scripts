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
    parser.add_argument('-d', '--deadlines', metavar='DEADLINES_JSON', help='Specify a JSON file of deadline settings.')
    parser.add_argument('-c', '--compress_masters', action='store_true', help='Create a zip archive of masters.')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, metavar='VERSION', help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-s', '--source', nargs='*', required=True, help='Specify source ipynb file(s).')
    commandline_args = parser.parse_args()

    new_deadlines = {}
    if commandline_args.deadlines:
        with open(commandline_args.deadlines, encoding='utf-8') as f:
            new_deadlines = json.load(f)

    existing_keys = {}
    for filepath in commandline_args.source:
        key, ext = os.path.splitext(os.path.basename(filepath))
        assert ext == '.ipynb', f'Not ipynb: {filepath}'
        assert key not in existing_keys, \
            f'[ERROR] Exercise key conflicts between `{filepath}` and `{existing_keys[key]}`.'
        existing_keys[key] = filepath
        release_ipynb(filepath, new_deadlines, commandline_args.renew_version)

    if commandline_args.compress_masters:
        with zipfile.ZipFile(ARCHIVE + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
            logging.info(f'[INFO] Creating zip archive {zipf.filename} of released masters...')
            for filepath in commandline_args.source:
                zipf.write(filepath, os.path.basename(filepath))
        logging.info(f'[INFO] Released {ARCHIVE}.zip')


def release_ipynb(master_path, new_deadlines, new_version):
    key, ext = os.path.splitext(os.path.basename(master_path))
    cells, metadata = ipynb_util.load_cells(master_path, True)
    title = extract_first_heading(cells)
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
        logging.info(f'[INFO] Renew version of `{master_path}`')
        version = new_version

    deadlines_cur = ipynb_metadata.master_metadata_deadlines(metadata)
    deadlines = new_deadlines.get(key, deadlines_cur)
    if deadlines != deadlines_cur:
        logging.info(f'[INFO] Renew deadline of `{master_path}`')

    master_metadata = ipynb_metadata.master_metadata(key, False, version, title, deadlines)
    ipynb_util.save_as_notebook(master_path, cells, master_metadata)
    logging.info(f'[INFO] Released master `{master_path}`')

    form_path = os.path.join(os.path.dirname(master_path), f'form_{key}.ipynb')
    submission_metadata = ipynb_metadata.submission_metadata({key: version}, False)
    ipynb_util.save_as_notebook(form_path, cells, submission_metadata)
    logging.info(f'[INFO] Released form `{form_path}`')


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
