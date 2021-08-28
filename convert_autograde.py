#!/usr/bin/env python3

import argparse
import os
import re
import sys

import ipynb_util


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--source', nargs='*', required=True, help=f'Specify source(s) (ipynb files in separate mode and directories in bundle mode)')
    commandline_options = parser.parse_args()

    paths = []
    for path in sorted(commandline_options.source):
        if os.path.isdir(path):
            dirpath = path
            dirname = os.path.basename(dirpath)
            for nb in sorted(os.listdir(dirpath)):
                if re.fullmatch(fr'({dirname}[-_].*)\.ipynb', nb):
                    paths.append(os.path.join(dirpath, nb))
        else:
            if path.endswith('.ipynb'):
                paths.append(path)

    for path in paths:
        print('Convert:', path)
        correct_typos_master(path)


def correct_typos_master(filepath):
    CONTENT_TYPE_REGEX = r'\*\*\*CONTENT_TYPE:\s*(.+?)\*\*\*'

    cells, metadata = ipynb_util.load_cells(filepath)
    for c in cells:
        if c['cell_type'] == 'markdown':
            matches = list(re.finditer(CONTENT_TYPE_REGEX, ''.join(c['source'])))
            if not matches:
                continue
            key = matches[0][1]
            if key in REWRITE_RULES:
                c['source']= REWRITE_RULES[key].splitlines(True)

    new_cells = []
    deleting = False
    for c in cells:
        if c['cell_type'] == 'markdown':
            matches = list(re.finditer(CONTENT_TYPE_REGEX, ''.join(c['source'])))
            if matches:
                deleting = False
                if matches[0][1] in DELETED_FIELDS:
                    deleting = True
        if not deleting:
            new_cells.append(c)

    ipynb_util.save_as_notebook(filepath, new_cells, metadata)


DELETED_FIELDS = {
    'SYSTEM_TEST_SETTING',
}

REWRITE_RULES = {
    'CONTENT': """
***CONTENT_TYPE: DESCRIPTION***  
課題説明を書いてください．
`## 課題タイトル` から始まるMarkdownセルで始めてください．
その`課題タイトル`は，課題一覧に表示されます．
複数セル可，省略不可．
""".strip(),
    'STUDENT_CODE_CELL': """
***CONTENT_TYPE: ANSWER_CELL_CONTENT***  
解答セルにおける既定のコードを記述してください．
複数セル不可，空白可．
""".strip(),
    'EXPLANATION': """
***CONTENT_TYPE: COMMENTARY***  
解説を記述してください．
`## ...` から始まるMarkdownセルで始めてください．
これは，解説用ipynbのためにあります．
複数セル可，省略可．
""".strip(),
    'ANSWER_EXAMPLES': """
***CONTENT_TYPE: EXAMPLE_ANSWERS***  
解答例をコードセルに記述してください．
最初のセルは，模範解答であることが期待されます．
ここで記述されたコードは，自動評価には使われませんが，このipynb上でテストコードを実行したり，補助ipynbを生成する際に使われます．
複数セル可，省略可．
""".strip(),
    'STUDENT_TESTS': """
***CONTENT_TYPE: INSTRUCTIVE_TEST***  
学生向けのテスト指示とテストコードを記述してください．
複数セル可，省略可．
""".strip(),
    'SYSTEM_TEST_CASES': """
***CONTENT_TYPE: SYSTEM_TESTCODE***  
次の点に留意して自動評価に使われるテストコードを記述してください．

* **1つのコードセルが1つの独立したモジュール**になります．
* 各セルの先頭行には，**一意なモジュール名**をコメントで指定してください．
* 2行目以降は，**利用する外部ファイルの相対パス**を行毎にコメントで指定してください．指定されるファイルは，このipynbのディレクトリ以下に存在する必要があります．
* それらのヘッダコメントが終わった後から，プログラムコードとして解釈されます．
* 1つのモジュールが1つのstageとして扱われ，セルの出現順で実行されます．

複数セル可，省略可．
""".strip(),
    'SYSTEM_TEST_CASES_EXECUTE_CELL': """
***CONTENT_TYPE: PLAYGROUND***  
このセルより下は，課題のビルドに影響しない自由編集領域です．

次のコードは，上で定義したテストコードを，このipynb上で実行するためのものです．
自動評価と同等の結果を得ます．
""".strip(),
}


if __name__ == '__main__':
    main()
