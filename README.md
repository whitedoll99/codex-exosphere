# codex-exosphere

`codex-exosphere` は、resident Codexが判断と最終検収を保持しながら、明確で限定された実装作業をLuna workerへ委譲するための、単一利用者向けCodex開発ハーネスです。

[English](README_en.md)

## 提供するもの

- Codexのグローバル作業規約と、Sol・Luna・Terraのモデルルーティング。
- version 1の委譲packetと、起動前・終了後のGit scope検査。
- 一時`CODEX_HOME`で動くguarded Luna launcher。
- 大きなread-heavy diff向けの任意のTerra reviewer。
- 診断、検証、TDD、問題設定、契約・architecture・domain・interface分析を扱う10個のSkill。
- content-freeな運用event store、CLI、read-only WebUI。
- ルーティングとレビュー品質を検証する隔離eval harness。
- plan/apply/verify/uninstall型のbootstrap。

このハーネスは、workerの成功報告をそのまま採用しません。resident Codexがactual diff、scope、非目標、edge case、compatibility、test evidenceを独立に確認し、最終報告を所有します。

## 想定する運用

既定profileは、個人開発者が自分のLinux環境へ導入するsingle-user構成です。公開配布されるsourceであっても、各installのtrust boundaryは独立しています。multi-user service、enterprise RBAC、Internet-facing deploymentは既定scopeではありません。

各projectでは、必要に応じてproject rootのローカル`AGENTS.md`へ小さな`Operating context`を置き、実際の利用者、規模、trust boundary、failure riskに合わせて設計・reviewの厳しさを調整できます。profileがないこと自体はエラーではありません。

automation safetyは規模にかかわらず維持します。workerのscope、既存差分、commit・push権限、actual diff、fresh verificationは常に確認対象です。

## Responsibility boundaries

- ユーザーはproduct direction、goal scope、不可逆・外部影響を伴う判断を所有します。
- resident Codexはscope、委譲判断、actual diff review、verification、最終報告を所有します。
- Lunaは、acceptance criteriaと変更範囲が確定したbounded implementationだけを実行します。
- Terra reviewerは任意のread-only advisory passであり、acceptance ownerにはなりません。
- Skillとモデルルーティングは権限を付与しません。commit、push、release、外部状態変更には別の認可が必要です。

## Requirements

- Python 3.10以降。サードパーティPython packageは不要です。
- Bash、Git、およびCodex CLI。
- local marketplaceと`plugin add` / `plugin remove`を利用できるCodex CLI。
- 既存のCodex login、またはCodexが受け付けるAPI認証情報。

認証情報はrepositoryへコピー・生成されません。

## Quick start

```bash
git clone <repository-url> ~/codex-exosphere
cd ~/codex-exosphere

# planを表示するだけ。書き込みはしない
python3 bootstrap/install.py

# 適用する
python3 bootstrap/install.py --apply

python3 bootstrap/verify.py
```

インストールはこれで完了です。設定ファイルは必要ありません。

installを2段階に分けているのは意図的です。1回目は何をするかを表示するだけで、2回目は
上書きせずに停止するため、すべてのdestinationがmissingか既に同一である必要があります。

### Optional: Codexの`config.toml`を生成する

`--local-config`を渡すと、installerが`config.toml`も生成します。

```bash
cp config/local.example.toml config/local.toml
$EDITOR config/local.toml
python3 bootstrap/install.py --local-config config/local.toml --apply
```

`config/local.toml`は追跡対象外です。対応するtop-level keyは次の3個だけです。

```toml
network_access = true
trusted_projects = ["~/codex-exosphere"]
writable_roots = ["~/codex-exosphere"]
```

pathは絶対pathまたは`~/`で始めます。rendererは未知keyを拒否します。

### Optional: インストール済みpluginを検証する

`verify.py --installed`はeffective plugin selectionも検査し、これをCodex CLI経由で
読み取ります。そのため上のコマンドと違い、動作するCLIとインストール済みpluginが必要です。

```bash
python3 bootstrap/verify.py --installed
```

## Luna delegation

write-capableな委譲は、guarded launcherを通します。

```bash
~/.codex/bin/run-luna-worker \
  --cd /path/to/git-worktree \
  --packet-file /tmp/luna-packet.json \
  --output /tmp/luna-result.md \
  --metrics /tmp/luna-metrics.json
```

launcherは次を行います。

1. version 1 packetのshape、size、path、authorizationを起動前に検査する。
2. 既存dirty stateとHEADを記録する。
3. 一時`CODEX_HOME`へ実装用Skillだけを公開する。
4. Luna実行後にHEAD、変更path、mode、symlinkを検査する。
5. raw JSONLとstderrを一時領域へ隔離し、bounded resultとcontent-free metricsだけを返す。
6. 違反時は証拠を自動revertせず、fail closedにする。

packet schemaとstop conditionは[`docs/luna-delegation-contract.md`](docs/luna-delegation-contract.md)を参照してください。launcherはworkerのdiffをacceptしません。resident Codexのreview gateは別工程です。

## Optional Terra review

`terra_reviewer`は、大きいがboundedなdiff、regression scan、長いchecklistのread-heavy reviewに限って試せます。通常の小変更へ必須化せず、resident Codexのreview gateを置き換えません。live runtimeがread-onlyを保証しているかは実行時に確認してください。

## Codex Observatory

Codex Observatoryは、prompt、message、diff、source text、command、path、transcript、credentialを受け付けないevent schemaで、task、委譲、review、Skill、token、scopeの観測事実だけを保存します。

