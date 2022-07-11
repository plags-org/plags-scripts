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
        style = f'border-radius: 16%; padding: 4px 8px; margin: 1px 2px; font-weight: 600; background-color: {self.background_color}; color: {self.font_color};'
        return f'<span style="{style}">{self.name}</span>'


class EvaluationTagMapping(tuple, collections.abc.Mapping):
    def __init__(self, iterable):
        self.__map = {t.name: t for t in iterable}

    def __getitem__(self, k):
        return self.__map[k]

    def __contains__(self, k):
        return k in self.__map

    def to_html(self):
        if len(self) == 0:
            return ''
        name_width = max(len(t.name) for t in self)
        dts = '\n'.join(f"""
<dt style="padding: 2px 8px; margin: 2px 2px; clear: left; width: {name_width}em;">{t.to_html()}</dt>
<dd style="padding: 2px 8px; margin: 2px 2px; float: left; width: {len(t.description)}em;">{t.description}</dd>
""".strip('\n') for t in sorted(self, key=lambda x: x.name))
        dl = f"""
<dl style="clear: left;">
{dts}
</dl>
""".strip('\n')
        return dl


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
))


class JudgeTestCaseBase(unittest.TestCase):
    ok_tags = []
    fail_tags = []
    error_tag_rules = {}

class JudgeTestStageBase(JudgeTestCaseBase):
    mode = 'append' # or 'separate'
    name: typing.Optional[str]
    required_files: list
    score: typing.Optional[int]
    unsuccessful_score: typing.Optional[int]

def teststage(name=None, *, score=1, unsuccessful_score=0, required_files=None):
    class JudgeTestStage(JudgeTestStageBase):
        pass
    JudgeTestStage.name = name
    JudgeTestStage.score = score
    JudgeTestStage.unsuccessful_score = unsuccessful_score
    JudgeTestStage.required_files = list(required_files) if required_files else []
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

def set_error_tag(self, error_tag, exception=Exception):
    if not issubclass(exception, Exception):
        raise ValueError(exception)
    if error_tag is None:
        self.error_tag_rules.pop(exception, None)
    elif isinstance(error_tag, EvaluationTag):
        self.error_tag_rules = {**self.error_tag_rules, exception: error_tag}
    elif error_tag in PREDEFINED_TAGS:
        self.error_tag_rules = {**self.error_tag_rules, exception: PREDEFINED_TAGS[error_tag]}
    else:
        raise ValueError(error_tag)


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
        common = 'border-radius: 16%; padding: 4px 8px; margin: 1px 2px; font-weight: 600;'
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
        self.exc_info = {}

    def startTest(self, test):
        super().startTest(test)
        self.run_tests.append(test)

    def addSuccess(self, test):
        super().addSuccess(test)
        self.successes.add(test)
        _message_log.pop(test, None)

    def addError(self, test, err):
        super().addError(test, err)
        self.exc_info[test] = err

    def to_table(self, stage_name=None):
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
                tags = [tag for e, tag in t.error_tag_rules.items() if issubclass(self.exc_info[t][0], e)]
                err = errors[t]
                msg = _message_log.get(t, '')
            else:
                status = ResultStatus.UNKNOWN
                tags = []
                err = ''
                msg = ''
            name = _decode_method_name(t._testMethodName)
            if stage_name is not None:
                name = f'{stage_name[type(t)]}.{name}'
            rows.append(JudgeTestResult.Record(name, status, tags, err, msg))
        return rows

    def to_json(self):
        rows = [x._asdict() for x in self.to_table()]
        for row in rows:
            row['status'] = row['status'].name.lower()
            row['tags'] = [dataclasses.asdict(t) for t in row['tags']]
        return rows


class JudgeTestRunner(unittest.TextTestRunner):
    resultclass = JudgeTestResult


def render_evaluation_html(rows):
    ts = set()
    for _, _, tags, _, _ in rows:
        ts.update(tags)
    tagmap = EvaluationTagMapping(ts)
    return f'<h3>Evaluation</h3><div style="float: left;">\n{render_summary_table(rows)}</div>\n<div style="clear: left;">{tagmap.to_html()}</div>\n{render_details_html(rows)}'

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
    <td style="text-align: left;"><code>{name}</code></td>
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
<table>
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
<h4>{status.to_html()} <code>{name}</code></h6>
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
        caller_globals = inspect.currentframe().f_back.f_globals
        stage_name = {v: n if v.name is None else v.name for n, v in caller_globals.items() if isinstance(v, type) and issubclass(v, JudgeTestStageBase)}
        import IPython.display
        return IPython.display.HTML(render_evaluation_html(main.result.to_table(stage_name)))
    else:
        print('', json.dumps(main.result.to_json(), ensure_ascii=False), sep='\n')
