#! /usr/bin/env python3

import argparse
import os
import shutil
import zipfile
import json
import hashlib
import logging

import ipynb_metadata
import ipynb_util

MASTERS_DIR = 'as-is_masters'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--add', metavar='TARGET_DIR', help='Add masters to a target directory.')
    parser.add_argument('-d', '--deadline', metavar='DEADLINE_JSON', help='Specify a JSON file of deadline configuration.')
    parser.add_argument('-z', '--zip_masters', action='store_true', help='Create a zip archive of masters.')
    parser.add_argument('-n', '--renew_version', nargs='?', const=hashlib.sha1, metavar='VERSION', help='Renew the versions of every exercise (default: the SHA1 hash of each exercise definition)')
    parser.add_argument('-t', '--targets', nargs='*', default=[], metavar='TARGET', help='Specify paths to exercise ipynb files.')
    commandline_args = parser.parse_args()

    existing_keys = frozenset(os.path.splitext(x)[0] for x in (os.listdir(commandline_args.add) if commandline_args.add else []))
    submission_forms = create_submission_forms(commandline_args.targets,
                                               commandline_args.renew_version,
                                               existing_keys)
    if commandline_args.deadline:
        with open(commandline_args.deadline, encoding='utf-8') as f:
            deadline = json.load(f)
    else:
        deadline = None
    create_masters(submission_forms,
                   commandline_args.add,
                   commandline_args.zip_masters,
                   deadline)

def create_submission_forms(targets, renew_version, existing_keys=frozenset()):
    logging.info(f'[INFO] Normalizing as-is exercise ipynb...')
    forms = {}
    for filepath in targets:
        key, ext = os.path.splitext(os.path.basename(filepath))
        assert ext == '.ipynb', f'Not ipynb target: {filepath}'
        cells, metadata = ipynb_util.load_cells(filepath, True)

        if key in existing_keys:
            logging.info(f'[INFO] Exercise {key} shall be overwritten with {filepath}')
        assert key not in forms, f'Conflict of exercise key: {key}'
        if renew_version:
            logging.info(f'[INFO] Renew version of {filepath}')
            if renew_version == hashlib.sha1:
                m = hashlib.sha1()
                m.update(json.dumps(cells).encode())
                version = m.hexdigest()
            else:
                assert isinstance(renew_version, str)
                version = renew_version
        else:
            version = metadata['judge_submission']['exercises'][key]

        metadata = ipynb_metadata.submission_metadata({key: version}, False)
        ipynb_util.save_as_notebook(filepath, cells, metadata)
        logging.info(f'[INFO] Released {filepath}')
        forms[key] = (cells, version)

    return forms

def create_masters(submission_forms, target_dir=None, zip_archived=False, deadline=None):
    logging.info(f'[INFO] Creating master ipynb...')
    if target_dir is None:
        shutil.rmtree(MASTERS_DIR, ignore_errors=True)
        os.makedirs(MASTERS_DIR, exist_ok=True)
        target_dir = MASTERS_DIR
    for key, (cells, version) in submission_forms.items():
        metadata = ipynb_metadata.master_metadata(key, False, version, deadline)
        filepath = os.path.join(target_dir, key + '.ipynb')
        ipynb_util.save_as_notebook(filepath, cells, metadata)
        logging.info(f'[INFO] Released {filepath}')
    if zip_archived:
        with zipfile.ZipFile(target_dir + '.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
            logging.info(f'[INFO] Creating zip archive {zipf.filename} of released masters...')
            for filename in os.listdir(target_dir):
                zipf.write(os.path.join(target_dir, filename), filename)
        logging.info(f'[INFO] Released {target_dir}.zip')


if __name__ == '__main__':
    logging.getLogger().setLevel('INFO')
    main()
