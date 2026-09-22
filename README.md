# codex-exosphere

**SolをOrchestrator、AstraをOracle、LunaをWorkerとして使い分けるCodex CLI向け開発ハーネスです。**

Solは通常の対話・調査・判断・最終レビューを所有します。難しい問題設定や競合する因果説明は、変更を行わない助言役として運用するAstra Oracleへ限定して問い、仕様と変更範囲が固まった実装はLunaへ委譲します。Oracleの助言とLunaの変更は、どちらもSolが現物に照らして検証します。Astraのagent定義は`read-only` sandboxを要求しますが、親runtimeのoverrideが優先される場合があるため、これは機械的なwrite barrierの保証ではありません。runtimeの実効権限にかかわらず、Oracleには変更・commit・push・publishなどを行う権限を与えません。

さらに、問題整理・デバッグ・TDD・設計分析・レビュー・検証などの開発Skillを同梱。
単にモデルを振り分けるだけでなく、**判断・助言・実装の各工程の品質を底上げする開発環境**を目指しています。

[English](README_en.md)

---

## 何がうれしいのか

### 1. 低コストなLunaを実装workerとして使える

GPT-6 Solは強力ですが、すべてのコーディングをSol自身に行わせる必要はありません。

codex-exosphereでは、Solが問題を理解して作業を整理したあと、判断の余地が少ない実装単位をGPT-6 Lunaへ委譲できます。現在のCodex価格体系ではLunaはSolより低コストです（[Codex rate card](https://help.openai.com/en/articles/20001106-codex-rate-card)）。

```mermaid
flowchart TD
    U["User"] --> S1["GPT-6 Sol<br/>要件整理・調査・設計・作業分割"]
    S1 -->|"難しい限定判断"| A["GPT-6 Astra<br/>advisory Oracle"]
    A -->|"根拠・反証・成立条件"| S1
    S1 -->|"実装可能な単位"| L["GPT-6 Luna<br/>実装・テスト"]
    L --> S2["GPT-6 Sol<br/>diff・テスト結果を最終レビュー"]
```

ユーザーがAstraやLunaを直接操作する必要はありません。
通常どおりSolへ作業を依頼すれば、相談や委譲を行うかどうかも含めてSolが判断します。

### 2. 各役割の開発作業そのものを改善する

codex-exosphereには、ソフトウェア開発向けのSkillセットが含まれています。

たとえば、

* 問題が曖昧なら、いきなり実装せず整理する（`problem-framing`）
* 原因不明の不具合なら、推測で修正せず証拠から原因を絞る（`systematic-diagnosis`）
* 明確な局所変更なら、focused testを使って実装する（`bounded-tdd`）
* 「できました」という自己申告ではなく、実際のdiffとfreshな検証結果を見る（`verification-before-reporting`）

といった開発パターンをCodexに与えます。全10種類の一覧は[Engineering Skills](#engineering-skills)にあります。

Skillはタスクに応じて暗黙的に選択されるため、通常はユーザーがSkill名を指定する必要はありません。

### 3. Lunaへ任せても野放しにしない

Lunaは単なる別プロセスとして自由に実装するわけではありません。

Solが委譲する作業には、何を実装するか、何をもって完了とするか、変更してよい範囲、変更してはいけないもの、必要な検証、判断が必要になったら止まる条件が与えられます。

さらにworker実行の前後でGitの状態を比較し、指定外の変更やcommitなどを検出します。

Luna自身が「成功した」と報告しても、それだけでは完了になりません。

**実際のdiffと検証結果をSolが確認してから、ユーザーへ最終結果を報告します。**

---

## Quick Start

### Requirements

主な対象環境はLinuxです。

必要なもの:

* Python 3.10+
* Bash
* Git
* Codex CLI
* Codex CLIを利用できる認証環境

追加のPythonパッケージは必要ありません。

### Install

```bash
git clone https://github.com/whitedoll99/codex-exosphere.git ~/codex-exosphere
cd ~/codex-exosphere
```

まず、何がインストールされるか確認します。

```bash
python3 bootstrap/install.py
```

この段階では変更は行われません。

問題がなければ適用します。

```bash
python3 bootstrap/install.py --apply
```

最後に検証します。

```bash
python3 bootstrap/verify.py
```

これで基本的なセットアップは完了です。

インストールは`$CODEX_HOME`、`$HOME/.local/bin`、`$HOME/plugins`配下へファイルを書き込みます。正確な対応は[Managed paths](docs/managed-paths.md)を参照してください。

既存の`$CODEX_HOME/AGENTS.md`は上書きも自動mergeもされません。planが`CONFLICT`を表示した場合は`--apply`へ進まず、[既存Codex環境への導入](docs/install-existing-environment.md)に従ってください。

### Use

作業したいGitリポジトリで、普通にCodexを起動します。

```bash
cd /path/to/your-project
codex
```

あとは普段どおり依頼してください。

```text
設定画面で保存ボタンを押しても変更が反映されません。
原因を調べて修正し、関連するテストも実行してください。
```

ユーザーが、

* Lunaを起動する
* 委譲packetを書く
* Skillを選ぶ
* launcherを直接操作する

必要は通常ありません。

Solがタスクを整理し、必要に応じてSkillを使い、Lunaへ委譲できる作業かどうかを判断します。

---

## How it works

codex-exosphereでは、モデルを単純な上下関係ではなく、役割によって使い分けます。

| Model           | Role |
| --------------- | ---- |
| **GPT-6 Sol** | Orchestrator: 問題理解、調査、設計、委譲、判断、最終レビュー |
| **GPT-6 Astra** | Oracle: 難しい問題設定、競合する因果説明、複数契約にまたがる判断への変更を伴わない助言 |
| **GPT-6 Luna** | Worker: 仕様と範囲が明確になった実装 |

基本的な考え方はシンプルです。

> **Use Sol for judgment.**<br>
> **Use Astra for bounded advice.**<br>
> **Use Luna for implementation.**<br>
> **Let Sol verify the result.**

### Solが担当する仕事

たとえば次のような仕事はSolが保持します。

* 要求がまだ曖昧
* 原因不明の障害調査
* アーキテクチャ判断
* public API / CLIの設計
* schemaやmigration
* 互換性判断
* security / privacyに関わる変更
* 複数componentにまたがる大きな作業

### Astraへ相談する判断

Solは、現物調査後も問題設定自体が疑わしい場合、因果説明が競合する場合、または複数の契約にまたがる設計判断を局所的に解けない場合に限り、Astra Oracleへ一つの限定された問いを渡します。

Oracleは根拠、反証、成立条件、最小の次の確認を返す助言役です。実装、承認、commit、pushは行いません。`sandbox_mode = "read-only"`はagent側の要求であり、親runtime overrideがそれを上回る場合があります。そのためread-onlyはOracleの運用契約として扱い、実効sandboxを確認できない限り機械的なwrite barrierとはみなしません。情報が足りないだけならSolが先に調査し、ユーザーの選好や権限判断をOracleへ委譲しません。

### Lunaへ渡す仕事

Lunaに適しているのは、たとえば次のような作業です。

* 再現済みの局所バグ修正
* 既存パターンに沿った実装
* focused testで確認できる変更
* 変更範囲を明確に限定できる作業

途中で設計判断やscope拡張が必要になった場合、Lunaは勝手に決めずSolへ戻します。

### 委譲の流れ

```mermaid
flowchart TD
    S["GPT-6 Sol<br/>Orchestrator"] -->|"difficult bounded question"| A["GPT-6 Astra<br/>Oracle"]
    A -->|"evidence and advice"| S
    S -->|"bounded task"| P["委譲packet"]
    P --> G1["Luna launcher<br/>preflight check"]
    G1 --> L["GPT-6 Luna"]
    L --> G2["Git scope check"]
    G2 --> R["GPT-6 Sol<br/>diff / test review"]
```

packetの仕様、preflight / postflightの検査内容、手動でpacketを扱う方法は[Luna delegation contract](docs/luna-delegation-contract.md)にあります。

### 権限について

model routingは権限を与えません。commit、push、release、deploymentなどの外部影響を伴う変更には、通常どおり別の認可が必要です。詳細は[Responsibility boundaries](docs/responsibility-boundaries.md)を参照してください。

---

## Why an external Luna worker?

2026-08-08時点のCodexでは、LunaはMulti-Agent V1として登録されており、V2のnative subagentとして直接spawnできません（[openai/codex#34700](https://github.com/openai/codex/issues/34700)）。

codex-exosphereはこの制約のもとで、Lunaを独立したephemeral Codex processとして実行し、Sol側の管理下へ組み込みます。これは製品の本質ではなく、現時点でこの実装方式を採っている理由です。

概念的には次のようになります。

```mermaid
flowchart TD
    S["GPT-6 Sol"] -->|"guarded delegation"| W["run-luna-worker"]
    W --> H["temporary CODEX_HOME"]
    H --> E["codex exec<br/>--model gpt-6-luna"]
    E --> L["GPT-6 Luna"]
```

ただし、単に別のCodex CLIを起動しているだけではありません。

Luna用の環境には、

* 必要な実装Skillだけをロード
* task scopeを明示
* Git状態を事前確認
* 変更可能範囲を検査
* 実行結果をSolへ返却

する仕組みが追加されています。

---

## Engineering Skills

Skillは単なるプロンプト例ではなく、Codexが特定の種類の問題に遭遇したときに使う開発workflowです。

### Included Skills

| Skill                           | 主な用途             |
| ------------------------------- | ---------------- |
| `problem-framing`               | 曖昧な要求を実装可能な問題へ整理 |
| `systematic-diagnosis`          | 不具合を証拠ベースで診断     |
| `bounded-tdd`                   | 明確な局所変更をTDDで実装   |
| `contract-design`               | API・CLIなどの契約設計   |
| `architecture-quality-analysis` | アーキテクチャ案の比較      |
| `domain-model-audit`            | ドメインモデルの検査       |
| `interface-boundary-audit`      | インターフェース境界の検査    |
| `review-feedback-triage`        | レビュー指摘の妥当性確認     |
| `review-packet-preparation`     | 独立レビュー用の情報整理     |
| `verification-before-reporting` | 完了報告前の最終検証       |

Solは状況に応じてこれらを使います。
Lunaにはこのうち実装に必要なSkillだけを与え、設計や最終判断はSol側に残します。

### 動き方の例

原因不明の障害では `systematic-diagnosis` が、

```text
症状
 ↓
最小再現
 ↓
境界ごとの証拠確認
 ↓
仮説
 ↓
反証可能な検査
 ↓
root cause
```

という流れを促します。

明確な実装では `bounded-tdd` が、

```text
failing test
    ↓
minimum implementation
    ↓
passing test
    ↓
broader verification
```

という作業を促します。

完了時には `verification-before-reporting` が、古いテスト結果やworkerの自己申告ではなく、現在のdiffとfreshな検証証拠を確認します。

Skill routing自体もevaluation harnessで検証できます。設計は[Skill routing eval design](docs/skill-routing-eval-design.md)、初回baselineは[2026-07-16 baseline](docs/skill-routing-eval-baseline-2026-07-16.md)にあります。

---

## Observatory

Codex Observatoryは、codex-exosphereの実行状況を確認するための軽量なobservability機能です。

タスク、委譲、レビュー、Skill利用、usageなどの運用イベントを確認できます。

一方で、

* prompt
* source code
* diff
* credential

などの内容そのものは保存しません。

```bash
codex-observe summary
codex-observe tasks --limit 20
codex-observe serve
```

詳細は[Observability foundation design](docs/observability-foundation-design.md)を参照してください。

---

## Evaluation

モデルやSkillのルーティングが「設定上そうなっている」だけではなく、実際に期待どおり動くか確認するためのeval harnessを含んでいます。

通常の確認ではモデルを呼びません。

```bash
python3 evals/run.py list
python3 evals/run.py validate
python3 evals/run.py plan --case routing-local-bug
```

明示的にlive evaluationを実行することもできます。

```bash
python3 evals/run.py live \
  --case routing-local-bug \
  --output /tmp/codex-eval-routing-local-bug
```

routing、Skill選択、Lunaのscope判断、Solのdiff reviewなどを観測できます。

---

## Verify / Uninstall

インストール状態の確認:

```bash
python3 bootstrap/verify.py
```

uninstall plan:

```bash
python3 bootstrap/uninstall.py
```

実際に削除:

```bash
python3 bootstrap/uninstall.py --apply
```

installer管理外のファイルを無条件に削除することはありません。

---

## Documentation

READMEでは通常利用に必要な概要だけを扱います。

内部contract、設計判断、評価方法、実測結果などは `docs/` にあります。

* [Luna delegation contract](docs/luna-delegation-contract.md) — 委譲packet、Git scope guard、手動操作
* [Luna launcher troubleshooting](docs/luna-launcher-troubleshooting.md) — 通信制限、許可ルール、app-server再起動の切り分け
* [Luna worker efficiency design](docs/luna-worker-efficiency-design.md) — Luna work-unitとcontext効率
* [Skill routing eval design](docs/skill-routing-eval-design.md) — Skill / model routing評価
* [Observability foundation design](docs/observability-foundation-design.md) — Observatory設計
* [Managed paths](docs/managed-paths.md) — installerが書き込む先の一覧
* [既存Codex環境への導入](docs/install-existing-environment.md) — `CONFLICT`の扱い
* [Responsibility boundaries](docs/responsibility-boundaries.md) — 責任境界、権限、sandboxの実効範囲
* [Verified scope and limitations](docs/verified-scope.md) — 検証済み範囲と未検証事項

---

## Repository layout

```text
agents/                 Astra Oracle / Luna Worker agent definitions
bin/                    Luna launcher and command shims
bootstrap/              install / verify / uninstall
codex_observability/    Observatory
config/                 Codex configuration
docs/                   contracts, designs and baselines
evals/                  Skill / model routing evaluation
plugins/                engineering Skills
tests/                  tests
```

---

## Current status

codex-exosphereは現在、**個人のLinux開発環境**を主な対象としています。

bootstrap、install、verification、uninstallの各経路は、隔離したLinux環境でend to endに検証済みです。一方で、**公開版を新規インストールした直後の、認証を伴うSol / Astra / Lunaの実model実行はまだ検証していません。**

macOS / Windowsは現時点では主要な検証対象ではありません。Codex CLIやモデル側の仕様変更によって挙動が変わる可能性があります。

検証済み範囲と未検証事項の詳細は[Verified scope and limitations](docs/verified-scope.md)にあります。

---

## License

MIT License
