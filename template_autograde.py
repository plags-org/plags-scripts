#!/usr/bin/env python3

import argparse
import ast
import os
import sys
import contextlib

import ipynb_metadata
import ipynb_util
from build_autograde import FieldKey

if (sys.version_info.major, sys.version_info.minor) < (3, 9):
    print('[ERROR] This script requires Python >= 3.9.')
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('DEST_IPYNB', help='Specify a destination ipynb file.')
    parser.add_argument('-d', '--description', help='Specify a Markdown file of problem description.')
    parser.add_argument('-p', '--prefill', help='Specify a Python module of the prefill code of answer code.')
    parser.add_argument('-a', '--answer', help='Specify a Python module of model answer code.')
    parser.add_argument('-i', '--instructive_assertion', help='Specify a Python module of instructive assertions.')
    parser.add_argument('-t', '--title', help='Specify title (default: ${exercise_key})')
    commandline_args = parser.parse_args()

    dest_path = commandline_args.DEST_IPYNB
    assert dest_path[-6:] == '.ipynb'
    exercise_key = os.path.basename(dest_path)[:-6]

    kwargs = {}
    for kw in ('description', 'prefill', 'answer', 'instructive_assertion'):
        kwargs[kw] = ''
        with contextlib.suppress(FileNotFoundError), open(getattr(commandline_args, kw, ''), encoding='utf-8') as f:
            kwargs[kw] = f.read().strip()
    kwargs['title'] = exercise_key if commandline_args.title is None else commandline_args.title

    cells = generate_template_body(**kwargs)

    version = ipynb_metadata.master_metadata_version({})
    metadata = ipynb_metadata.master_metadata(exercise_key, True, version, kwargs['title'])

    ipynb_util.save_as_notebook(dest_path, cells, metadata)


def generate_template_body(title, description, prefill, answer, instructive_assertion):
    cells = [field_heading_cell(FieldKey.WARNING)]
    cells.append(field_heading_cell(FieldKey.DESCRIPTION))
    cells.append(ipynb_util.markdown_cell(f'## {title}\n\n{description}').to_ipynb())
    cells.append(field_heading_cell(FieldKey.ANSWER_CELL_CONTENT))
    cells.append(ipynb_util.code_cell(prefill).to_ipynb())
    cells.append(field_heading_cell(FieldKey.EXAMPLE_ANSWERS))
    cells.append(ipynb_util.code_cell(answer).to_ipynb())
    cells.append(field_heading_cell(FieldKey.INSTRUCTIVE_TEST))
    cells.append(ipynb_util.code_cell(instructive_assertion).to_ipynb())
    cells.append(field_heading_cell(FieldKey.SYSTEM_TESTCODE))
    cells.append(generate_precheck_test_code(prefill, answer))
    cells.extend(generate_given_test_code(prefill, instructive_assertion))
    cells.append(generate_hidden_test_code(prefill))
    cells.append(field_heading_cell(FieldKey.PLAYGROUND))
    cells.append(ipynb_util.code_cell('judge_util.unittest_main()').to_ipynb())
    return cells


def field_heading_cell(field_key):
    return ipynb_util.markdown_cell(f'***CONTENT_TYPE: {field_key.name}***  \n'
                                    + FIELD_DESCRIPTIONS[field_key]).to_ipynb()

FIELD_DESCRIPTIONS = {
    FieldKey.WARNING: '`CONTENT_TYPE:`から始まるセルは，システム用なので書き換えないで下さい．',
    FieldKey.DESCRIPTION: '課題説明を書いてください．\n'
                          '`## 課題タイトル` から始まるMarkdownセルで始めてください．\n'
                          'その`課題タイトル`は，課題一覧に表示されます．\n'
                          '複数セル可，省略不可．',
    FieldKey.ANSWER_CELL_CONTENT: '解答セルにおける既定のコードを記述してください．\n'
                                  '複数セル不可，空白可．',
    FieldKey.EXAMPLE_ANSWERS: '解答例をコードセルに記述してください．\n'
                              '最初のセルは，模範解答であることが期待されます．\n'
                              'ここで記述されたコードは，自動評価には使われませんが，このipynb上でテストコードを実行したり，補助ipynbを生成する際に使われます．\n'
                              '複数セル可，省略可．',
    FieldKey.INSTRUCTIVE_TEST: '学生向けのテスト指示とテストコードを記述してください．\n'
                               '複数セル可，省略可．',
    FieldKey.SYSTEM_TESTCODE: '次の点に留意して自動評価に使われるテストコードを記述してください．\n'
                              '\n'
                              '* **1つのコードセルが1つの独立したモジュール**になります．\n'
                              '* 1つのモジュールが1つのstageとして扱われ，セルの出現順で実行されます．\n'
                              '* 各セルに `judge_util.teststage` が返すクラスを，**グローバルに1つ**定義してください．\n'
                              '\n'
                              '複数セル可，省略可．',
    FieldKey.PLAYGROUND: 'このセルより下は，課題のビルドに影響しない自由編集領域です．\n'
                         '\n'
                         '次のコードは，上で定義したテストコードを，このipynb上で実行するためのものです．\n'
                         '自動評価と同等の結果を得ます．',
}


def generate_precheck_test_code(prefill, answer):
    given_ast = ast.parse(prefill)
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
        templates.append(ast.unparse(funcdef).strip() + '\n')

    return code_cell(templates)

PRECHECK_HEADER_TEMPLATE = """
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


def code_cell(source_lines):
    return ipynb_util.code_cell('\n'.join(source_lines).strip()).to_ipynb()


def generate_given_test_code(prefill, instructive_assertion):
    given_ast = ast.parse(instructive_assertion)
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
            assert_methods.append(f'{method_map[ty]}({ast.unparse(test.left).strip()})')
        elif ty == ast.Not:
            assert_methods.append(f'{method_map[ty]}({ast.unparse(test.operand).strip()})')
        elif ty is None:
            assert_methods.append(f'{method_map[ty]}({ast.unparse(test).strip()})')
        else:
            assert_methods.append(f'{method_map[ty]}({ast.unparse(test.left).strip()}, {ast.unparse(test.comparators[0]).strip()})')

    imports = '\n'.join(ast.unparse(node).strip() for node in ast.walk(ast.parse(prefill)) if isinstance(node, (ast.Import, ast.ImportFrom)))

    templates = [GIVEN_TEST_HEADER_TEMPLATE.format(f'\n{imports}\n' if imports else '')]
    for i, m in enumerate(assert_methods):
        templates.append(GIVEN_TEST_TEMPLATE.format(f'g{i}', m))

    return [code_cell(templates)] if assert_methods else []

GIVEN_TEST_HEADER_TEMPLATE = """
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


def generate_hidden_test_code(prefill):
    imports = '\n'.join(ast.unparse(node).strip() for node in ast.walk(ast.parse(prefill)) if isinstance(node, (ast.Import, ast.ImportFrom)))
    return code_cell([HIDDEN_TEST_HEADER_TEMPLATE.format(f'\n{imports}\n' if imports else '')])

HIDDEN_TEST_HEADER_TEMPLATE = """
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
