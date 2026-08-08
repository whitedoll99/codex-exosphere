# Responsibility boundaries

## 誰が何を所有するか

- ユーザーはproduct direction、goal scope、不可逆・外部影響を伴う判断を所有します。
- resident Codex（Sol）はscope、委譲判断、actual diff review、verification、最終報告を
  所有します。
- Lunaは、acceptance criteriaと変更範囲が確定したbounded implementationだけを実行します。
- Terra reviewerは任意のread-only advisory passであり、acceptance ownerにはなりません。

## routingは権限を与えない

Skillとmodel routingは権限を付与しません。commit、push、release、deployment、その他の
外部状態変更には、通常どおり別の認可が必要です。

「Lunaへ委譲できる」ことは「Lunaがcommitしてよい」ことを意味しません。委譲packetは
commitとpushを禁止し、launcherは実行の前後でGitの状態を比較してこれを検出します。

## sandboxの実効範囲

`luna_worker`と`terra_reviewer`では、read-onlyに関する事情が異なります。**同じ注意書き
としてまとめないでください。**

### native `luna_worker`

custom agent定義に`sandbox_mode`を**設定していません**。native subagentは親runtimeの
sandbox policyを継承します。

したがってnative `luna_worker`は、read-onlyのexploration、evidence gathering、review
supportにのみ使用してください。これは運用上の役割制限であり、独立したwrite barrierでは
ありません。親runtimeがread-onlyであることを確認できる場合にのみ使い、そうでなければ
作業をresident側に保持します。

**write権限を伴うLuna委譲は、native subagentではなくguarded launcher
（`bin/run-luna-worker`）を経由します。**

### `terra_reviewer`

custom agent定義は`sandbox_mode = "read-only"`を**要求しています**。加えてdeveloper
instructionsで、file変更、mutating command、commit、push、publish、外部メッセージ送信、
subagent起動を禁止しています。

ただし親turnのlive runtime overrideがcustom-agent defaultを上回る場合があります。
**現在のruntimeがその境界を確認できない限り、Terra reviewを「mechanically read-only」と
記述しないでください。** runtimeの能力にかかわらず、reviewerはfileの編集、commit、push、
publish、外部メッセージ送信、product / architecture判断を認可されていません。

## 運用profile

既定profileは、個人開発者が自分のLinux環境へ導入するsingle-user構成です。公開配布される
sourceであっても、各installのtrust boundaryは独立しています。multi-user service、
enterprise RBAC、Internet-facing deploymentは既定scopeではありません。

各projectでは、必要に応じてproject rootのローカル`AGENTS.md`へ小さな`Operating context`を
置き、実際の利用者、規模、trust boundary、failure riskに合わせて設計・reviewの厳しさを
調整できます。profileがないこと自体はエラーではありません。

automation safetyは規模にかかわらず維持します。workerのscope、既存差分、commit・push
権限、actual diff、fresh verificationは常に確認対象です。

## repositoryへ入れないもの

- `auth.json`、API key、OAuth token、`.env`、private key。
- Codex session JSONL、runtime log、cache、plugin cache。
- memory database、message database、backup、queue data。
- home directory全体のsnapshot。

この境界はhostile multi-user環境を前提にするものではありません。認証情報とruntime stateを
portable sourceから分離し、automationの誤動作から既存作業を守るための境界です。

## 関連

- [`luna-delegation-contract.md`](luna-delegation-contract.md) — packet schemaとGit scope guard
- [Managed paths](managed-paths.md) — installerが書き込む先
