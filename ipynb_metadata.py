COMMON_METADATA = {
    'kernelspec': {
        'display_name': 'Python 3',
        'language': 'python',
        'name': 'python3',
    },
    'language_info': {
        'name': 'python',
    },
}

METADATA_BASE_KEY = 'plags'

def submission_metadata(name_to_version, extraction: bool):
    return {
        METADATA_BASE_KEY: {
            'type': 'submission',
            'exercises': name_to_version,
            'extraction': extraction,
        },
        **COMMON_METADATA,
    }

def master_metadata(name: str, autograde: bool, version: str, title=None, deadlines=None, drive=None, *, confidentiality=None, shared_after_confirmed=None):
    if title is None:
        title = name
    if deadlines is None:
        deadlines = {}
    deadlines = {k: deadlines.get(k) for k in ('begin', 'open', 'check', 'close', 'end')}
    if confidentiality is None:
        confidentiality = {}
    confidentiality = {k: a for k in ('score', 'remarks') if (a := confidentiality.get(k)) in ('student', 'assistant', 'lecturer', None)}
    return {
        METADATA_BASE_KEY: {
            'type': 'master',
            'evaluation': autograde,
            'confidentiality': confidentiality,
            'deadlines': deadlines,
            'drive': drive,
            'name': name,
            'shared_after_confirmed': shared_after_confirmed,
            'title': title,
            'version': version,
        },
        **COMMON_METADATA,
    }

def master_metadata_version(metadata=None, *, filepath=None):
    import ipynb_util
    assert metadata is None or filepath is None
    if metadata is None:
        metadata = {}
    if filepath is not None:
        _, metadata = ipynb_util.load_cells(filepath)
    return metadata.get(METADATA_BASE_KEY, {}).get('version', '')

def master_metadata_deadlines(metadata):
    deadlines = metadata.get(METADATA_BASE_KEY, {}).get('deadlines', {})
    return {k: deadlines.get(k) for k in ('begin', 'open', 'check', 'close', 'end')}

def master_metadata_drive(metadata):
    return metadata.get(METADATA_BASE_KEY, {}).get('drive')

def extend_master_metadata_for_trial(metadata, initial_source):
    metadata[METADATA_BASE_KEY]['trial'] = {
        'initial_source': initial_source,
        'editor': {
            'name': 'CodeMirror',
            'options': {
                'indentUnit': 4,
                'lineNumbers': True,
                'matchBrackets': True,
                'mode': {
                    'name': 'python',
                    'singleLineStringErrors': True,
                }
            }
        }
    }
