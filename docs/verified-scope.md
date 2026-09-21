# Verified scope and limitations

## 検証済み

install、verification、uninstallの各経路は2026-08-08に、`HOME`・`CODEX_HOME`・
`XDG_STATE_HOME`をtemporary directoryへ差し替えた使い捨てのLinux環境で、end to endに
実行しました。planとapplyの両phase、repository verificationとinstalled verification、
既存のCodex CLIを用いたplugin addとremove、uninstall、当時66件のtest suite全体が対象です。
併せて、抽出元マシンに紐づくabsolute path・symlink・親ディレクトリへのtraversalを走査し、
該当する依存は検出されませんでした。

2026-09-21には、既存のpersonal development環境でSol residentが限定されたcross-layer
変更を契約化し、task-scoped collaboratorの実装へ途中・最終reviewを行う運用観測を記録
しました。これはSolのorchestration/reviewに関する一例であり、Luna workerやAstra
Oracleの実行検証、または新規install直後のend-to-end検証ではありません。詳細は
[Sol orchestrator field note — 2026-09-21](sol-orchestrator-field-note-2026-09-21.md)
を参照してください。

2026-09-21には三役routingへの更新後に71件のtest suiteとrepository verificationを再実行し、
Astra Oracleのinstall/uninstall、新規installからのTerra除外、旧install stateに記録された
未変更Terraの削除、変更済みTerraでのfail-closed停止を隔離HOMEで確認しました。併せて、
この環境で利用可能なofficial plugin validatorも通過しました。

既存`$CODEX_HOME/AGENTS.md`の3状態（存在しない / byte単位で同一 / 内容が異なる）も、
隔離HOMEで実際に再現して契約どおりに動作することを確認しています。手順は
[Install into an existing Codex environment](install-existing-environment.md)にあります。

### 手元で再実行する

```bash
python3 bootstrap/verify.py
python3 bootstrap/verify.py --installed
python3 -m unittest discover -s tests -v
python3 evals/run.py validate
```

## 未検証

- 別の物理マシンまたはcontainer、および実行に用いたもの以外のLinux distribution。
- Codex CLIの新規インストール。実行時はインストール済みの`codex-cli 0.147.0`を
  使用しました。
- 新規のCodex loginのprovisioning、および認証を伴うmodel実行。
- **インストール後のSol・Astra・Lunaの実際のmodel呼び出し。**
- macOS、Windows、および将来のCodex CLIとの互換性。

## 欠陥ではなく意図した挙動

- `uninstall.py`はmanaged file、marketplace entry、install state、インストール済み
  pluginを削除しますが、`.codex/agents`や`.codex/bin`のような空の親ディレクトリは
  残します。これらはCodex CLI側のディレクトリであり、削除すると本プロジェクトの管理外の
  インストールを壊すおそれがあるためです。
- `verify.py --installed`はCodex CLIを必要とします。effective plugin selectionを検査
  するためです。repository verificationとinstall payload自体はCodex CLIを必要と
  しません。

## 関連

- [Managed paths](managed-paths.md)
- [Install into an existing Codex environment](install-existing-environment.md)
- [Responsibility boundaries](responsibility-boundaries.md)
