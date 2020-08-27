#!/usr/bin/env python3

output = None

def generate_system_test_setting(testlist, time_limit=2, memory_limit=256):
    states = {
        name: {
            'runner': {
                'name': 'test_runner_py37_unittest.py',
                'version': '',
                'options': {'evaluation_style': 'append'}
            },
            'time_limit': time_limit,
            'require_files': require_files,
            'accumulation_rule': {'grade': 'min'},
            'transitions': [
                {'if': {'only': ['CO', 'CS']}, 'then': testlist[i+1][0]},
                {'else': 'end'}
            ] if i + 1 < len(testlist) else [{'always': 'end'}]
        } for i, (name, require_files) in enumerate(testlist)
    }
    setting = {
        'front': {
            'editor': {
                'name': 'CodeMirror',
                'options': {'mode': {'name': 'python', 'singleLineStringErrors': True}}
            },
            'rejection': {'reject_initial_source': True}
        },
        'judge': {
            'preprocess': {'rename': 'submission.py'},
            'environment': {'name': 'python__anaconda3-2020.02', 'version': ''},
            'sandbox': {
                'name': 'Firejail',
                'options': {
                    'cpu_limit': 1,
                    'memory_limit': f'{memory_limit}MiB',
                    'network_limit': 'disable'
                }
            },
            'evaluation_dag': {
                'initial_state': testlist[0][0],
                'states': states,
                'accumulation_rule': {'grade': 'min'}
            }
        },
    }
    global output
    output = setting
    return setting