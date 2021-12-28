#!/usr/bin/env python3

import ast, inspect
import unittest
import sys, io
import os
import re
import enum
import collections
import json


def _func_source(f):
    src_lines = inspect.getsource(f).splitlines()
    offset_indent = len(src_lines[0]) - len(src_lines[0].lstrip(' '))
    return '\n'.join(x[offset_indent:] for x in src_lines)


def is_ellipsis_body(f):
    node = next(n for n in ast.walk(ast.parse(_func_source(f))) if type(n) == ast.FunctionDef and n.name == f.__name__)
    def is_ellipsis(s):
        if type(s) == ast.Expr:
            b1 = type(s.value) == ast.Ellipsis # Python <= 3.7 (Deprecated in 3.8)
            b2 = type(s.value) == ast.Constant and s.value.value == ... # Python >= 3.8
            return b1 or b2
        else:
            return False
    return all(is_ellipsis(s) for s in node.body)


def find_loop(f):
    for n in  ast.walk(ast.parse(_func_source(f))):
        if type(n) == ast.For:
            return n
        if type(n) == ast.While:
            return n


def congruent(f, g):
    alias_map = {f.__name__: g.__name__, g.__name__: f.__name__}
    def eq(x, y):
        if type(x) != type(y):
            return False
        if type(x) == ast.Constant:
            return x.value == y.value
        if type(x) == ast.Name:
            return x.id == y.id or alias_map.get(x.id) == y.id
        return True
    return all(eq(n, m) or n == m for n, m in zip(*(ast.walk(ast.parse(_func_source(x))) for x in [f, g])))


class JudgeTestCaseBase(unittest.TestCase):
    ok_tags = []
    fail_tags = []
    unsuccessful_score = 0


def testcase(score=1):
    class JudgeTestCase(JudgeTestCaseBase):
        pass
    JudgeTestCaseBase.score = score
    assert JudgeTestCase.score >= JudgeTestCase.unsuccessful_score
    return JudgeTestCase


def _encode_method_name(name):
    assert isinstance(name, str) and len(name) > 0
    return f'test_{name}'

def _decode_method_name(method_name):
    _, name = method_name.split('_', 1)
    return name


def set_ok_tag(self, ok_tag):
    self.ok_tags = [ok_tag] if ok_tag else []

def set_fail_tag(self, fail_tag):
    self.fail_tags = [fail_tag] if fail_tag else []


def check_method(testcase_cls, fail_tag=None):
    assert issubclass(testcase_cls, JudgeTestCaseBase)
    def decorator(func):
        def wrapper_method(self):
            set_fail_tag(self, fail_tag)
            func(self)
        name = _encode_method_name(func.__name__)
        setattr(testcase_cls, name, wrapper_method)
        return func
    return decorator


def name_error_trap(testcase_cls, fail_tag=None):
    assert issubclass(testcase_cls, JudgeTestCaseBase)
    def decorator(func):
        name = _encode_method_name(func.__name__)
        def wrapper(self):
            set_fail_tag(self, fail_tag)
            try:
                func()
            except NameError:
                self.fail()
        setattr(testcase_cls, name, wrapper)
        return func
    return decorator


def test_method(testcase_cls):
    assert issubclass(testcase_cls, JudgeTestCaseBase)
    def decorator(func):
        def wrapper_method(self):
            set_ok_tag(self, 'CO')
            set_fail_tag(self, 'IO')
            func(self)
        name = _encode_method_name(func.__name__)
        setattr(testcase_cls, name, wrapper_method)
        return func
    return decorator


_argument_log = io.StringIO()

def argument_logger(f):
    def argrepr(x):
        if isinstance(x, io.TextIOBase):
            pos = x.tell()
            s = x.read()
            x.seek(pos)
            return f'File({repr(s)})'
        else:
            return repr(x)
    def cutoff(s, limit=256):
        return s[:limit] + '...' if len(s) >= limit else s
    def wrapper(*args, **kwargs):
        args_repr = [cutoff(argrepr(x)) for x in args]
        args_repr.extend(f'{k}={cutoff(argrepr(v))}' for k, v in kwargs.items())
        logfile = _argument_log if 'IPython' in sys.modules else sys.stderr
        print(f'Called: {f.__name__}({", ".join(args_repr)})', file=logfile)
        return f(*args, **kwargs)
    return wrapper

def read_argument_log():
    global _argument_log
    log = _argument_log.getvalue()
    _argument_log = io.StringIO()
    return log


class ResultStatus(enum.Enum):
    PASS = enum.auto()
    FAIL = enum.auto()
    ERROR = enum.auto()
    UNKNOWN = enum.auto()


class JudgeTestResult(unittest.TestResult):
    Record = collections.namedtuple('JudgeRecord', ('name', 'status', 'score', 'tags', 'err'))

    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.successes = set()
        self.run_tests = []

    def startTest(self, test):
        super().startTest(test)
        self.run_tests.append(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.add(test)

    def to_table(self):
        failures = {t: e for t, e in self.failures}
        errors = {t: e for t, e in self.errors}
        rows = []
        for t in self.run_tests:
            if t in self.successes:
                status = ResultStatus.PASS
                score = t.score
                tags = t.ok_tags
                err = ''
            elif t in failures:
                status = ResultStatus.FAIL
                score = t.unsuccessful_score
                tags = t.fail_tags
                err = failures[t]
            elif t in errors:
                status = ResultStatus.ERROR
                score = t.unsuccessful_score
                tags = []
                err = errors[t]
            else:
                status = ResultStatus.UNKNOWN
                score = t.unsuccessful_score
                tags = []
                err = ''
            name = _decode_method_name(t._testMethodName)
            rows.append(JudgeTestResult.Record(name, status, score, tags, err))
        return rows

    def to_json(self):
        rows = [x._asdict() for x in self.to_table()]
        for row in rows:
            row['status'] = row['status'].name.lower()
        return json.dumps(rows, indent=1, ensure_ascii=False)


class JudgeTestRunner(unittest.TextTestRunner):
    resultclass = JudgeTestResult


def unittest_main(debug=False):
    stream = io.StringIO()
    main = unittest.main(argv=[''], testRunner=JudgeTestRunner(stream, verbosity=2), exit=False)
    result_json = main.result.to_json()
    if debug:
        for row in json.loads(result_json):
            print(row['name'], row['status'], row['tags'], sep='\t', file=sys.stderr)
        for row in json.loads(result_json):
            if row['status'] != ResultStatus.PASS.name:
                print('='*70, f"{row['status']}: {row['name']}", '-'*70, row['err'], sep='\n', file=sys.stderr)
        print('----\n', read_argument_log(), sep='', file=sys.stderr)
    else:
        print(result_json)
