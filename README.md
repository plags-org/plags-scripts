# PLAGS Scripts for Exercises

[PLAGS UT](https://judge.eidos.ic.i.u-tokyo.ac.jp/)（通称judgeシステム）に課題をアップロードするためのスクリプト群と簡単な課題例．

## 用語

以下では，「課題」の形態に合わせて，用語を使い分ける．

* 自動評価有り（の課題）: autograde (exercise)
* 自動評価無し（の課題）: as-is (exercise)
* システムに登録するもの: master
* 受講生に配布するもの: form

autogradeとas-isでは，master/formの書式も異なり，スクリプトの使い方も異なる．

尚，as-isという名称は，masterをそのまま（*as-is*）formに使うという点に由来する．

以下では，[ipynb形式におけるmetadata](https://nbformat.readthedocs.io/en/latest/format_description.html#metadata)を単に*メタデータ*と呼ぶ．メタデータは，JupyterやColabの挙動に影響を与えず，それらの通常の利用で誤って改変されるものではない．単に，システムに対するインタフェースとして機能する．したがって，メタデータを直接編集することは想定されておらず，本レポジトリが提供するスクリプトを使って設定・更新することが想定されている．

## 各種ファイルとディレクトリ

提供するスクリプト：

* `build_autograde.py`: autogradeのビルド用スクリプト（Python 3.7以上）
* `release_as_is.py`: as-isのビルド用スクリプト（Python 3.6以上）
* `ipynb_{util,metadata}.py`: ↑2つが利用するライブラリ
* `judge_util.py`: autogradeのテストコードの記述に使うライブラリ
* `judge_setting.py`: autogradeのテスト設定の記述に使うライブラリ
* `install_judge_util.sh`: `judge_util.py`のインストール用スクリプト

課題例：

* `exercises_separate/ex1-{1,2}-find_nearest.ipynb`: autograde masterの具体例（separateモード用）
* `exercises_bundled/ex1/ex1-{1,2}-find_nearest.ipynb`: autograde masterの具体例（bundleモード用）
* `exercises_bundled/ex1/intro.ipynb`: bundleしたときの導入部分（オプショナル）
* `exercises_as-is/ex2.ipynb`: as-is masterの具体例

アップロード用ファイル：

* `autograde.zip`: autograde master一式
* `as-is_masters.zip`: as-is master一式

## スクリプトの使い方

### autogradeのビルド（separateモード）

準備として，`judge_util.py` を所定のディレクトリにインストールする．

```sh
./install_judge_util.sh exercises_separate
```

autograde masterに対して個別にformを作るseparateモードでビルドする例．

```sh
./build_autograde.py -c -t exercises_separate/ex1-{1,2}-find_nearest.ipynb
```

**効果**：

* `exercises_separate/ex1-{1,2}-find_nearest.ipynb` から出力部分を除去し，master用メタデータを設定
* `exercises_separate/form_ex1-{1,2}-find_nearest.ipynb` の作成
* `exercises_separate/ans_ex1-{1,2}-find_nearest.ipynb` の作成
* `autograde.zip` の作成（`-c`）

`form_${exercise}.ipynb`は，`${exercise}.ipynb`のformであり，`ans_${exercise}.ipynb`は，解答例・解説・テストケースをまとめたもの（answer）である．answerは，教員が授業中に表示させたり，TAに配布したりすることを想定している．

`autograde.zip` を作成する際に，副産物として `autograde/` を作るが，ビルド用ディレクトリなので消して問題ない．

### autogradeのビルド（bundleモード）

準備として，`judge_util.py` を所定のディレクトリにインストールする．

```sh
./install_judge_util.sh exercises_bundled/*
```

複数のmasterを束ねたformを作るbundleモード（`-b`）でビルドする例．

```sh
./build_autograde.py -c -b -t exercises_bundled/*
```

**効果**：

* `exercises_bundled/ex1/ex1-{1,2}-find_nearest.ipynb` からOutputを除去し，master用メタデータを設定
* `exercises_bundled/ex1/ex1.ipynb` の作成
* `exercises_bundled/ex1/ans_ex1.ipynb` の作成
* `autograde.zip` の作成（`-c`）

separateモードと違って，`ex1-{1,2}-find_nearest.ipynb`を1つのform `ex1.ipynb` にまとめている．`ex1.ipynb` の導入部分として `intro.ipynb` があれば使われ，無ければディレクトリ名だけの見出し（`# ex1`）が自動で付けられる．

`ans_ex1.ipynb`は，`ex1-{1,2}-find_nearest.ipynb`のanswerをまとめたものである．

### as-isのビルド

```sh
./release_as_is.py -c -t exercises_as-is/*.ipynb
```

**効果**：

* `exercises_as-is/*.ipynb` にmaster用メタデータを設定
* `exercises_as-is/form_*.ipynb` の作成
* `as-is_masters.zip` の作成（`-c`）

`exercises_as-is/form_${exercise}.ipynb` は，`exercises_as-is/${exercise}.ipynb` のformであり，メタデータの違いしかない．

as-isの場合は，master用メタデータが設定された `exercises_as-is/*.ipynb` を個別にアップロードしてシステムに登録できる．`as-is_masters.zip` は引数に指定された `exercises_as-is/*.ipynb` を単にまとめただけである．

## 課題の作り方

共通事項として，ipynbの編集にはJupyter(Lab| Notebook)を推奨する．

### autogradeの作り方

separateモードを使うなら`exercises_separate/ex1-1-find_nearest.ipynb`をコピーして，bundleモードを使うなら`exercises_bundled/ex1/ex1-1-find_nearest.ipynb`をコピーして，そこに書かれた指示に従って改変する．

ただし，bundleモードを利用する際には，次の点を踏まえて，ファイルやディレクトリの命名に留意すること．

* `exercises_bunbled/foo` というディレクトリは `exercises_bundled/foo/foo.ipynb` という form を作るためのディレクトリである．
* `exercises_bundled/foo/foo[-_].*\.ipynb` の正規表現にマッチするファイルが `foo.ipynb` を作るmasterと見做される．
* `foo.ipynb` 内での課題の順序は，masterのファイル名の辞書順である．

### as-isの作り方

masterを自由に作れる．特に制限はない．ただし，次の点に留意して，formとして指示を記述するべきである．

* 提出者がformのセルを全て消しても，メタデータが適切であればシステムは受理する．
* Outputが大きい（数MB）と，アップロードに成功してもブラウザ上で表示できなくなる．

`release_as_is.py` は，masterに含まれるMarkdownセルの中で最初に現れる見出し（正規表現 `^#+\s+(.*)$` のグループ部分）をタイトルと解釈する．これはブラウザ上の課題表示に用いられる．もし見出しが見つからなければ，拡張子を除いたファイル名がタイトルとして用いられる．

### exercise_key

exercise_keyとは，システム上の課題のIDであり，ブラウザ上での課題の整列順も規定する文字列である．`build_autograde.py` と `release_as_is.py` では，masterの拡張子を除いたファイル名がexercise_keyとして利用される．

exercise_keyは正規表現 `[a-zA-Z0-9_-]{1,64}` にマッチする文字列でなければならない．したがって，前述のスクリプトを利用する際には，masterのファイル名もそれに限定される．

exercise_keyは，master用メタデータとform用メタデータの両方に埋め込まれる．アップロードされるmasterが持つexercise_keyに基づいて，更新すべき課題が特定される．提出されたformが持つexercise_keyに基づいて，提出された課題が特定される．

exercise_keyの実体はipynbのメタデータにあるので，一旦メタデータが設定されたformは自由にリネームして配布できる．

## 課題のバージョン

masterとformのメタデータには，課題のバージョンが埋め込まれる．システムに登録された最新のmasterのバージョンに対応しないformは，提出時に形式エラーでrejectされる．そして，システムにmasterを登録・更新する際にも，課題のバージョンが検査される．具体的には，次の規則に従う．

* アップロードしたバージョンが新規のものだったら，バージョンを含めて課題を更新する．
* アップロードしたバージョンと現在のバージョンと一致していたら，課題内容だけ更新する．
* アップロードしたバージョンが過去のバージョンに含まれていたら，更新をrejectする．

このシステムの仕様に基づき，課題に意味的変更が加わった際には，バージョンを変えて，意味的変更がないとき（典型的には誤植訂正やスタイル変更）は，バージョンを保つ運用が想定されている．

`build_autograde.py` 及び `release_as_is.py` を実行する際に，`-n` オプションを与えると，masterのバージョンを更新し，新しいバージョンに対応したformを生成する．具体的には，次の規則に従う．

* `-n` が引数付きで指定されたときは，その引数（文字列）がバージョンとして設定される．
* `-n` が引数無しで指定されたときは，課題内容（formに統合される内容）から計算したSHA1ハッシュがバージョンとして設定される．
* `-n` が指定されない場合は，バージョンを保つ．
* `-n` が指定されず，master用メタデータがない（バージョンを持っていない）場合は，空文字列がバージョンとして設定される．

## 締切の設定

課題をアップロードした後，ブラウザ上で各種締切を設定できるが，masterにメタデータとして付与することもできる．その仕組みを利用すれば，ブラウザ上の手作業を減らすことができる．

### `deadline.json`

個々の課題の締切は，次のような中身をした `deadline.json` を使って設定できる．

```json
{
    "begins_at": "YYYY-MM-DD hh:mm:ss",
    "opens_at":  "YYYY-MM-DD hh:mm:ss",
    "checks_at": "YYYY-MM-DD hh:mm:ss",
    "closes_at": "YYYY-MM-DD hh:mm:ss",
    "ends_at":   "YYYY-MM-DD hh:mm:ss"
}
```

ここで，`YYYY-MM-DD`は西暦の日付，`hh:mm:ss`は24時間表記の時刻である．

属性名 `"begins_at"`・`"opens_at"`・`"checks_at"`・`"closes_at"`・`"ends_at"` は，それぞれブラウザ上の begin（公開開始）・open（提出開始）・check（締切）・close（提出終了）・end（公開終了）に対応する．

属性値は `null` も可能である．`null`の項目は，システムのCourse設定から自動的に計算される．属性値が `null` の項目は，省略できる．

### autogradeの場合の設定方法

例えば，次のように `-d` オプションを与えると，

```sh
./build_autograde.py -d -t exercises_separate/ex1-{1,2}-find_nearest.ipynb
```

`exercises_separate/deadline.json` を使って，`exercises_separate/ex1-{1,2}-find_nearest.ipynb` のメタデータに締切を埋め込む．`-d` が指定されない場合は，締切メタデータを変更しない．`-d` 指定されていても，`exercises_separate/deadline.json` が無かった場合には，`exercises_separate/ex1-{1,2}-find_nearest.ipynb` に対する `-d` 指定は無効になる．そして，`-d` 指定の有無にかかわらず，master用メタデータを持っていなかった場合は，全ての締切項目が `null` と設定される．

bundleモードの場合，

```sh
./build_autograde.py -b -d -t exercises_bundled/*
```

とすると，

`exercises_bundled/${dirname}/deadline.json` が，`exercises_bundled/${dirname}/${dirname}.ipynb` を構成するmasterに対して使われる．

### as-isの場合の設定方法

例えば，次のように `-d` オプションを与えると，

```sh
./release_as_is.py -d deadline.json -t exercises_as_is/*.ipynb
```

`deadline.json` を使って，`exercises_as_is/*.ipynb` の全てに共通の締切を設定する．課題毎に異なる締切を設定したいときには，個別に指定すればよい．例えば，

```sh
for i in $(seq 2 4)
do
    ./release_as_is.py -a -d deadline${i}.json -t exercises_as-is/ex${i}.ipynb
done
```

とすれば，`deadline${i}.json` によって締切が設定された `exercises_as-is/ex${i}.ipynb` が生成される．その後，`-d` を指定せずに `-c` を指定して `as-is_masters.zip` を作れば，異なる締切の課題を一括でアップロードできる．