```bash
codex-observe emit --file /tmp/event.json
codex-observe import-luna \
  --metrics /tmp/luna-metrics.json \
  --task-id task-001 --run-id run-001 --event-id event-001 \
  --occurred-at 2026-07-16T12:00:00Z --task-kind implementation
codex-observe summary
codex-observe tasks --limit 20
codex-observe serve
```

既定DBは`$XDG_STATE_HOME/codex-observability/events.sqlite3`、未設定時は`$HOME/.local/state/codex-observability/events.sqlite3`です。WebUIはread-onlyで、APIにはprocessごとのephemeral bearerを要求します。詳しいcontractは[`docs/observability-foundation-design.md`](docs/observability-foundation-design.md)にあります。

## Evaluation

offline commandはmodelを呼びません。

```bash
python3 evals/run.py list
python3 evals/run.py validate
python3 evals/run.py plan
```

model callは明示した`live --case CASE_ID`だけが行います。評価設計は[`docs/skill-routing-eval-design.md`](docs/skill-routing-eval-design.md)、初回baselineは[`docs/skill-routing-eval-baseline-2026-07-16.md`](docs/skill-routing-eval-baseline-2026-07-16.md)を参照してください。

## Managed paths

| Versioned source | Default deployment |
| --- | --- |
| `config/AGENTS.md` | `$CODEX_HOME/AGENTS.md` |
| `agents/luna_worker.toml` | `$CODEX_HOME/agents/luna_worker.toml` |
| `agents/terra_reviewer.toml` | `$CODEX_HOME/agents/terra_reviewer.toml` |
| `bin/run-luna-worker` | `$CODEX_HOME/bin/run-luna-worker` |
| `bin/luna-packet-guard` | `$CODEX_HOME/bin/luna-packet-guard` |
| `bin/codex-observe` | `$CODEX_HOME/bin/codex-observe` |
| `bin/codex-observe-shim` | `$HOME/.local/bin/codex-observe` |
| `codex_observability` | `$CODEX_HOME/lib/codex_observability` |
| `plugins/resident-engineering-patterns` | `$HOME/plugins/resident-engineering-patterns` |
| `config/config.base.toml` + `config/local.toml` | `$CODEX_HOME/config.toml` |

installerは所有情報とdigestを`~/.local/state/codex-exosphere/install-state.json`へ保存します。既存の異なるファイルを上書きせず、uninstallもinstallerが作成し、その後変更されていないartifactだけを削除します。

## Verify and uninstall

```bash
python3 bootstrap/verify.py
python3 bootstrap/verify.py --installed
python3 -m unittest discover -s tests -v

# uninstallも既定はplan only
python3 bootstrap/uninstall.py
python3 bootstrap/uninstall.py --apply
```

`CONFLICT`はforce-overwriteの合図ではありません。repository版とdeployment版を確認して、意図したsourceを手動で選んでください。

## Repository layout

```text
agents/       custom agent definitions
bin/          guarded launchers and CLI shims
bootstrap/    renderer, installer, verifier, uninstaller
codex_observability/  content-free event model, store, CLI, WebUI
config/       portable defaults and host-local example
docs/         contracts, decisions, and evaluation notes
evals/        isolated routing and review evaluation
plugins/      resident engineering Skill source
tests/        isolated contract and bootstrap tests
```

## Safety boundary

次をrepositoryへ追加しないでください。

- `auth.json`、API key、OAuth token、`.env`、private key。
- Codex session JSONL、runtime log、cache、plugin cache。
- memory database、message database、backup、queue data。
- home directory全体のsnapshot。

この境界はhostile multi-user環境を前提にするものではありません。認証情報とruntime stateをportable sourceから分離し、automationの誤動作から既存作業を守るための境界です。

## Verified scope and limitations

install、verification、uninstallの各経路は2026-08-08に、`HOME`・`CODEX_HOME`・
`XDG_STATE_HOME`をtemporary directoryへ差し替えた使い捨てのLinux環境で、end to endに
実行しました。planとapplyの両phase、repository verificationとinstalled verification、
既存のCodex CLIを用いたplugin addとremove、uninstall、66件のtest suite全体が対象です。
併せて、抽出元マシンに紐づくabsolute path・symlink・親ディレクトリへのtraversalを走査し、
該当する依存は検出されませんでした。

次は未検証です。

- 別の物理マシンまたはcontainer、および実行に用いたもの以外のLinux distribution。
- Codex CLIの新規インストール。実行時はインストール済みの`codex-cli 0.147.0`を使用しました。
- 新規のCodex loginのprovisioning、および認証を伴うmodel実行。
- インストール後のLuna・Terra・Solの実際のmodel呼び出し。
- official plugin validator。test環境に存在せず、repository verificationとinstalled
  verificationの双方で`SKIP`となりました。
- macOS、Windows、および将来のCodex CLIとの互換性。

次の2点は欠陥ではなく意図した挙動です。

- `uninstall.py`はmanaged file、marketplace entry、install state、インストール済みpluginを
  削除しますが、`.codex/agents`や`.codex/bin`のような空の親ディレクトリは残します。これらは
  Codex CLI側のディレクトリであり、削除すると本プロジェクトの管理外のインストールを
  壊すおそれがあるためです。
- `verify.py --installed`はCodex CLIを必要とします。effective plugin selectionを検査する
  ためです。repository verificationとinstall payload自体はCodex CLIを必要としません。

## License

本体は[MIT License](LICENSE)で提供します。第三者由来の影響と表示は[`plugins/resident-engineering-patterns/THIRD_PARTY_NOTICES.md`](plugins/resident-engineering-patterns/THIRD_PARTY_NOTICES.md)を参照してください。
