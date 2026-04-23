# Configuration Profile (`profile.toml`)

`~/.wtl/profile.toml` は、インポート時と、エクスポート時のデータ構造を定義するファイルです。

テンプレート文字列には **Jinja2** 構文を使います。変数の埋め込みは `{{ 変数名 }}`、条件分岐は `{% if ... %}...{% endif %}` で記述できます。

## セクション構造

- `[import.mapping]`: インポート時、CSVの列を内部データ構造にどう組み込むかを設定します。
- `[export.extract]`: エクスポート時、内部の `job_code` を分解して変数を取り出すルールを設定します（正規表現）。
- `[export.defaults]`: 抽出した変数が空だった場合の初期値を設定します。
- `[export]`: 変数をもとに作業記録をどうグループ化・合算し、どうフォーマットするかを設定します。
- `[export.format]`: 備考の書式を設定します。
- `[export.columns]`: 最終的に出力するCSVのカラム（ヘッダーと中身）を設定します。
- `[tui]`: TUI（ターミナルUI）固有の動作設定を行います。

---

### import.mapping

CSVインポート時に各列をどのジョブ属性に対応させるかを Jinja2 テンプレートで指定します。

- `name`: データベースの `name`（ジョブ名）として登録する値。
- `description`: データベースの `description`（ジョブの詳細）として登録する値。
- `job_code`: データベースの `job_code`（識別・集計用のコード）として登録する値。

```toml
[import.mapping]
# CSVの "name" 列
name     = "{{ name }}"
# CSVの "type" 列と "ticket" 列を組み合わせる
job_code = "{{ type }}-{{ ticket }}"
```

---

### export.extract

`job_code` を正規表現で分解して変数を取り出します。正規表現の名前付きグループ `(?P<変数名>パターン)` で記述します。

```toml
[export.extract]
# "DEV-001" を type='DEV', ticket='001' に分解する
job_code = "^(?P<type>[A-Za-z]+)-(?P<ticket>\\d+)$"
```

`[export.defaults]` では、正規表現にマッチしなかった場合の初期値を設定します。

```toml
[export.defaults]
type   = "General"
ticket = "None"
```

---

### export

```toml
[export]
# type と ticket が同じログを1行にまとめ、作業時間を合算する
group_by = ["type", "ticket"]
# 合計時間の精度と丸め方: "round" | "floor" | "ceil"
time_precision = 2
time_rounding  = "round"
# 集計方法: "sum_then_round" | "round_then_sum" | "round_subtotal_then_sum"
# "round_subtotal_then_sum" は各詳細項目の小計を丸めてから合計します。
time_aggregation_method = "sum_then_round"
```

---

### export.format

`aggregated_notes` の各ログの書式を設定します。Jinja2 の条件分岐も使えます。

- `note_item`: 各ログの書式を設定します。
- `note_separator`: 複数備考の区切り文字を設定します。

```toml
[export.format]
# 例: "001:1.5 (DB修正)" または "001:1.5"
note_item = "{{ ticket }}:{{ time_hours }}{% if memo %} ({{ memo }}){% endif %}"
note_separator = " / "
```

---

### export.columns

出力するCSVの「ヘッダー名」と「中身」を対応づけます。中身は Jinja2 テンプレートです。

```toml
[export.columns]
"種別"     = "{{ type }}"
"チケット"  = "{{ ticket }}"
"作業時間"  = "{{ aggregated_time }}"
"備考詳細"  = "{{ aggregated_notes }}"
```

> [!NOTE]
> `export.columns` では、`aggregated_time` と `aggregated_notes` に加え、グループ化の基準となった変数（`type` や `ticket` など）も使用できます。これらはグループ内の最初のログエントリから取得されます。

---

### tui

TUIの挙動をカスタマイズします。


---

## 利用可能な変数一覧

### ログ1件が持つ基本データ（`note_item` 等で使用）

| 変数名         | 説明                                          |
| :------------- | :-------------------------------------------- |
| `project_name` | プロジェクト名                                |
| `job_name`     | ジョブ名                                      |
| `memo`         | その作業の備考欄                              |
| `time_hours`   | その作業にかかった時間（時間単位、小数）      |

*(上記に加え、`[export.extract]` で分解した独自変数（例: `type`, `ticket`）も使えます)*

### グループ集計後のデータ（`export.columns` で使用）

| 変数名             | 説明                                                         |
| :----------------- | :----------------------------------------------------------- |
| `aggregated_time`  | グループ内の全作業時間の合計                                 |
| `aggregated_notes` | グループ内の `note_item` を `note_separator` で連結した結果  |
| *(独自変数)*       | `[export.extract]` で取り出した変数（最初の1件の値）         |

---

## 実用例（社内プロジェクト管理）

job_code を `プロジェクトコード_工程_チケット番号` の形式で管理し、プロジェクト×工程単位に集計するシナリオです。

```toml
[export.extract]
# "PA2401_DEV_042" → project_code='PA2401', phase='DEV', ticket='042'
job_code = "^(?P<project_code>[^_]+)_(?P<phase>[^_]+)_(?P<ticket>[^_]+)$"

[export.defaults]
project_code = "UNKNOWN"
phase        = ""
ticket       = ""

[export]
# プロジェクト×工程単位で作業時間を集計
group_by       = ["project_code", "phase"]
time_precision = 2
time_rounding  = "round"

[export.format]
# チケット番号がある場合は付記、ない場合はメモのみ
note_item      = "{% if ticket %}[#{{ ticket }}] {% endif %}{{ memo }}"
note_separator = " / "

[export.columns]
"プロジェクトコード" = "{{ project_code }}"
"工程"              = "{{ phase }}"
"合計工数 (h)"      = "{{ aggregated_time }}"
"作業内容"           = "{{ aggregated_notes }}"

[import.mapping]
# CSVの "name" 列をジョブ名、複数列を組み合わせて job_code に
name     = "{{ name }}"
job_code = "{{ project_code }}_{{ phase }}_{{ ticket }}"
```

**対応する `sample-jobs.csv` の例:**

```csv
name,project_code,phase,ticket
要件定義MTG,PA2401,MGT,001
基本設計書作成,PA2401,DEV,002
単体テスト計画,PA2401,TEST,010
進捗報告,PB2402,MGT,001
```
