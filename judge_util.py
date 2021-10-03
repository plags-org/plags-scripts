#!/usr/bin/env python3

import ast, inspect
import unittest
import sys, io
import re


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
                prettyname, *_ = _decode_method_name(self._testMethodName)
                legalname = self._testMethodName
                self._testMethodName = prettyname
                ret = super().__str__()
                self._testMethodName = legalname
            else:
                ret = super().__str__()
            return ret
    JudgeTestCase.score = score
    return JudgeTestCase


def _encode_method_name(name, ok_score, fail_score, ok_tag, fail_tag):
    assert isinstance(name, str) and len(name) > 0
    assert all(isinstance(x, int) and x >= 0 for x in (ok_score, fail_score))
    assert all(isinstance(x, str) or x is None for x in (ok_tag, fail_tag))
    return f'test_{normalize_tag(ok_tag)}_{ok_score}_{normalize_tag(fail_tag)}_{fail_score}_{name}'

def normalize_tag(tag):
    if tag is None:
        return tag
    chars = r'[0-9A-Za-z]+'
    max_length = 16
    if re.fullmatch(chars, tag) is None:
        raise ValueError(repr(tag))
    if len(tag) <= max_length:
        return tag
    else:
        print(f'[Warning] Tag name {repr(tag)} is truncated to {repr(tag[:max_length])}.', file=sys.stderr)
        return tag[:max_length]

def _decode_method_name(method_name):
    _, ok_tag, ok_score, fail_tag, fail_score, name = method_name.split('_', 5)
    conv = lambda st: (int(st[0]), None if st[1] == 'None' else st[1])
    return (name, *map(conv, ((ok_score, ok_tag), (fail_score, fail_tag))))


def set_ok_tag(self, ok_tag):
    name, (ok_score, _), (fail_score, fail_tag) = _decode_method_name(self._testMethodName)
    self._testMethodName = _encode_method_name(name, ok_score, fail_score, ok_tag, fail_tag)

def set_fail_tag(self, fail_tag):
    name, (ok_score, ok_tag), (fail_score,  _) = _decode_method_name(self._testMethodName)
    self._testMethodName = _encode_method_name(name, ok_score, fail_score, ok_tag, fail_tag)


def check_method(testcase_cls, fail_tag=None):
    assert isinstance(testcase_cls.score,int) and testcase_cls.score > 0
    def decorator(func):
        name = _encode_method_name(func.__name__, testcase_cls.score, 0, None, fail_tag)
        setattr(testcase_cls, name, func)
        return func
    return decorator


def name_error_trap(testcase_cls, fail_tag=None):
    assert isinstance(testcase_cls.score,int) and testcase_cls.score > 0
    def decorator(func):
        name = _encode_method_name(func.__name__, testcase_cls.score, 0, None, fail_tag)
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
        name = _encode_method_name(func.__name__, testcase_cls.score, 0, 'CO', 'IO')
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


class TextTestResult(unittest.TestResult):
    """A test result class that can print formatted text results to a stream.
    Used by TextTestRunner.
    """
    separator1 = '=' * 70
    separator2 = '-' * 70

    def __init__(self, stream, descriptions, verbosity):
        super(TextTestResult, self).__init__(stream, descriptions, verbosity)
        self.stream = stream
        self.showAll = verbosity > 1
        self.dots = verbosity == 1
        self.descriptions = descriptions

    def getDescription(self, test):
        doc_first_line = test.shortDescription()
        if self.descriptions and doc_first_line:
            return '\n'.join((str(test), doc_first_line))
        else:
            return str(test)

    def startTest(self, test):
        super(TextTestResult, self).startTest(test)


    def addSuccess(self, test):
        super(TextTestResult, self).addSuccess(test)
        if self.showAll:
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ")
            self.stream.writeln("ok")
        elif self.dots:
            self.stream.write('.')
            self.stream.flush()

    def addError(self, test, err):
        super(TextTestResult, self).addError(test, err)
        if self.showAll:
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ")
            self.stream.writeln("ERROR")
        elif self.dots:
            self.stream.write('E')
            self.stream.flush()

    def addFailure(self, test, err):
        super(TextTestResult, self).addFailure(test, err)
        if self.showAll:
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ")
            self.stream.writeln("FAIL")
        elif self.dots:
            self.stream.write('F')
            self.stream.flush()

    def addSkip(self, test, reason):
        super(TextTestResult, self).addSkip(test, reason)
        if self.showAll:
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ")
            self.stream.writeln("skipped {0!r}".format(reason))
        elif self.dots:
            self.stream.write("s")
            self.stream.flush()

    def addExpectedFailure(self, test, err):
        super(TextTestResult, self).addExpectedFailure(test, err)
        if self.showAll:
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ")
            self.stream.writeln("expected failure")
        elif self.dots:
            self.stream.write("x")
            self.stream.flush()

    def addUnexpectedSuccess(self, test):
        super(TextTestResult, self).addUnexpectedSuccess(test)
        if self.showAll:
            self.stream.write(self.getDescription(test))
            self.stream.write(" ... ")
            self.stream.writeln("unexpected success")
        elif self.dots:
            self.stream.write("u")
            self.stream.flush()

    def printErrors(self):
        if self.dots or self.showAll:
            self.stream.writeln()
        self.printErrorList('ERROR', self.errors)
        self.printErrorList('FAIL', self.failures)

    def printErrorList(self, flavour, errors):
        for test, err in errors:
            self.stream.writeln(self.separator1)
            self.stream.writeln("%s: %s" % (flavour,self.getDescription(test)))
            self.stream.writeln(self.separator2)
            self.stream.writeln("%s" % err)


class TextTestRunner(unittest.TextTestRunner):
    resultclass = TextTestResult


def unittest_main(debug=False):
    if debug:
        global PRETTY_PRINT_METHOD_NAME
        PRETTY_PRINT_METHOD_NAME = True
        unittest.main(argv=[''], verbosity=2, exit=False)
        print('----\n', read_argument_log(), sep='', file=sys.stderr)
        PRETTY_PRINT_METHOD_NAME = False
    else:
        unittest.main(argv=[''], testRunner=TextTestRunner, verbosity=2, exit=False)
