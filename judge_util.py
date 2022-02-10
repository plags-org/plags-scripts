#!/usr/bin/env python3

import ast, inspect
import unittest
import sys, io
import os
import re
import enum
import collections
import json
import html
import typing
import dataclasses


SUBMISSION_FILENAME = 'submission.py'


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


@dataclasses.dataclass(frozen=True)
class EvaluationTag:
    name: str
    description: str
    background_color: str = '#333333'
    font_color: str = '#cccccc'
    visible: bool = True

    def __new__(cls, name, description, background_color='#333333', font_color='#cccccc', visible=True):
        name_pat = r'[0-9A-Za-z]{1,16}'
        text_pat = r'[^\a\b\f\n\r\v]+'
        color_pat = r'#[0-9A-Fa-f]{6}'
        if not isinstance(visible, bool) or \
           any(x is None for x in [re.fullmatch(name_pat, name),
                                   re.fullmatch(text_pat, description, re.ASCII),
                                   re.fullmatch(color_pat, background_color),
                                   re.fullmatch(color_pat, font_color)]):
           raise ValueError(name, description, background_color, font_color, visible)
        return super().__new__(cls)

    def to_html(self):
        style = f'border-radius: 16%; padding: 4px 8px; margin: 1px 2px 1px; font-weight: 600; background-color: {self.background_color}; color: {self.font_color};'
        return f'<span style="{style}">{self.name}</span>'


class EvaluationTagMapping(tuple, collections.abc.Mapping):
    def __init__(self, iterable):
        self.__map = {t.name: t for t in iterable}

    def __getitem__(self, k):
        return self.__map[k]

    def __contains__(self, k):
        return k in self.__map


PREDEFINED_TAGS = EvaluationTagMapping((
    # rawcheck
    EvaluationTag('SE', 'Syntax Error', '#ffbf3f', '#ffdfbf'),
    EvaluationTag('SCE', 'Shell Command (!command) Exists', '#ffbf3f', '#ffdfbf'),
    EvaluationTag('MCE', 'Magic Command (%command) Exists', '#ffbf3f', '#ffdfbf'),
    EvaluationTag('UMI', 'Unsupported Module Imported', '#ffbf3f', '#ffdfbf'),
    EvaluationTag('TE', 'Top-level Error', '#ffbf3f', '#ffdfbf'),
    EvaluationTag('IOT', 'I/O found at Top level', '#ffbf3f', '#ffdfbf'),
    EvaluationTag('QE', 'Question Exists', '#6f00ff', '#e5d1ff'),

    # judge_util.test_method
    EvaluationTag('CO', 'Correct Output',   '#7fbf7f', '#dfffdf'),
    EvaluationTag('IO', 'Incorrect Output', '#bf7f7f', '#ffdfdf'),

    # template_autograde
    EvaluationTag('ND', 'No Definition', '#333333', '#cccccc'),
    EvaluationTag('NF', 'Not Filled', '#333333', '#cccccc'),
    EvaluationTag('IM', 'Import Missing', '#ffbf3f', '#ffdfbf'),
))


class JudgeTestCaseBase(unittest.TestCase):
    ok_tags = []
    fail_tags = []

class JudgeTestStageBase(JudgeTestCaseBase):
    mode = 'append' # or 'separate'
    name: typing.Optional[str]
    required_files: list
    score: typing.Optional[int]
    unsuccessful_score: typing.Optional[int]

def teststage(name=None, *, score=1, unsuccessful_score=0, required_files=[]):
    class JudgeTestStage(JudgeTestStageBase):
        required_files = ['.judge/judge_util.py']
    JudgeTestStage.name = name
    JudgeTestStage.score = score
    JudgeTestStage.unsuccessful_score = unsuccessful_score
    JudgeTestStage.required_files.extend(required_files)
    return JudgeTestStage


def _encode_method_name(name):
    assert isinstance(name, str) and len(name) > 0
    return f'test_{name}'

def _decode_method_name(method_name):
    _, name = method_name.split('_', 1)
    return name


def set_ok_tag(self, ok_tag):
    if ok_tag is None:
        self.ok_tags = []
    elif isinstance(ok_tag, EvaluationTag):
        self.ok_tags = [ok_tag]
    elif ok_tag in PREDEFINED_TAGS:
        self.ok_tags = [PREDEFINED_TAGS[ok_tag]]
    else:
        raise ValueError(ok_tag)

