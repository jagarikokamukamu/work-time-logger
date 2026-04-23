# Work Time Logger (wtl) クイックスタートガイド

このガイドでは、設定プロファイル (`profile.toml`) を活用してカスタマイズしたジョブのインポートから、TUIを使った実際の記録開始までの流れを説明します。

## 1. 設定プロファイルの確認・編集

`wtl` では、`~/.wtl/profile.toml` の設定を編集することで、インポートするCSVのカラム名と内部データの紐づけ(`import.mapping`)を自由に設定できます。
以下のコマンドを実行すると、設定ファイルが（存在しない場合は作成された上で）システムのデフォルトエディタで開かれます。

```bash
wtl profile open
```

> [!TIP]
> プレースホルダ (`{time_hours}`, `{project_name}` 等) で使える変数の完全な仕様やリストは [docs/profile.md](profile.md) を参照してください。
以下のように `[import.mapping]` セクションを追記・編集します。
この設定により、「CSVの `type` 列」と「`ticket` 列」をハイフンで繋げて、自動的に `job_code` としてデータベースに登録することができます。

```toml
[import.mapping]
name = "{{ name }}"
description = "{{ description }}"
job_code = "{{ type }}-{{ ticket }}"
```

## 2. ジョブの準備とインポート

次に、インポートする対象のプロジェクトと、上記のフォーマットに合わせたCSVファイル (`docs/sample-jobs.csv`) を準備します。

**docs/sample-jobs.csv** の例:

```csv
name,description,type,ticket
Fix Database,Fixing the database bug,DEV,001
Update UI,Updating the main dashboard UI,FE,102
Document API,Writing API docs for new endpoint,DOC,055
```

以下のコマンドを実行し、「Example Project」へジョブを一括インポートします。

```bash
# プロジェクトの作成
wtl project add -p "Example Project"

# プロファイル（雛形）を利用したCSVのインポート
wtl job import docs/sample-jobs.csv -p "Example Project"
```

これにより、「Fix Database」ジョブの `job_code` の値は自動的に `"DEV-001"` として取り込まれます。  
※この `job_code` 属性は、のちのエクスポート機能などでもタグやラベルとして集計に利用できます。

## 3. TUI (ターミナルUI) で記録を開始する

ジョブがインポートできたら、さっそく TUI を起動して作業時間を記録してみましょう。

```bash
wtlui
```

### 便利な操作方法・ショートカット

- **検索と作業開始 (`s` キー)**
  `s` キーを押すと「ジョブ検索モーダル」が開きます。数文字入力するだけでインポートしたジョブを絞り込め、`Enter` でタイマーをすぐに開始できます。
- **未割り当てのまま開始 (`S` キー / Shift+s)**
  プロジェクトやジョブを決めずに、裏でタイマーだけを走らせたいときに便利です。後からログを選択してジョブを「割り当て (Assign)」できます。
- **ログの直接編集 (セルで `Enter` キー)**
  記録されたログのセルを選択して `Enter` を押すと、その場で内容を編集できます。開始/終了時刻は `↑` `↓` 矢印キーで手軽に微調整が可能です。
- **その他**: `x` で現在の作業の終了、`D` (Shift+d) で選択中のログの削除を行えます。

## 4. プロジェクトの整理（アーカイブ機能）

プロジェクトが増えてきて、選択リストが煩雑になってきたら「アーカイブ機能」を活用しましょう。
アーカイブされたプロジェクトは、TUIのツリーやCLIのデフォルトリストから隠されます。

- **CLIでアーカイブ**: `wtl project archive -p "Project Name"`
- **TUIでアーカイブ**: サイドバーのプロジェクトを選択して `z` キー。
- **アーカイブを表示**: TUIで `Z` (Shift+z) を押すと、アーカイブ済みのプロジェクトが `[A]` マーク付きで表示されます。もう一度 `z` を押せばアクティブに戻せます。
