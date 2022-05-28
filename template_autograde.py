#!/usr/bin/env python3

import argparse
import ast
import itertools
import logging
import os
import re
import sys

import astunparse

import ipynb_metadata
import ipynb_util
import build_autograde

if (sys.version_info.major, sys.version_info.minor) < (3, 8):
    print('[ERROR] This script requires Python >= 3.8.')
    sys.exit(1)


def main():
    logging.getLogger().setLevel('INFO')
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--source', nargs='*', required=True, help=f'Specify source(s) (ipynb files in separate mode and directories in bundle mode)')
    commandline_options = parser.parse_args()

    separates, bundles = build_autograde.load_sources(commandline_options.source)
    exercises = list(itertools.chain(*bundles.values(), separates))
    for ex in exercises:
        generate_template(ex)


def generate_template(exercise):
    FieldKey = build_autograde.FieldKey
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'

    cells, metadata = ipynb_util.load_cells(os.path.join(exercise.dirpath, exercise.key + '.ipynb'))
    gen_cells = []
    for i, c in enumerate(cells):
        if c['cell_type'] == 'markdown':
            matches = list(re.finditer(CONTENT_TYPE_REGEX, ''.join(c['source'])))
            gen_cells.append(c)
            if not matches:
                continue
            key = getattr(FieldKey, matches[0][1])
            if key == FieldKey.SYSTEM_TESTCODE:
                gen_cells.append(generate_precheck_test_code(exercise))
                given_test = generate_given_test_code(exercise)
                gen_cells.extend(given_test)
                gen_cells.append(generate_hidden_test_code(exercise))
            if key == FieldKey.PLAYGROUND:
                gen_cells.append(ipynb_util.code_cell('judge_util.unittest_main()').to_ipynb())
        else:
            gen_cells.append(c)

    filepath = os.path.join(exercise.dirpath, f'template_{exercise.key}.ipynb')
    ipynb_util.save_as_notebook(filepath, gen_cells, metadata)


def generate_precheck_test_code(exercise):
    given_ast = ast.parse(exercise.answer_cell_content.source)
    ellipsis_vars = []
    for node in ast.walk(given_ast):
        if isinstance(node, ast.Assign) and \
           len(node.targets) == 1 and \
           isinstance(node.targets[0], ast.Name) and \
           isinstance(node.value, ast.Constant) and \
           node.value.value == ...:
           ellipsis_vars.append(node.targets[0].id)
    ellipsis_funcs = []
    context_funcs = []
    for node in ast.walk(given_ast):
        if isinstance(node, ast.FunctionDef):
            if all(isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant) and x.value.value == ... for x in node.body):
                ellipsis_funcs.append(node.name)
            elif any(isinstance(x, ast.Constant) and x.value == ... for x in ast.walk(node)):
                context_funcs.append(node)

    templates = [PRECHECK_HEADER_TEMPLATE]
    templates.extend(PRECHECK_ELLIPSIS_VAR_CHECK_TEMPLATE.format(x,x) for x in ellipsis_vars)
    templates.extend(PRECHECK_ELLIPSIS_FUNC_CHECK_TEMPLATE.format(x,x) for x in ellipsis_funcs)
    templates.extend(PRECHECK_CONGRUENT_FUNC_CHECK_TEMPLATE.format(x.name,x.name,x.name) for x in context_funcs)
    for funcdef in context_funcs:
        funcdef.originalname = funcdef.name
        funcdef.name = '_predefined_' + funcdef.name
        templates.append(astunparse.unparse(funcdef).strip() + '\n')

    if exercise.example_answers:
        predefined_mods = set()
        for node in ast.walk(given_ast):
            if isinstance(node, ast.Import):
                predefined_mods.update(x.name for x in node.names)
            if isinstance(node, ast.ImportFrom):
                predefined_mods.update([node.module] if node.module else [x.name for x in node.names])
        required_mods = set()
        for node in ast.walk(ast.parse(exercise.example_answers[0].source)):
            if isinstance(node, ast.Import):
                required_mods.update(x.name for x in node.names if x.name not in predefined_mods)
            if isinstance(node, ast.ImportFrom):
                required_mods.update(({node.module} if node.module else {x.name for x in node.names}) - predefined_mods)
        templates.extend(PRECHECK_IMPORT_CHECK_TEMPLATE.format(x.replace('.', '_'),x) for x in required_mods)

    return code_cell(templates)

PRECHECK_HEADER_TEMPLATE = """
import sys
sys.path.append('.judge')
import judge_util # モジュール全体をそのままの名前でimport

# この名前は任意
Precheck = judge_util.teststage()
""".lstrip()

PRECHECK_ELLIPSIS_VAR_CHECK_TEMPLATE = """
# 検査対象を実行しない静的検査
@judge_util.check_method(Precheck, 'NF') # 失敗（≠エラー）時に付くタグ（オプショナル）
def {}_filled(self):
    judge_util.set_error_tag(self, 'ND', NameError) # NameErrorが生じたらNDタグをつける
    self.assertNotEqual({}, ...) # ...と等しいなら失敗
""".lstrip()