def set_fail_tag(self, fail_tag):
    if fail_tag is None:
        self.fail_tags = []
    elif isinstance(fail_tag, EvaluationTag):
        self.fail_tags = [fail_tag]
    elif fail_tag in PREDEFINED_TAGS:
        self.fail_tags = [PREDEFINED_TAGS[fail_tag]]
    else:
        raise ValueError(fail_tag)


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


def argument_logger(testcase, func):
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
        set_unsuccessful_message(testcase, f'Something went wrong: {func.__name__}({", ".join(args_repr)})')
        return func(*args, **kwargs)

    return wrapper


_message_log = {}

def set_unsuccessful_message(testcase, msg):
    _message_log[testcase] = msg


class ResultStatus(enum.Enum):
    PASS = enum.auto()
    FAIL = enum.auto()
    ERROR = enum.auto()
    UNKNOWN = enum.auto()

    def style(self):
        common = 'border-radius: 16%; padding: 4px 8px; margin: 1px 2px 1px; font-weight: 600;'
        if self == self.PASS:
            return common + 'background-color: #3fbf3f; color: #bfffbf;'
        elif self in (self.FAIL, self.ERROR):
            return common + 'background-color: #bf3f3f; color: #ffdfdf;'
        else:
            return common + 'background-color: #333333; color: #cccccc;'

    def to_html(self):
        return f'<span style="{self.style()}">{self.name.lower()}</span>'


class JudgeTestResult(unittest.TestResult):
    Record = collections.namedtuple('JudgeRecord', ('name', 'status', 'tags', 'err', 'msg'))

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
        _message_log.pop(test, None)

    def to_table(self):
        failures = {t: e for t, e in self.failures}
        errors = {t: e for t, e in self.errors}
        rows = []
        for t in self.run_tests:
            if t in self.successes:
                status = ResultStatus.PASS
                tags = t.ok_tags
                err = ''
                msg = _message_log.get(t, '')
            elif t in failures:
                status = ResultStatus.FAIL
                tags = t.fail_tags
                err = failures[t]
                msg = _message_log.get(t, '')
            elif t in errors:
                status = ResultStatus.ERROR
                tags = []
                err = errors[t]
                msg = _message_log.get(t, '')
            else:
                status = ResultStatus.UNKNOWN
                tags = []
                err = ''
                msg = ''
            name = _decode_method_name(t._testMethodName)
            rows.append(JudgeTestResult.Record(name, status, tags, err, msg))
        return rows

    def to_json(self):
        rows = [x._asdict() for x in self.to_table()]
        for row in rows:
            row['status'] = row['status'].name.lower()
            row['tags'] = [dataclasses.asdict(t) for t in row['tags']]
        return json.dumps(rows, indent=1, ensure_ascii=False)


class JudgeTestRunner(unittest.TextTestRunner):
    resultclass = JudgeTestResult


def render_evaluation_html(rows):
    return '<h3>Evaluation</h3>\n' + render_summary_table(rows) + '\n' + render_details_html(rows)

def render_summary_table(records):
    thead = """
<thead>
  <tr>
    <th style="text-align: center;">Test case</th>
    <th style="text-align: center;">Result type</th>
    <th style="text-align: center;">Result tag</th>
  </tr>
</thead>
""".strip('\n')
    trs = '\n'.join(f"""
  <tr>
    <td style="text-align: left;">{name}</td>
    <td style="text-align: left;">{status.to_html()}</td>
    <td style="text-align: left;">{' '.join(t.to_html() for t in tags)}</td>
  </tr>
""".strip('\n') for name, status, tags, _, _ in records)
    tbody = f"""
<tbody>
{trs}
</tbody>
""".strip('\n')
    table = f"""
<table border="1">
{thead}
{tbody}
</table>
""".strip('\n')
    return table

def render_details_html(rows):
    def unsuccessful_detail_html(record):
        name, status, _, err, msg = record
        return f"""
<section style="padding-top: 8px;">
<h4>{status.to_html()} {name}</h6>
<h5>Message</h5>
<pre>
{html.escape(msg.strip())}
</pre>
<h5>Error message</h5>
<pre>
{html.escape(err.strip())}
</pre>
</section>
""".strip('\n')
    return '\n'.join(unsuccessful_detail_html(x) for x in rows if x.status != ResultStatus.PASS)


def unittest_main(*, on_ipynb='IPython' in sys.modules):
    global _message_log
    _message_log = {}
    stream = io.StringIO()
    main = unittest.main(argv=[''], testRunner=JudgeTestRunner(stream, verbosity=2), exit=False)
    if on_ipynb:
        import IPython.display
        return IPython.display.HTML(render_evaluation_html(main.result.to_table()))
    else:
        print(main.result.to_json())
