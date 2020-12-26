#!/usr/bin/env python3

generate = None

def generate_system_test_setting(testlist):
    def setting_generator(env, time_limit, memory_limit, exercise_key, exercise_version, initial_source):
        states = {
            name: {
                'runner': {
                    'name': 'test_runner_py37_unittest.py',
                    'version': '',
                    'options': {'evaluation_style': 'append'}
                },
                'time_limit': time_limit,
                'require_files': require_files,
                'result_aggregation': {'grade': 'min'},
                'transitions': [
                    (('$forall', ('CO', 'CS')), testlist[i+1][0] if i + 1 < len(testlist) else 'accept')
                ]
            } for i, (name, require_files) in enumerate(testlist)
        }
        return {
            'schema_version': 'v0.0',
            'metadata': {
                'name': exercise_key,
                'version': exercise_version
            },
            'front': {
                'initial_source': initial_source,
                'editor': {
                    'name': 'CodeMirror',
                    'options': {'mode': {'name': 'python', 'singleLineStringErrors': True}}
                },
                'rejection': {'reject_initial_source': True},
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
                    'initial_state': testlist[0][0],
                    'states': states,
                    'result_aggregation': {'grade': 'min'},
                }
            },
        }

    global generate
    generate = setting_generator
    return generate('ENVIRONMENT', 2, 256, 'EXERCISE_KEY', 'EXERCISE_VERSION', '') # Dummy arguments


def required_files(setting):
    fs = set()
    for x in setting['judge']['evaluation_dag']['states'].values():
        fs.update(x['require_files'])
    return fs