PRECHECK_ELLIPSIS_FUNC_CHECK_TEMPLATE = """
# 検査対象を実行しない静的検査
@judge_util.check_method(Precheck, 'NF') # 失敗（≠エラー）時に付くタグ（オプショナル）
def {}_filled(self):
    judge_util.set_error_tag(self, 'ND', NameError) # NameErrorが生じたらNDタグをつける
    self.assertFalse(judge_util.is_ellipsis_body({})) # ...のみをbodyに持つなら失敗
""".lstrip()

PRECHECK_CONGRUENT_FUNC_CHECK_TEMPLATE = """
# 検査対象を実行しない静的検査
@judge_util.check_method(Precheck, 'NF') # 失敗（≠エラー）時に付くタグ（オプショナル）
def {}_filled(self):
    judge_util.set_error_tag(self, 'ND', NameError) # NameErrorが生じたらNDタグをつける
    self.assertFalse(judge_util.congruent({}, _predefined_{})) # 既定のコードとASTレベルで合同なら失敗
""".lstrip()

PRECHECK_IMPORT_CHECK_TEMPLATE = """
# 検査対象を実行しない静的検査
@judge_util.check_method(Precheck, 'IM') # 失敗時に付くタグ（オプショナル）
def {}_imported(self):                   # 成功・エラーの時にはタグは付かない
    import sys
    self.assertIn('{}', sys.modules) # importされていなかったら失敗
""".lstrip()


def code_cell(source_lines):
    return ipynb_util.code_cell('\n'.join(source_lines).strip()).to_ipynb()


def generate_given_test_code(exercise):
    given_ast = ast.parse('\n'.join(c.source for c in exercise.instructive_test if c.cell_type == ipynb_util.CellType.CODE))
    typed_asserts = []
    for node in ast.walk(given_ast):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Compare) and len(node.test.comparators) == 1:
                if isinstance(node.test.ops[0], (ast.Is, ast.IsNot)) and node.test.comparators[0].value is None:
                    typed_asserts.append(((type(node.test.ops[0]), None), node.test))
                else:
                    typed_asserts.append((type(node.test.ops[0]), node.test))
            elif isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
                typed_asserts.append((type(node.test.op), node.test))
            else:
                typed_asserts.append((None, node.test))

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
        ast.Not: 'assertFalse',
        None: 'assertTrue',
    }

    assert_methods = []
    for ty, test in typed_asserts:
        if ty in ((ast.Is,None),(ast.IsNot,None)):
            assert_methods.append(f'{method_map[ty]}({astunparse.unparse(test.left).strip()})')
        elif ty == ast.Not:
            assert_methods.append(f'{method_map[ty]}({astunparse.unparse(test.operand).strip()})')
        elif ty is None:
            assert_methods.append(f'{method_map[ty]}({astunparse.unparse(test).strip()})')
        else:
            assert_methods.append(f'{method_map[ty]}({astunparse.unparse(test.left).strip()}, {astunparse.unparse(test.comparators[0]).strip()})')

    imports = '\n'.join(astunparse.unparse(node).strip() for node in ast.walk(ast.parse(exercise.answer_cell_content.source)) if isinstance(node, (ast.Import, ast.ImportFrom)))

    templates = [GIVEN_TEST_HEADER_TEMPLATE.format(f'\n{imports}\n' if imports else '')]
    for i, m in enumerate(assert_methods):
        templates.append(GIVEN_TEST_TEMPLATE.format(f'g{i}', m))

    return [code_cell(templates)] if assert_methods else []

GIVEN_TEST_HEADER_TEMPLATE = """
import sys
sys.path.append('.judge')
import judge_util # モジュール全体をそのままの名前でimport
{}
Given = judge_util.teststage()
""".lstrip()

GIVEN_TEST_TEMPLATE = """
# 検査対象を実行して出力を比較するテスト
@judge_util.test_method(Given) # 成功時にCOタグ，失敗時にIOタグを付与
def {}(self):
    self.{}
""".lstrip()


def generate_hidden_test_code(exercise):
    imports = '\n'.join(astunparse.unparse(node).strip() for node in ast.walk(ast.parse(exercise.answer_cell_content.source)) if isinstance(node, (ast.Import, ast.ImportFrom)))
    return code_cell([HIDDEN_TEST_HEADER_TEMPLATE.format(f'\n{imports}\n' if imports else '')])

HIDDEN_TEST_HEADER_TEMPLATE = """
import sys
sys.path.append('.judge')
import judge_util # モジュール全体をそのままの名前でimport
{}
Hidden = judge_util.teststage()

# 検査対象を実行して出力を比較するテスト
@judge_util.test_method(Hidden) # 成功時にCOタグ，失敗時にIOタグを付与
def h0(self):
    ...
""".lstrip()


if __name__ == '__main__':
    main()
