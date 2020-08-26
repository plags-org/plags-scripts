# PLAGS Scripts for Exercises

[PLAGS UT](https://judge.eidos.ic.i.u-tokyo.ac.jp/)（通称judgeシステム）に課題をアップロードするためのスクリプト群と簡単な課題例．

## 準備

### 用語

以下では，「課題」の形態に合わせて，用語を使い分ける．

* 自動評価有り（の課題）: autograde (exercise)
* 自動評価無し（の課題）: as-is (exercise)
* 課題内容を定義するもの: source
* システムに登録するもの: master
* 受講生に配布するもの: form

autogradeとas-isでは，source/master/formの書式も異なり，スクリプトの使い方も異なる．

尚，as-isという名称は，sourceをそのまま（*as-is*）masterとformに使うという点に由来する．

### 動作環境

* Python 3.7以上
* sourceの編集にはJupyter(Lab| Notebook)を推奨

## 各種ファイルとディレクトリ

提供するスクリプト：

* `build_autograde.py`: autograde sourceの為のスクリプト
* `release_as_is.py`: as-is sourceの為のスクリプト
* `ipynb_{util,metadata}.py`: ↑2つが利用するライブラリ
* `exercises/ex1/.judge/judge_util.py`: autogradeのテストコードの記述に使うライブラリ

課題例：

* `exercises/ex1/ex1-{1,2}-find_nearest.ipynb`: autograde sourceの具体例
* `exercises/ex1/ex1.ipynb`: ↑2つを統合したautograde form
* `exercises/ex1/intro.ipynb`: `ex1.ipynb` の導入部分（オプショナル）
* `exercises_as-is/ex2.ipynb`: as-is source兼formの具体例

アップロード用ファイル：

* `autograde.zip`: autograde master一式
* `as-is_masters.zip`: as-is master一式

## スクリプトの使い方

```sh
./build_autograde.py -c -n
```

**効果**：

* `exercises/ex1/ex1.ipynb` の作成
* `exercises/ex1/ans-ex1.ipynb` の作成
* `exercises/ex1/ex1-{1,2}-find_nearest.ipynb` におけるOutputの除去
* `autograde.zip` の作成（`-c`）
* `exercises/ex1/ex1-{1,2}-find_nearest.ipynb` のバージョン更新（`-n`）

`-n` に引数を与えた場合は，その引数（文字列）がバージョンとして設定される．上の例の様に無引数の場合は，それぞれの課題内容（formに統合される内容）から計算したSHA1ハッシュがバージョンとして設定される．バージョン設定の際には，メタデータはmaster用にリセットされる．`-n` 指定の有無にかかわらず，master用メタデータを持っていないときは，バージョンには空文字列が設定される．

`ans-ex1.ipynb` は，`ex1.ipynb`の解答例・解説・テストケースをまとめたものである．教員が授業中に表示させたり，TAに配布したりすることを想定している．

`autograde.zip` を作成する際に，副産物として `autograde/` を作るが，ビルド用ディレクトリなので消して問題ない．

```sh
./release_as_is.py -z -t exercises_as-is/*.ipynb
```

**効果**：

* `exercises/*.ipynb` をformとして設定
* `as-is_masters/*.ipynb` の作成
* `as-is_masters.zip` の作成（`-z`）

`as-is_masters.zip` は `as-is_masters/*.ipynb` を単にまとめただけである．システムに対して，`as-is_masters/*.ipynb` を個別にアップロードすることもできる．

## 課題の作り方

### autogradeの作り方

`exercises/ex1/ex1-1-find_nearest.ipynb` をコピーして，そこに書かれた指示に従って改変する．更に，次の点を踏まえて，ファイルやディレクトリの命名に留意すること．

* `exercises/foo` というディレクトリは `exercises/foo/foo.ipynb` という form を作るためのディレクトリである．
* `exercises/foo/foo[-_](.*).ipynb` の正規表現にマッチするファイルを `foo.ipynb` を作る source として扱われる．
* `foo.ipynb` 内での課題の順序は，source のファイル名の辞書順である．

### as-isの作り方

sourceを自由に作れる．特に制限はない．ただし，次の点に留意して，formとして指示を記述するべきである．

* 提出者がformのセルを全て消しても，メタデータが適切であればシステムは受理する．
* Outputが大きい（数MB）と，アップロードに成功してもブラウザ上で表示できなくなる．

### 課題ID

autogradeでもas-isでも，sourceの拡張子を除いたファイル名が，システム上の課題ID（DB上でのkey）として扱われる．アップロードした際に，課題IDに基いて課題が更新される．そして，as-isの課題IDは，ブラウザ上での表示名を兼ねる．

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

属性名 `"begins_at"`・`"opens_at"`・`"checks_at"`・`"closes_at"`・`"ends_at"` は，それぞれブラウザ上の `begin`（公開開始）・`open`（投稿開始）・`check`（締切）・`close`（投稿終了）・`end`（公開終了）に対応する．

属性値は `null` も可能である．`null`の項目は，システムのCourse設定から自動的に計算される．属性値が `null` の項目は，省略できる．

### autogradeの場合の設定方法

例えば，次のように `-d` オプションを与えると，

```sh
./build_autograde.py -d
```

`exercises/ex1/deadline.json` を使って，`exercises/ex1/ex1-{1,2}-find_nearest.ipynb` のメタデータに締切を埋め込む．指定されない場合は，締切メタデータを変更しない．`-d` 指定されていても，
`exercises/ex1/deadline.json` が無かった場合には，`exercises/ex1/ex1-{1,2}-find_nearest.ipynb` に対する `-d` 指定は無効になる．そして，`-d` 指定の有無にかかわらず，master用メタデータを持っていなかった場合は，全ての締切項目が `null` と設定される．

### as-isの場合の設定方法

例えば，次のように `-d` オプションを与えると，

```sh
./release_as_is.py -d deadline.json -t exercises_as_is/*.ipynb
```

`deadline.json` を使って，`as-is_masters/*.ipynb` の全てに共通の締切を設定する．課題毎に異なる締切を設定したいときには `-a` オプションと併用して，masterを追加していくようにする．例えば，

```sh
for i in $(seq 2 4)
do
    ./release_as_is.py -a -d deadline${i}.json -t exercises_as-is/ex${i}.ipynb
done
```

とすれば，`deadline${i}.json` によって締切が設定された `as-is_masters/ex${i}.ipynb` が生成される．
