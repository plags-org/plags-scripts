MATERIALS_METADATA = {
    'kernelspec': {
        'display_name': 'Python 3',
        'language': 'python',
        'name': 'python3',
    },
    'language_info': {
        'name': '',
    },
}

EXERCISE_METADATA = {'exercise_version': None,
                     **MATERIALS_METADATA}

def submission_metadata(id_to_version, extraction: bool):
    return {
        'judge_submission': {'exercises': id_to_version, 'extraction': extraction},
        **MATERIALS_METADATA,
    }
