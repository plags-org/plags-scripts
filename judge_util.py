#!/usr/bin/env python3

import ast, inspect
import unittest
import sys, io


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


PRETTY_PRINT_METHOD_NAME = False

def testcase(score=1):
    class JudgeTestCase(unittest.TestCase):
        def __str__(self):
            if PRETTY_PRINT_METHOD_NAME:
                prettyname = self._testMethodName.split('_', 5)[-1]
                legalname = self._testMethodName
                self._testMethodName = prettyname
                ret = super().__str__()
                self._testMethodName = legalname
            else:
                ret = super().__str__()
            return ret
    JudgeTestCase.score = score
    return JudgeTestCase


def _test_method_name(name, ok_score, fail_score, ok_tag=None, fail_tag=None):
    return f'test_{ok_tag}_{ok_score}_{fail_tag}_{fail_score}_{name}'


def check_method(testcase_cls, fail_tag=None):
    assert isinstance(testcase_cls.score,int) and testcase_cls.score > 0
    def decorator(func):
        name = _test_method_name(func.__name__, testcase_cls.score, 0, None, fail_tag)
        setattr(testcase_cls, name, func)
        return func
    return decorator


def name_error_trap(testcase_cls, fail_tag=None):
    assert isinstance(testcase_cls.score,int) and testcase_cls.score > 0
    def decorator(func):
        name = _test_method_name(func.__name__, testcase_cls.score, 0, None, fail_tag)
        def wrapper(self):
            try:
                func()
            except NameError:
                self.fail()
        setattr(testcase_cls, name, wrapper)
        return func
    return decorator


def test_method(testcase_cls):
    assert isinstance(testcase_cls.score,int) and testcase_cls.score > 0
    def decorator(func):
        name = _test_method_name(func.__name__, testcase_cls.score, 0, 'CO', 'IO')
        setattr(testcase_cls, name, func)
        return func
    return decorator


def tagging_method(testcase_cls, ok_tag):
    assert isinstance(testcase_cls.score,int) and testcase_cls.score > 0
    def decorator(func):
        name = _test_method_name(func.__name__, testcase_cls.score, testcase_cls.score, ok_tag, None)
        setattr(testcase_cls, name, func)
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


def unittest_main(debug=False):
    if debug:
        global PRETTY_PRINT_METHOD_NAME
        PRETTY_PRINT_METHOD_NAME = True
        unittest.main(argv=[''], verbosity=2, exit=False)
        print('----\n', read_argument_log(), sep='', file=sys.stderr)
        PRETTY_PRINT_METHOD_NAME = False
    else:
        unittest.main(argv=[''], verbosity=2, exit=False)
