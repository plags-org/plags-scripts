# PLAGS Scripts for Exercises

[PLAGS UT](https://plags.eidos.ic.i.u-tokyo.ac.jp/)に課題をアップロードするためのスクリプト群と簡単な課題例．

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

* `build_autograde.py`: autogradeのビルド用スクリプト（Python 3.8以上）
* `template_autograde.py`: autogradeのテンプレート生成スクリプト（Python 3.8以上，要 `pip astunparse`）
* `release_as_is.py`: as-isのビルド用スクリプト（Python 3.6以上）
* `judge_util.py`: autogradeのテストコードの記述に使うライブラリ
* `judge_setting.py`: `build_autograde.py` が利用するライブラリ
* `ipynb_{util,metadata}.py`: `build_autograde.py` `release_as_is.py` が利用するライブラリ

課題例：

* `exercises/autograde/ex1-3-find_nearest_str.ipynb`: autograde masterの具体例（separateモード用）
* `exercises/autograde/ex1/ex1-{1,2}-find_nearest.ipynb`: autograde masterの具体例（bundleモード用）
* `exercises/autograde/ex1/intro.ipynb`: bundleしたときの導入部分（オプショナル）
* `exercises/as-is/ex2.ipynb`: as-is masterの具体例

アップロード用ファイル：

* `autograde.zip`: autograde master一式
* `as-is_masters.zip`: as-is master一式

## スクリプトの使い方

### autogradeのビルド

#### separateモードのビルド

autograde masterに対して個別にformを作るseparateモードでビルドする例．

```sh
./build_autograde.py -lp -s exercises/autograde/ex1-3-find_nearest_str.ipynb
```

**効果**：

* `exercises/autograde/ex1-3-find_nearest_str.ipynb` から出力部分を除去し，master用メタデータを設定
* `exercises/autograde/form_ex1-3-find_nearest_str.ipynb` の作成
* `exercises/autograde/ans_ex1-3-find_nearest_str.ipynb` の作成
* `exercises/autograde/.judge/judge_util.py` の設置（`-lp`）

`form_${exercise}.ipynb`は，`${exercise}.ipynb`のformであり，`ans_${exercise}.ipynb`は，解答例・解説・テストケースをまとめたもの（answer）である．answerは，教員が授業中に表示させたり，TAに配布したりすることを想定している．

`-s` は任意個の引数を取ることができる．したがって，コマンドラインのワイルドカード指定などを使うことで，一括ビルドができる．

`-lp` は，指定されたmasterが利用する `judge_util.py` をインストールする．課題例のmasterのテストコードは，`.judge/judge_util.py` を使うように記述されているので，インストールしないとローカルでもサーバでも動作しない．レポジトリ内の `judge_util.py` が更新される場合に備えて，毎回 `-lp` を指定する方が安全である．

#### bundleモードのビルド

複数のmasterを束ねたformを作るbundleモードでビルドする例．

```sh
./build_autograde.py -lp -s exercises/autograde/ex1
```

**効果**：

* `exercises/autograde/ex1/ex1-{1,2}-find_nearest.ipynb` からOutputを除去し，master用メタデータを設定
* `exercises/autograde/ex1/form_ex1.ipynb` の作成
* `exercises/autograde/ex1/ans_ex1.ipynb` の作成
* `exercises/autograde/ex1/.judge/judge_util.py` の設置（`-lp`）

separateモードと違って，`ex1-{1,2}-find_nearest.ipynb`を1つのform `form_ex1.ipynb` にまとめている．`form_ex1.ipynb` の導入部分として `intro.ipynb` があれば使われ，無ければディレクトリ名だけの見出し（`# ex1`）が自動で付けられる．

`ans_ex1.ipynb`は，`ex1-{1,2}-find_nearest.ipynb`のanswerをまとめたものである．

ビルドが，bundleモードになるかseparateモードになるは，`-s` で指定される対象がディレクトリかipynbかで決まる．それらを混合して指定することもできる．

#### `autograde.zip` の生成

アップロード用設定ファイル `autograde.zip` を生成するには，アップロード対象のmaster全てを対象に指定して，`-c` オプションで実行する．

```sh
./build_autograde.py -c judge_env.json -lp -s exercises/autograde/ex1*
```

**効果**：

* `./build_autograde.py -lp -s exercises/autograde/ex1` の効果
* `./build_autograde.py -lp -s exercises/autograde/ex1-3-find_nearest_str.ipynb` の効果
* `exercises/autograde/ex1/ex1-{1,2}-find_nearest.ipynb` と
  `exercises/autograde/ex1-3-find_nearest_str.ipynb` からなる `autograde.zip` を作成

`autograde.zip` を作成する際に，副産物として `autograde/` を作るが，ビルド用ディレクトリなので消して問題ない．

`-c` の引数 `judge_env.json` は，自動評価環境のパラメタをまとめたJSONファイルであり，PLAGS UTの管理者によって指定される．

### as-isのビルド

```sh
./release_as_is.py -c -s exercises/as-is/*.ipynb
```

**効果**：

* `exercises/as-is/*.ipynb` にmaster用メタデータを設定
* `exercises/as-is/form_*.ipynb` の作成
* `as-is_masters.zip` の作成（`-c`）

`exercises/as-is/form_${exercise}.ipynb` は，`exercises/as-is/${exercise}.ipynb` のformであり，メタデータの違いしかない．

as-isの場合は，master用メタデータが設定された `exercises/as-is/*.ipynb` を個別にアップロードしてシステムに登録できる．`as-is_masters.zip` は引数に指定された `exercises/as-is/*.ipynb` を単にまとめただけである．

## 課題の作り方

共通事項として，ipynbの編集にはJupyter(Lab| Notebook)を推奨する．

### autogradeの作り方

separateモードを使うなら`exercises/autograde/ex1-3-find_nearest_str.ipynb`をコピーして，bundleモードを使うなら`exercises/autograde/ex1/ex1-1-find_nearest.ipynb`をコピーして，そこに書かれた指示に従って改変すればよい．

ただし，bundleモードを利用する際には，次の点を踏まえて，ファイルやディレクトリの命名に留意すること．

* `spam` というディレクトリが指定されると，`spam/form_spam.ipynb` というformを作る．
* `spam/spam[-_].*\.ipynb` の正規表現にマッチするファイルが `spam/form_spam.ipynb` を作るmasterと見做される．
* `spam/form_spam.ipynb` 内での課題の順序は，masterのファイル名の辞書順である．

個々のautograde masterのテストコードの作成には，`template_autograde.py`を用いる方が安全かつ効率的である．

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

### ipynbのレンダリングについて

PLAGS UTは，ipynbのレンダリングに [nbviewer.js](https://github.com/kokes/nbviewer.js) を用いている．これは，必ずしもJupyterと同じレンダリングをするわけではない．表示調整の試行錯誤の際には，[nbviewer.js live demo](https://kokes.github.io/nbviewer.js/viewer.html)で，formのレンダリングを確認すると手際が良い．

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

### 設定方法

`build_autograde.py` 及び `release_as_is.py` は，`-d` オプションの引数として `deadlines.json` を指定できる．`-d` を指定すると，`-s` で指定された対象のmaster全てについて，`deadlines.json` に従って締切を設定する．逆に，`-d` が指定されない場合は，締切を変更しない．例えば，次のコマンドで，締切を設定できる．

```sh
./build_autograde.py -d deadlines.json -s exercises/autograde/ex1*
./release_as_is.py -d deadlines.json -s exercises/as-is/ex2.ipynb
```

ただし，`deadlines.json` の中に対象masterに関する締切情報が見つからなかった場合，当該masterの締切は更新されない．

### `deadlines.json`

`deadlines.json` は，exercise_keyと締切時刻を対応付ける辞書である．具体的には，次のようになっている．

```json
{
  "ex1-3-find_nearest_str": {
    "begin": "YYYY-MM-DD hh:mm:ss",
    "open":  "YYYY-MM-DD hh:mm:ss",
    "check": "YYYY-MM-DD hh:mm:ss",
    "close": "YYYY-MM-DD hh:mm:ss",
    "end":   "YYYY-MM-DD hh:mm:ss"
  },
  "ex1/": {
    "open":  "YYYY-MM-DD hh:mm:ss",
    "close": "YYYY-MM-DD hh:mm:ss"
  },
  "ex2": {
  }
}
```

ここで，`YYYY-MM-DD`は西暦の日付，`hh:mm:ss`は24時間表記の時刻である．

締切時刻の属性名は，それぞれブラウザ上の begin（公開開始）・open（提出開始）・check（締切）・close（提出終了）・end（公開終了）に対応する．

締切時刻の属性値は `null` も可能である．`null`の項目は，コースのデフォルト設定が使われる．属性値が `null` の項目は，締切時刻から省略できる．

bundleモードでまとめられるautogradeに対しては，exercise_keyの代わりに，`/`付きのディレクトリ名を属性名に用いることで，一括で締切時刻を設定できる．上の例では，`"ex1/"`をキーにすることで，`exercises/autograde/ex1/ex1-{1,2}-find_nearest.ipynb`に対する締切を指定している．

## Colabリンクの設定

課題をアップロードした後，formのGoogle Drive IDをブラウザ上で指定することで，formをColabで開く ![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg) リンクをコースページに表示させることができる．このformのDrive IDについても，締切情報と同様に，masterのメタデータに埋め込むことで，一括で設定できる．

### 設定方法

`build_autograde.py` 及び `release_as_is.py` は，`-gd` オプションの引数として `drive.json` を指定できる．`-gd` を指定すると，`-s` で指定された対象のmaster全てについて，`drive.json` に従ってformのDrive IDを設定する．例えば，次のコマンドで設定できる．

```sh
./build_autograde.py -gd drive.json -s exercises/autograde/ex1*
./release_as_is.py -gd drive.json -s exercises/as-is/ex2.ipynb
```

締切を設定する `-d` と同様に，`-gd` が指定されない場合や， `drive.json` の中に対象masterの項目が見つからなかった場合には，Drive IDは更新されない．

### `drive.json`

`drive.json` は，課題とDrive IDを対応付ける辞書である．具体的には，次のようになっている．

```json
{
    "ex1-3-find_nearest_str": "https://drive.google.com/file/d/${DriveID}/view?usp=sharing",
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
