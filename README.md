# PLAGS Scripts for Exercises

[PLAGS UT](https://plags.eidos.ic.i.u-tokyo.ac.jp/)に課題をアップロードするためのスクリプト群と簡単な課題例．

## 用語

以下では，「課題」の形態に合わせて，用語を使い分ける．

* 課題作成者が作成するもの: master
* 受講生に配布するもの: form

masterには，次の2つのスタイルがある．

* formatted: 所定の形式のipynbのセルに課題を記入
* as-is: 任意のipynbをそのまま問題文として利用

手軽に使うならas-is，課題とテストコードの設計をまとめて行いたい場合にはformattedが適している．formattedとas-isは，課題の定義方法だけでなく，ビルド方法や自動評価用のテストコードの書き方も異なる．

### メタデータ

以下では，[ipynb形式におけるmetadata](https://nbformat.readthedocs.io/en/latest/format_description.html#metadata)を単に*メタデータ*と呼ぶ．

メタデータは，ipynb内に記述されたプログラムの挙動に影響を与えず，JupyterやColabなどのノートブック環境の通常の利用において，誤って改変されるものではない．単に，システムに対するインタフェースとして機能する．したがって，メタデータを直接編集することは想定されておらず，本レポジトリが提供するスクリプトを使って設定・更新することが想定されている．

### exercise_key

exercise_keyとは，システム上の課題のIDであり，ブラウザ上での課題の整列順も規定する文字列である．後述するビルドスクリプトでは，masterの拡張子を除いたファイル名がexercise_keyとして利用される．

exercise_keyは正規表現 `[a-zA-Z0-9_-]{1,64}` にマッチする文字列でなければならない．したがって，ビルドスクリプトに与えるmasterのファイル名は， `[a-zA-Z0-9_-]{1,64}\.ipynb` に限定される．

exercise_keyは，master用メタデータとform用メタデータの両方に埋め込まれる．masterが持つexercise_keyに基づいて，アップロード時に更新される課題が特定される．提出されたformが持つexercise_keyに基づいて，当該提出物の課題が特定される．

exercise_keyの実体はipynbのメタデータにあるので，一旦メタデータが設定されたformは自由にリネームして配布できる．

以下では，適当なexercise_keyを参照する変数として `${exercise_key}` を利用する．

## 各種ファイルとディレクトリ

主要スクリプト：

* `build_formatted.py`: formattedのビルドスクリプト（Python 3.8以上）
* `template_formatted.py`: formatted用のテンプレート生成器（Python 3.9以上）
* `build_as_is.py`: as-isのビルドスクリプト（Python 3.8以上）
* `Makefile`: 自動評価付きのas-isを簡単にビルド＆テストするためのMakefile（要 [`ipykernel`](https://pypi.org/project/ipykernel/)）
* `judge_util.py`: 自動評価用のテストコードの記述に使うライブラリモジュール（Python 3.8以上）

課題例：

* `exercises/formatted/ex1/`: formattedの具体例
* `exercises/formatted/template/`: `template_formatted.py` への入力例
* `exercises/as-is/`: as-isの具体例

## ビルドスクリプトの単純な使い方

### formattedのビルド

#### single formの生成

`build_formatted.py` にformatted masterへのパスを渡すと課題をビルドできる．

```sh
python3 build_formatted.py exercises/formatted/ex1/ex1-1.ipynb 
```
* `exercises/formatted/ex1/ex1-1.ipynb` から出力部分を除去し，master用メタデータを設定
* `ex1-1.ipynb` に対応するform `exercises/formatted/ex1/form_ex1-1.ipynb` を生成

`build_formatted.py` は複数のmasterを引数に取れるので，次のように指定すると，

```sh
python3 build_formatted.py exercises/formatted/ex1/ex1-*.ipynb 
```

指定されたmaster毎の*single* formが生成される．

尚，`build_formatted.py` は `judge_util.py` を，指定されたmasterと同ディレクトリに自動的に設置するが，ビルドとは直接関係しない．当該masterをJupyterで開いた時に，`judge_util` モジュールをインポートできるようするための措置である．

#### bundled formの生成

`build_formatted.py` にディレクトリパスを渡すと，その中にあるmasterをまとめてビルドする．

```sh
python3 build_formatted.py exercises/formatted/ex1
```

* `exercises/formatted/ex1/ex1-{1,2}.ipynb` から出力部分を除去し，master用メタデータを設定
* `exercises/formatted/ex1/form_ex1.ipynb` を生成

この `form_ex1.ipynb` は，`ex1-{1,2}.ipynb` を束ねた*bundled* formである．

bundled formを1つ提出することで，その中に含まれる課題を全て提出したことになる．

bundled formの導入部分として，指定されたディレクトリ中に `intro.ipynb` があれば使われ，無ければディレクトリ名だけの見出し（`# ex1`）が自動で付与される．

`build_formatted.py` の引数には，masterとディレクトリを，同時に指定することができ，まとめてビルドできる．ただし，ビルド対象一式の中で，exercise_keyの重複は許可されない．したがって，前述の具体例において， `ex1-1.ipynb` と `ex1` の両方を同時に指定すると，エラーになる．

#### アップロード用設定ファイルの生成

アップロード用設定ファイル `conf.zip` を生成するには，アップロード対象のmaster全てを対象に指定して，`-c` オプションで実行する．

```sh
python3 build_formatted.py -c judge_env.json exercises/formatted/ex1
```

`-c` の引数 `judge_env.json` は，サーバ側の自動評価環境のパラメタをまとめたJSONファイルであり，PLAGS UTの管理者によって，運用レベルで指定されるものである．本レポジトリ中の `judge_env.json` は，1つの具体例に過ぎない．

尚，`conf.zip` を作成する際に，副産物として `conf/` を作るが，ビルド用ディレクトリなので消して問題ない．

### as-isのビルド

as-isにおいて，自動評価はオプショナルである．自動評価用のテストコードは，ビルドオプションの形で指定される．

#### formの生成

as-isでは，常に1つのmasterに対して1つのformが生成される．

```sh
python3 build_as_is.py -ac -qc exercises/as-is/ex2.ipynb
```

* `exercises/as-is/ex2.ipynb` にmaster用メタデータを設定
* `ex2.ipynb` に対応するform `exercises/as-is/form_ex2.ipynb` を生成
* `-ac` オプションにより，formに解答セルを追加
* `-qc` オプションにより，formに質問セルを追加

`-ac` オプションを与えるとき，解答セルを事前に埋める（prefill）コードを設定できる．上の例の場合，`exercises/as-is/ex2.py` がprefillコードと解釈される．

自動評価を有効にする場合は，`-ag` オプションを追加する．これによって，master用メタデータは変化するが，生成されるformは変化しない．

```sh
python3 build_as_is.py -ag -ac -qc exercises/as-is/ex2.ipynb
```

このとき，`exercises/as-is/test_ex2.py` が，課題固有のテストコードとして解釈される．

#### アップロード用設定ファイルの生成

自動評価を有効にしない場合，引数なしで `-c` オプションを付与すれば，アップロード可能な `conf.zip` を生成できる．

```sh
python3 build_as_is.py -c -ac -qc exercises/as-is/ex2.ipynb
```

自動評価を有効にする場合，`build_formatted.py` と同様に， `judge_env.json` の引数付きで `-c` オプションを与える．

```sh
python3 build_as_is.py -ag -c judge_env.json -ac -qc exercises/as-is/ex2.ipynb
```

尚，`build_formatted.py` と同様に，masterは複数指定でき，それらをまとめてビルドした `conf.zip` を生成できる．

## 課題の作り方

共通事項として，ipynbの編集には[Jupyter](https://jupyter.org/)を推奨する．

### formattedの作り方

single formを配布したいなら，`exercises/formatted/ex1/ex1-1.ipynb` をコピーし，その中の指示に沿って適当に改変すればよい．

bundled formを配布したい場合は，まず適当な課題ディレクトリを作り，その中にmasterを任意個配置する．このとき，次の点を踏まえて，masterや課題ディレクトリの命名に留意すること．

* `spam` というディレクトリが指定されると，`spam/form_spam.ipynb` というformを作る．
* 正規表現 `spam/spam[-_].*\.ipynb` にマッチするファイルが `spam/form_spam.ipynb` を作るmasterと解釈される．
* `spam/form_spam.ipynb` 内での課題の順序は，masterのファイル名の辞書順である．

formatted masterの作成には，`template_formatted.py` を用いるのが安全かつ効率的である．これは，問題文（`-d`），prefillコード（`-p`），ヒントとしてformに含めるassertion（`-i`），模範解答（`-a`）の md/py ファイルから，formatted masterを構成するスクリプトである．具体的には，次のように使う．

```sh
python3 template_formatted.py -d exercises/formatted/template/cbrt.md -p exercises/formatted/template/cbrt_prefill.py -a exercises/formatted/template/cbrt_answer.py -i exercises/formatted/template/cbrt_assertion.py exercises/formatted/cbrt.ipynb
```

これで，formatted master `exercises/formatted/cbrt.ipynb` が生成される．与えられたpyファイルに基づいて，典型的なテストコードが生成されているので，そこに課題固有のテストを追加すると手際が良い．

### as-isの作り方

masterは自由に作れる．特に制限はない．ただし，ファイルサイズ（特に出力部分）が大きいと，アップロードに失敗するか，仮に成功してもブラウザ上で表示できなくなる．この点は，masterとformの双方で注意するべきである．

`build_as_is.py` は，masterに含まれるMarkdownセルの中で最初に現れる見出し（正規表現 `^#+\s+(.*)$` のグループ部分）をタイトルと解釈する．これはブラウザ上の課題表示に用いられる．もし見出しが見つからなければ，exercise_keyがタイトルとして用いられる．

解答セルを追加する（`-ac`）場合，デフォルトのprefillコードは，masterと同ディレクトリ内の `${exercise_key}.py` である．

#### 自動評価を有効にする場合

デフォルトの課題固有のテストコードは，masterと同ディレクトリ内の `test_${exercise_key}.py` である．その中身は，`exercises/as-is/` 内の具体例を参考に適当に作る．

as-isにおいて課題固有のテストコードが与えられなくても，構文検査などの共通の検査とタグ付けは行われる．

課題固有のテストコードを伴ったas-isを作成する際は，`build_as_is.py` を直接使うよりも，`Makefile` を利用する方が，簡単且つ効率的である．

### ipynbのレンダリングについて

PLAGS UTは，ipynbのレンダリングに [nbviewer.js](https://github.com/kokes/nbviewer.js) を用いている．これは，必ずしもJupyterと同じレンダリングをするわけではない．表示調整の試行錯誤の際には，[nbviewer.js live demo](https://kokes.github.io/nbviewer.js/viewer.html)で，formのレンダリングを確認すると手際が良い．

特にサイズの大きい（実行後に大きくなり得る）formを扱う時には，nbviewer.jsのレンダリングを確認する方が安全である．

## masterメタデータの詳細設定

### 課題のバージョン

masterとformのメタデータには，課題のバージョンが埋め込まれる．システムに登録された最新のmasterのバージョンに対応しないformは，提出時に形式エラーでrejectされる．そして，システムにmasterを登録・更新する際にも，課題のバージョンが検査される．具体的には，次の規則に従う．

* アップロードしたバージョンが新規のものだったら，バージョンを含めて課題を更新する．
* アップロードしたバージョンと現在のバージョンと一致していたら，課題内容だけ更新する．
* アップロードしたバージョンが過去のバージョンに含まれていたら，更新をrejectする．

このシステムの仕様に基づき，課題に意味的変更が加わった際には，バージョンを変えて，意味的変更がないとき（典型的には誤植訂正やスタイル変更）は，バージョンを保つ運用が想定されている．

`build_formatted.py` 及び `build_as_is.py` を実行する際に，`-n` オプションを与えると，masterのバージョンを更新し，新しいバージョンに対応したformを生成する．具体的には，次の規則に従う．

* `-n` が引数付きで指定されたときは，その引数（文字列）がバージョンとして設定される．
* `-n` が引数無しで指定されたときは，課題内容（formに統合される内容）から計算したSHA1ハッシュがバージョンとして設定される．
* `-n` が指定されない場合は，バージョンを保つ．
* `-n` が指定されず，master用メタデータがない（バージョンを持っていない）場合は，空文字列がバージョンとして設定される．

### 課題の締切

課題をアップロードした後，ブラウザ上で各種締切を設定できるが，masterにメタデータとして付与することもできる．その仕組みを利用すれば，ブラウザ上の手作業を減らすことができる．

#### 設定方法

`build_formatted.py` 及び `release_as_is.py` は，`-d` オプションを介して `deadlines.json` を受け取る．`-d` が指定されると，与えられたmaster全てに対し，`deadlines.json` に従って締切を設定する．例えば，次のコマンドで，締切を設定できる．

```sh
./build_formatted.py -d deadlines.json exercises/formatted/ex1
./build_as_is.py -d deadlines.json exercises/as-is/ex2.ipynb
```

ただし，指定されたmasterに関する締切が，
`deadlines.json` 内に見つからなかった場合，当該masterの締切データは更新されない．また，`-d` が指定されなかった場合も，締切データは更新されない．

#### `deadlines.json`

`deadlines.json` は，exercise_keyと締切時刻を対応付ける辞書である．具体的には，次のようになっている．

```json
{
  "ex1/": {
    "begin": "YYYY-MM-DD hh:mm:ss",
    "open":  "YYYY-MM-DD hh:mm:ss",
    "check": "YYYY-MM-DD hh:mm:ss",
    "close": "YYYY-MM-DD hh:mm:ss",
    "end":   "YYYY-MM-DD hh:mm:ss"
  },
  "ex2": {
    "open":  "YYYY-MM-DD hh:mm:ss",
    "close": "YYYY-MM-DD hh:mm:ss"
  }
}
```

ここで，`YYYY-MM-DD`は西暦の日付，`hh:mm:ss`は24時間表記の時刻である．

締切時刻の属性名は，それぞれブラウザ上の begin（公開開始）・open（提出開始）・check（締切）・close（提出終了）・end（公開終了）に対応する．

締切時刻の属性値は `null` も可能である．`null`の項目は，コースのデフォルト設定が使われる．属性値が `null` の項目は，締切時刻から省略できる．

bundled formとしてまとめられるformatted masterに対しては，exercise_keyの代わりに，`/`付きのディレクトリ名を属性名に用いることで，一括で締切時刻を設定できる．上の例では，`"ex1/"`を属性名にすることで，`exercises/formatted/ex1/ex1-{1,2}.ipynb`に対する締切を，まとめて指定している．

### Colabリンク

課題をアップロードした後，formのGoogle Drive IDをブラウザ上で指定することで，formをColabで開く ![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg) リンクをコースページに表示させることができる．このformのDrive IDについても，締切と同様に，masterのメタデータに埋め込むことで，一括で設定できる．

#### 設定方法

`build_formatted.py` 及び `build_as_is.py` は，`-gd` オプションを介して `drive.json` を受け取る．`-gd` が指定されると，与えられたmaster全てに対し，`drive.json` に従ってDrive IDを設定する．例えば，次のコマンドで設定できる．

```sh
./build_formatted.py -gd drive.json exercises/formatted/ex1
./build_as_is.py -gd drive.json exercises/as-is/ex2.ipynb
```

締切を設定する `-d` と同様に，`-gd` が指定されない場合や， `drive.json` の中に対象masterの項目が見つからなかった場合には，Drive IDは更新されない．

#### `drive.json`

`drive.json` は，課題とDrive IDを対応付ける辞書である．具体的には，次のようになっている．

```json
{
    "ex1/": "https://colab.research.google.com/drive/${DriveID}",
    "ex2": "${DriveID}"
}
```

課題を表す属性名は，`deadlines.json` と同様の規則で指定する．属性値には，上の例のように，Drive URL，Colab URL，Drive IDのいずれを設定しても，ブラウザ上の効果は同じである．属性値に `null` を設定すると，Colabリンクを削除できる．

次のGoogle Apps Scriptを使えば，Driveフォルダ内のformから `drive.json` を生成できる．

```javascript
function gen_drive_js() {
  const folderUrl = 'https://drive.google.com/drive/folders/${DriveID}' // formの設置場所
  const folderId = folderUrl.split('/').pop()
  const files = DriveApp.getFolderById(folderId).getFiles()
  const d = {}
  while (files.hasNext()) {
    const f = files.next()
    const fp = f.getUrl().split('/')
    const fid = fp[fp.length - 2]
    if (!f.getName().endsWith('.ipynb')) continue
    const metadata = JSON.parse(f.getBlob().getDataAsString())['metadata']['judge_submission']
    for (const key in metadata['exercises']) {
      d[key] = fid
    }
  }
  Logger.log(d)
  DriveApp.getRootFolder().createFile('drive.json', JSON.stringify(d))
}
```

指定したフォルダにform一式を設置後，このスクリプトを実行すると，Driveのrootディレクトリに `drive.json` が生成される．
