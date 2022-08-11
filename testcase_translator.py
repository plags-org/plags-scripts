#!/usr/bin/env python3

import argparse
import ast
import os
import sys
import types

import testcase_util


SRC_SPEC = """
# Specification of test-case source files

## Rules

* Source code in Python.
* Define a list of test cases as a global variable of the same name as a function to be tested.
* Global variables starting with `_` are not interpreted as test-case lists.
* Global variables bounded to modules and objects defined in `testcase_util` are not interpreted as test-case lists.
* A test case is a triple of an argument tuple used to test the function, an expected return value, and a comparison operator of `str`.
* Comparison operators in test cases are omittable; where omitted, `'=='` is considered to be specified.
* Arguments and return values in test cases are limited to values `x` such that `eval(repr(x)) == x` holds.

## Example

Given the following source file,

```
def _power(x,y):
    return x**y

power = [
    ((2,3), 2**3),
    ((1,4), _power(1,4)),
    ((1,4), [1**4], 'in'),
]
```

Generated is the test code corresponding to the following asserts:

```
assert power(2,3) == 8
assert power(1,4) == 1
assert power(1,4) in [1]
```

Note that the evaluation results of test-case expressions are to be embedded into the generated code.
""".strip()


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('src', nargs='?', help=f'A source file of test cases; stdin is used if not specified.')
    parser.add_argument('-ss', '--source-spec', action='store_true', help='Show the specification of source files and exit.')
    parser.add_argument('-sa', '--show_arguments', action='store_true', help='Show argument messages in unsuccessful tests.')
    parser.add_argument('-cf', '--check_if_filled', action='store_true', help='Check if filled definitions exist in answer cells.')
    commandline_args = parser.parse_args(args)

    if commandline_args.source_spec:
        return SRC_SPEC

    with sys.stdin if commandline_args.src is None else open(commandline_args.src, encoding='utf-8') as f:
        src = f.read()

    testcases = interpret_testcases(src)
    output = [HEADER_TEMPLATE]
    if commandline_args.check_if_filled:
        for target, cases  in testcases.items():
            if all(lhs_args is None for lhs_args, _, _ in cases):
                output.append(VAR_FILLED_CHECK_TEMPLATE.format(name=target))
            else:
                assert all(lhs_args is not None for lhs_args, _, _ in cases)
                output.append(FILLED_CHECK_TEMPLATE.format(name=target))
    output.extend(generate_methods(testcases, commandline_args.show_arguments))

    return '\n'.join(output)


def _main():
    print(main())


def interpret_testcases(source):
    env = {'__name__': '__main__'}
    path = sys.path[:]
    cwd = os.getcwd()
    exec(source, env)
    sys.path = path
    os.chdir(cwd)
    env = {name: val for name, val in env.items() if not name.startswith('_')
                                                 and not getattr(val, '__module__', '') == testcase_util.__name__
                                                 and not isinstance(val, types.ModuleType)}

    assert all(isinstance(cases, list) for cases in env.values())

    for cases in env.values():
        for i, case in enumerate(cases):
            if isinstance(case, tuple):
                if len(case) == 2:
                    cmp_op = '=='
                elif len(case) == 3:
                    cmp_op = case[2]
                else:
                    assert False
                if isinstance(cmp_op, str):
                    exp_ast = ast.parse(f'_ {cmp_op} _').body[0].value
                    assert isinstance(exp_ast, ast.Compare)
                    op, *_ = exp_ast.ops
                else:
                    assert cmp_op.__module__ == testcase_util.__name__
                    op = cmp_op
                cases[i] = (*case[:2], op)
            else:
                assert case.__qualname__ == '<lambda>'
                raise NotImplemented
    return env


HEADER_TEMPLATE = """
import judge_util

Stage = judge_util.teststage(exercise_style=judge_util.ExerciseStyle.AS_IS, exec_answer=True)
""".lstrip()


FILLED_CHECK_TEMPLATE = """
@judge_util.check_method(Stage, 'NF')
def {name}_filled(self):
    judge_util.set_error_tag(self, 'ND', AttributeError)
    self.assertFalse(judge_util.is_ellipsis_body(self.answer.{name}))
""".lstrip()

VAR_FILLED_CHECK_TEMPLATE = """
@judge_util.check_method(Stage, 'NF')
def {name}_filled(self):
    judge_util.set_error_tag(self, 'ND', AttributeError)
    self.assertNotEqual(self.answer.{name}, ...)
""".lstrip()


def generate_methods(testcases, show_arguments):
    method_map = {
        ast.Eq: 'assertEqual',
        ast.NotEq: 'assertNotEqual',
        ast.Is: 'assertIs',
        ast.IsNot: 'assertIsNot',
        (ast.Is,None): 'assertIsNone',
        (ast.IsNot,None): 'assertIsNotNone',
        ast.In: 'assertIn',
        ast.NotIn: 'assertNotIn',
        ast.Lt: 'assertLess',
        ast.LtE: 'assertLessEqual',
        ast.Gt: 'assertGreater',
        ast.GtE: 'assertGreaterEqual',
        testcase_util.approx: 'assertAlmostEqual',
    }

    output = []
    for name, cases in testcases.items():
        suffix_format = '_test{:0' + str(len(str(len(cases)))) + '}'
        for i, (lhs_args, rhs, op) in enumerate(cases):
            method_name = method_map[type(op)]
            if rhs is None:
                method_name = method_name.get((op,None), method_name)
            decorator_name = {
                testcase_util.printed: 'test_method',
                testcase_util.stdout: 'test_method',
                testcase_util.call_count: 'check_method',
                testcase_util.recursively_called: 'check_method',
            }.get(type(rhs), 'test_method')

            decls = [f'{name} = self.answer.{name}']

            if isinstance(rhs, (testcase_util.printed, testcase_util.stdout)):
                wrapper = {
                    testcase_util.printed: 'judge_util.print_return',
                    testcase_util.stdout: 'judge_util.stdout_return',
                }[type(rhs)]
                decls.append(f'{name} = {wrapper}({name})')
                rhs = rhs.output
            elif isinstance(rhs, testcase_util.call_count):
                decls.append(f'{name} = judge_util.call_count_return({name})')
                if isinstance(rhs, testcase_util.recursively_called):
                    assert isinstance(op, ast.Eq)
                    method_name = method_map[ast.Gt]
                    decls.append("judge_util.set_fail_tag(self, 'NR')")
                rhs = rhs.count

            if lhs_args is None:
                lhs = f'self.answer.{name}'
                if show_arguments:
                    msg = f'Variable `{name}` is bound to value: '
                    decls = [f"judge_util.set_unsuccessful_message(self, {msg!r} + repr({lhs}))"]
            else:
                if show_arguments:
                    decls.append(f'{name} = judge_util.argument_logger(self, {name})')
                lhs = f"{name}({', '.join(map(repr, lhs_args))})"

            option = ''
            if isinstance(op, testcase_util.approx):
                option = ''.join(f', {key}={val!r}' for key, val in vars(op).items())

            assertion = f'self.{method_name}({lhs}, {rhs!r}{option})'
            body = decls + [assertion]
            output.append(TEST_TEMPLATE.format(decorator_name, f'{name}{suffix_format.format(i)}', '\n    '.join(body)))

    return output


TEST_TEMPLATE = """
@judge_util.{}(Stage)
def {}(self):
    {}
""".lstrip()


if __name__ == '__main__':
    _main()
