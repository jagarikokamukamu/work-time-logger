# Configuration Profile (`profile.toml`)

`~/.wtl/profile.toml` は、インポート時と、エクスポート時のデータ構造を定義するファイルです。

## セクション構造

デフォルトで生成される `profile.toml` は、以下のセクションに分かれています。

- `[import.mapping]`: インポート時、CSVの列を内部データ構造にどう組み込むかを設定します。
- `[export.extract]`: エクスポート時、内部の `job_code` を分解して変数を取り出すルールを設定します。
- `[export.defaults]`: 抽出した変数が空だった場合の初期値（デフォルト値）を設定します。
- `[export]`: 変数をもとに作業記録をどうグループ化・合算し、どうフォーマットするかを設定します。
- `[export.columns]`: 最終的に出力するCSVのカラム（ヘッダーと中身）を設定します。

### import.mapping

`[import.mapping]` セクションでは、CSVをインポートする際に読み込む列を指定します。

- `name`: データベースの `name` (ジョブ名) として登録する値を引数や固定文字列で指定します。
- `description`: データベースの `description` (ジョブの詳細) として登録する値を指定します。
- `job_code`: データベースの `job_code` (識別・集計用のコード) として登録する値を指定します。

```toml
[import.mapping]
# CSVの "name" 列をそのままジョブ名にする
name = "{name}"
# CSVの "詳細" 列を詳細にする
description = "{詳細}"
# CSVの "type" 列と "ticket" 列をハイフンで繋いで job_code にする
job_code = "{type}-{ticket}"
```

### export

- `group_by`: どの変数を基準にして作業データを**グループ合算**するかを指定します。

```toml
[export]
# type と ticket が同じログは、1行にまとめて作業時間を合算する！
group_by = ["type", "ticket"]
```

### export.extract

- `job_code`: エクスポート時に `job_code` をどう解釈し、分解するかを指定します。正規表現の名前付きグループ `(?P<変数名>パターン)` で記述します。

`[export.defaults]` セクションでは、`[export.extract]` > `job_code`で指定した正規表現にマッチしなかった場合（または空の場合）の初期値を指定します。

- **左側のキー**: デフォルト値を設定したい変数名を指定します（例: `type`）。
- **右側の値**: 正規表現にマッチしなかった場合に入る初期値を指定します（例: `"General"`）。

```toml
[export.extract]
# "DEV-001" を "type"='DEV' と "ticket"='001' という変数に分解する
job_code = "^(?P<type>[A-Za-z]+)-(?P<ticket>\\d+)$"

[export.defaults]
# 正規表現にマッチしなかった場合（または空の場合）の初期値
type = "General"
ticket = "None"
```

### export.format

`[export.format]` セクションでは、`{aggregated_notes}` の書式を設定します。

- `note_item`: 各ログの備考 (`memo`) 等をどのようなフォーマットで表記するかを指定します。
- `note_separator`: 各ログの`note_item`を結合する際の区切り文字を指定します。

```toml
[export.format]
# 1行にまとめる際、各ログのnoteをどういうフォーマットで表記するか
note_item = "[{project_name}/{job_name}] {time_hours}h: {memo}"
# 複数の備考を何で区切って繋げるか
note_separator = " / "
```

### export.columns

`[export.columns]`セクションで、出力するCSVの実際の「ヘッダー名」と「中身」を対応づけます。

- **左側のキー（`"種別"` 等）**: 出力されるCSVのカラム名として**自由に決めてよい**名前です。
- **右側の値（`"{type}"` 等）**: 事前定義済みの変数（**決まっている変数名**）を使って、その列に入るデータを指定します。

```toml
[export.columns]
"種別" = "{type}"
"チケット番号" = "{ticket}"
"合計作業時間" = "{aggregated_time}"
"作業詳細 (合算)" = "{aggregated_notes}"
```

---

## 利用可能な変数一覧

プロファイル（`{}` の中）で使える事前定義済みの変数です。

### ログ1件が持つ基本データ（`export.format.note_item` 等で使用）

| 変数名         | 説明                                        |
| :------------- | :------------------------------------------ |
| `project_name` | プロジェクト名                              |
| `job_name`     | ジョブ名                                    |
| `memo`         | その作業の備考欄                            |
| `time_hours`   | その作業にかかった時間（時間単位、小数2桁） |

*(※上記に加え、`[export.extract]`で分解した独自変数(例:`type`, `ticket`)も使えます)*

### グループ集計後のデータ（`export.columns` で使用）

| 変数名             | 説明                                                        |
| :----------------- | :---------------------------------------------------------- |
| `aggregated_time`  | グループ内の全作業時間の合計 (`time_hours` の合計)          |
| `aggregated_notes` | グループ内の `note_item` を `note_separator` で連結した結果 |
