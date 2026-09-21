# Managed paths

`bootstrap/install.py --apply`が書き込む先の一覧です。planフェーズ
（`python3 bootstrap/install.py`）で実際の対応を表示できます。

| Versioned source | Default deployment |
| --- | --- |
| `config/AGENTS.md` | `$CODEX_HOME/AGENTS.md` |
| `agents/luna_worker.toml` | `$CODEX_HOME/agents/luna_worker.toml` |
| `agents/astra_oracle.toml` | `$CODEX_HOME/agents/astra_oracle.toml` |
| `bin/run-luna-worker` | `$CODEX_HOME/bin/run-luna-worker` |
| `bin/luna-packet-guard` | `$CODEX_HOME/bin/luna-packet-guard` |
| `bin/codex-observe` | `$CODEX_HOME/bin/codex-observe` |
| `bin/codex-observe-shim` | `$HOME/.local/bin/codex-observe` |
| `codex_observability` | `$CODEX_HOME/lib/codex_observability` |
| `plugins/resident-engineering-patterns` | `$HOME/plugins/resident-engineering-patterns` |
| `config/config.base.toml` + `config/local.toml` | `$CODEX_HOME/config.toml` |

installerは所有情報とdigestを`~/.local/state/codex-exosphere/install-state.json`へ
保存します。既存の異なるファイルを上書きせず、uninstallもinstallerが作成し、その後
変更されていないartifactだけを削除します。

旧版が作成した`$CODEX_HOME/agents/terra_reviewer.toml`は新規install対象ではありません。
旧install stateに記録され、かつ記録済みdigestと現物が一致する場合に限り、uninstallerが
legacy managed pathとして削除します。内容が変更されている場合は削除せず、uninstall全体を
fail closedで停止します。

## `$HOME/.local/bin`について

`codex-observe`コマンドは`$HOME/.local/bin`へ設置されます。このディレクトリが`PATH`に
含まれていない環境では、コマンド名では起動できません。その場合は
`$CODEX_HOME/bin/codex-observe`を直接実行するか、`$HOME/.local/bin`を`PATH`へ追加して
ください。

## `config.toml`の生成

`--local-config`を渡した場合だけ、installerは`config/config.base.toml`と指定した
local overrideから`$CODEX_HOME/config.toml`を生成します。渡さない場合、`config.toml`は
managed targetになりません。

## 関連

- [Install into an existing Codex environment](install-existing-environment.md) — `CONFLICT`の扱い
- [Verified scope and limitations](verified-scope.md) — install / uninstall経路の検証状況
