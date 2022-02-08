#!/usr/bin/env python3

import json


judge_parameters = {
    'default': {
        'environment': ...,  # str
        'time_limit': ...,   # int (ms)
        'memory_limit': ..., # int (MiB)
    },
    'override': {
        # exercise_key: { 'environment': ..., 'time_limit': ..., 'memory_limit': ... }
    },
}


def load_judge_parameters(json_path):
    with open(json_path, encoding='utf-8') as f:
        judge_env = json.load(f)
    for k in judge_parameters['default']:
        judge_parameters['default'][k] = judge_env['default'][k]
    for ex_key, d in judge_env['override'].items():
        judge_parameters['override'][ex_key] = {k: d[k] for k in judge_parameters['default'] if k in d}


def generate_judge_setting(exercise_key, exercise_version, test_stages):
    params = {k: judge_parameters['override'].get(exercise_key, {}).get(k, v) for k, v in judge_parameters['default'].items()}
    env, time_limit, memory_limit = params['environment'], params['time_limit'], params['memory_limit']
    states = {
        stage.name: {
            'runner': {
                'name': 'test_runner_py37_unittest_v2.py',
                'version': '',
                'options': {'evaluation_style': 'append'}
            },
            'time_limit': time_limit,
            'require_files': stage.required_files,
            'result_aggregation': {'grade': 'min'},
            'transitions': [
                (('$forall', ('pass',)), test_stages[i+1].name if i + 1 < len(test_stages) else 'accept')
            ]
        } for i, stage in enumerate(test_stages)
    }
    return {
        'schema_version': 'v0.1',
        'metadata': {
            'name': exercise_key,
            'version': exercise_version
        },
        'judge': {
            'preprocess': {'rename': 'submission.py'},
            'environment': {'name': env, 'version': ''},
            'sandbox': {
                'name': 'Firejail',
                'options': {
                    'cpu_limit': 1,
                    'memory_limit': f'{memory_limit}MiB',
                    'network_limit': 'disable'
                }
            },
            'evaluation_dag': {
                'initial_state': test_stages[0].name,
                'states': states,
                'result_aggregation': {'grade': 'min'},
            }
        },
    }
