# Work Time Logger (wtl) クイックスタートガイド

このガイドでは、設定プロファイル (`export-profile.toml`) を活用してカスタマイズしたジョブのインポートから、TUIを使った実際の記録開始までの流れを説明します。

## 1. 設定プロファイルの確認・編集

`wtl` では、`~/.wtl/export-profile.toml` の設定を編集することで、インポートするCSVのカラム名と内部データの紐づけ(`import.mapping`)を自由に設定できます。
（※ファイルがない場合は、一度ダミーで `uv run wtl log export` を実行すると雛形が生成されます）

以下のように `[import.mapping]` セクションを追記・編集します。
この設定により、「CSVの `type` 列」と「`ticket` 列」をハイフンで繋げて、自動的に `job_code` としてデータベースに登録することができます。

```toml
[import.mapping]
name = "{name}"
description = "{description}"
job_code = "{type}-{ticket}"
```

## 2. ジョブの準備とインポート

次に、インポートする対象のプロジェクトと、上記のフォーマットに合わせたCSVファイル (`docs/sample_jobs.csv`) を準備します。

**docs/sample_jobs.csv** の例:
```csv
name,description,type,ticket
Fix Database,Fixing the database bug,DEV,001
Update UI,Updating the main dashboard UI,FE,102
Document API,Writing API docs for new endpoint,DOC,055
```

以下のコマンドを実行し、「Example Project」へジョブを一括インポートします。

```bash
# プロジェクトの作成
uv run wtl project add -n "Example Project"

# プロファイル（雛形）を利用したCSVのインポート
uv run wtl job import docs/sample_jobs.csv -p "Example Project"
```

これにより、「Fix Database」ジョブの `job_code` の値は自動的に `"DEV-001"` として取り込まれます。  
※この `job_code` 属性は、のちのエクスポート機能などでもタグやラベルとして集計に利用できます。

## 3. TUI (ターミナルUI) で記録を開始する

ジョブがインポートできたら、さっそく TUI を起動して作業時間を記録してみましょう。

```bash
uv run wtlui
```

### 便利な操作方法・ショートカット

- **検索と作業開始 (`s` キー)**
  `s` キーを押すと「ジョブ検索モーダル」が開きます。数文字入力するだけでインポートしたジョブを絞り込め、`Enter` でタイマーをすぐに開始できます。
- **未割り当てのまま開始 (`S` キー / Shift+s)**
  プロジェクトやジョブを決めずに、裏でタイマーだけを走らせたいときに便利です。後からログを選択してジョブを「割り当て (Assign)」できます。
- **ログの直接編集 (セルで `Enter` キー)**
  記録されたログのセルを選択して `Enter` を押すと、その場で内容を編集できます。開始/終了時刻は `↑` `↓` 矢印キーで手軽に微調整が可能です。
- **その他**: `x` で現在の作業の終了、`D` (Shift+d) で選択中のログの削除を行えます。
