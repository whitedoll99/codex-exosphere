# Codex collaborator availability and standalone operating modes

Status: Codex-side design draft。実装済みの運用mode、既存governanceの上書き、または
外部collaboration protocolの一般仕様を変更するものではない。

Decision owner: user。host-neutral protocolへ一般化する際のownerは別途決める。

## 1. 目的

通常はCodexと独立したarchitect／reviewerが協働する。相手agentがquota、process、transport、
session、その他のavailability理由で利用不能な場合も、Codexが安全な範囲の作業を継続できる
正式なfallbackを定義する。

fallbackはavailabilityを改善するが、権限や検収品質を自動的に引き上げない。

```text
collaborator unavailable
  -> assurance level decreases
  -> allowed task class narrows
  -> evidence and deferred-review duties increase
  != authority expands
```

## 2. Scope

本書が定義するのはresident Codex側の以下の振る舞いである。

- collaborative modeからsingle-agent fallbackへの進入判断。
- fallback中にCodexが継続できる作業と停止すべき判断。
- 自己検証と独立検収を混同しないreport semantics。
- collaborator復帰後のreconciliation packetと遡及review。
- handoff、knowledge index、repository artifactによる継続性。

以下は対象外とする。

- 外部agent側の実装、hook、skill、memory、session管理。
- host-neutral normative protocolの確定。
- user authority、repository governance、commit／push／release policyの変更。
- unavailable agentの人格、判断、承認をCodexが代行したと主張すること。
- independent reviewをmodelの自己批判promptだけで代替したと主張すること。

## 3. Actors and authority

### User

- goal、fallback利用、例外的なscope、外部actionの最終authorityを持つ。
- repository governanceが特定collaboratorの承認を要求する場合、そのgateを明示的に維持、
  一時上書き、または解除する。

### Resident Codex

- availabilityとauthorityを分けて評価する。
- fallback中の調査、bounded implementation、自己review、verification、handoffを担う。
- 独立review未実施の範囲を隠さず、最終reportに残す。

### Worker

- Luna等のworkerは、既存routing条件を満たすbounded implementation unitだけを実行できる。
- worker利用はmulti-agent collaborative reviewの代替ではない。resident Codexが引き続き
  actual diffとverificationをreviewする。

### Unavailable collaborator

- 不在中に新しいauthority、decision、verdictを発したものとして扱わない。
- 過去のspecやdecision artifactは、identity、revision、freshnessを再検証できる場合だけ入力に使う。

## 4. Mode state machine

### 4.1 States

`collaborative`
: 必要なarchitect／reviewerが利用可能。通常の役割分離と独立検収を適用する。

`fallback_read_only`
: collaborator不在を観測したが、mutable workの追加authorityはない。Codexは現物調査、
  status確認、再現、診断、packet準備を行える。

`fallback_authorized`
: userまたは既存の明示的task contractが、collaborator不在中のbounded mutable scopeを承認した。
  Codexは§6の範囲だけを実装できる。

`reconciliation_required`
: fallback中にmutable成果物が作られ、独立reviewが未実施。作業は保存されるが、
  `independently_accepted`とは表示できない。

### 4.2 Transitions

```text
collaborative
  -- collaborator unavailable --> fallback_read_only

fallback_read_only
  -- explicit bounded authority --> fallback_authorized
  -- collaborator returns ------> collaborative

fallback_authorized
  -- mutable unit completed ----> reconciliation_required
  -- scope/authority ambiguity --> fallback_read_only or stop

reconciliation_required
  -- independent review accepted --> collaborative
  -- findings require fixes -------> authorized fix round
  -- reviewer remains unavailable -> remain reconciliation_required
```

availabilityの変化だけで`fallback_authorized`へ遷移してはならない。read-only作業であっても
secret egress、cost、availability、privacyへ影響する場合は通常のauthority確認を要する。

## 5. Entry contract

Codexはfallback進入時に少なくとも次をcontent-bounded artifactまたはfinal reportへ記録する。

- modeと進入時刻。
- unavailableなrole／agent。
- availability根拠とその`observed_at`。
- 適用するuser指示、task spec、repository governanceのpointer。
- 許可されたscopeと明示的non-goal。
- commit、push、release、deploy、daemon、external writeのauthority状態。
- 独立reviewが欠けることで低下するassurance。
- reconciliation ownerと未処理状態。

この記録がcollaboratorのreview、approval、decision待ちを発生させる場合、handoffやartifactへの
記録だけをdeliveryとみなさない。待ちの発生時に設定済みtransportでも対象collaboratorへ1通送り、先頭行で
対象workと待ち種別を識別できるようにする。相手が不在でも送信を済ませ、未読配送を復帰後の
reconciliation入力にする。

quotaやprocess状態はvolatile claimである。rehydrate時に再確認できなければ、現在の事実ではなく
historical observationとして表示する。

## 6. Allowed work in `fallback_authorized`

fallbackへの進入だけでは実装権限を生まない。明示的に承認されたscope内で、次の条件をすべて
満たすwork unitを標準的な許可候補とする。

- 要求とobservable acceptance criteriaが確定している。
- local、bounded、independently reviewableな一単位である。
- 既存patternから実装がほぼ一意に導ける。
- rollback可能、または差分を未commitで安全に保持できる。
- focused testまたは同等の具体的verificationがある。
- unrelated dirty stateを列挙・保全できる。
- 新しいproduct policy、identity、ownership、compatibility判断を必要としない。

典型例:

- 明確な回帰testを伴う局所bug fix。
- 既存contractに忠実なvalidation強化。
- documentation clarificationとsource pointer追加。
- read-only診断、review packet、handoff、knowledge-index更新。

## 7. Mandatory stop or separate user decision

次の事項はfallback entryのauthorityだけでは開始しない。既存specで決定済みでない場合、
別の明示的user decisionを要求する。

- public API／CLI、schema、migration、persistence、default、backward compatibility変更。
- authentication、authorization、credential、privacy、retention、forget、data-loss semantics。
- profile identity、host handoff、memory merge、主体境界。
- 新規dependency、network service、license、recurring cost。
- destructive operation、release、publish、deploy、push、外部状態変更。
- core product policyまたはadapter boundary変更。
- goal scope拡張、acceptance criteria緩和、test skip、verification省略。
- 独立reviewなしでは評価不能なsecurity、concurrency、production failure。

userが個別に許可した場合も、独立reviewが行われたことにはならない。成果物は
`reconciliation_required`のまま保持する。

## 8. Execution and self-review contract

Codexは各mutable unitで次を行う。

1. authorization、allowed paths、existing dirty paths、non-goalsを固定する。
2. 可能ならred-green-refactorでobservable behaviorを固定する。
3. workerを使う場合はbounded packet、commit=false、push=falseとする。
4. actual working-tree diffをresident Codex自身が読む。
5. correctness、edge case、compatibility、privacy、unrelated changeを確認する。
6. focused verification後、riskに比例したbroader verificationを行う。
7. result packet、handoff、必要ならknowledge indexへpointerを保存する。

同じCodex session内の自己review、fresh-context自己review、worker reviewはいずれも有用だが、
外部roleによるindependent reviewとは表記しない。

## 9. Result semantics

fallback中の成果物は次のstatusを区別する。

`verified_by_codex`
: Codexがactual diffとfresh verificationを確認した。

`independent_review_pending`
: 外部architect／reviewerの検収が未実施。

`independently_accepted`
: collaborator復帰後、独立に現物とgateを再取得してacceptした。

`blocked`
: authority、scope、safety、verificationのいずれかを満たせず停止した。

`verified_by_codex`を`independently_accepted`、`fully accepted`、`pair approved`などと
言い換えてはならない。

最終reportは少なくとも、実装scope、verification、未検収範囲、既存変更、external action状態、
reconciliationの次actionを含む。

## 10. Reconciliation

collaborator復帰後は、会話要約ではなく保存artifactからreviewを開始する。

1. fallback mode record、user authority、task revisionを確認する。
2. handoffやartifactに記録されたreview、approval、decision待ちに対応するtransport配送を確認し、
   未送信ならreconciliation開始時に送る。
3. handoff digest、Git HEAD、branch、dirty inventory／fingerprintを検証する。
4. reviewerがactual diffと必要なverificationを独立に再取得する。
5. scope、correctness、compatibility、non-interference、test coverageを判定する。
6. accept、bounded fix request、user escalationのいずれかを記録する。
7. 全対象unitが処理された場合だけcollaborativeへ戻す。

reviewer不在中に複数unitを進めた場合、各unitのauthorityとevidenceを混ぜず、review可能な順序を
保持する。復帰したreviewerへ巨大な無境界diffを渡さない。

## 11. Failure semantics

- collaborator状態が不明: `fallback_read_only`。不在を断定しない。
- user authorityが曖昧: affected mutable sliceを停止する。
- verification不能: successへ昇格せず、partial／blockedとして保存する。
- scope drift: 新しいunitを開始せずdecision packetを返す。
- handoff／index不正: 自動修復せずfail closed。
- worker失敗: reviewable diffがあればCodexが検査し、なければ直接fallback可否を再判断する。
- collaborator復帰: 自動acceptせずreconciliationを開始する。

## 12. Privacy and retention

mode、evidence、handoff、indexにはraw transcript、prompt、response、memory本文、token、credential、
environment dumpを保存しない。保存対象はbounded status、timestamp、relative path、digest、count、
authority pointer、verification結果とする。

repository artifactはrepository policyに従う。machine-local handoffとknowledge indexは、
それぞれに設定されたprivacy、digest、freshness contractに従う。fallbackはmemory publicationを
暗黙に許可しない。

## 13. Compatibility

本書はdocumentation-only draftであり、現行`AGENTS.md`、repository governance、Luna packet、
plugin、hook、CLIの挙動を変更しない。実装時はmode artifactのversioningと、modeを知らない旧環境が
通常のauthority checkへfail closedする互換方針を別specで定める。

外部coordination protocolが将来host-neutralなmode semanticsを確定した場合、本書はそのCodex adapterへ
縮小する。競合時はuser-approved protocolとrepository governanceを優先する。

## 14. Proposed verification scenarios

実装roundでは少なくとも次をfixture化する。

1. collaborator利用可能時は`collaborative`を維持する。
2. quota claimだけではmutable fallbackへ入らない。
3. unavailable + user bounded authorityでlocal testable changeを許可する。
4. fallback entryだけでpush、schema変更、test skipを許可しない。
5. Codex verification済みでも`independently_accepted`を出さない。
6. session loss後にhandoffとmode recordから再構築できる。
7. collaborator復帰後、独立再取得なしにreconciliationを完了しない。
8. stale availability claimをcurrent factとして扱わない。
9. raw transcript、secret、memory本文がartifactへ混入しない。
10. unresolved review unitがある間は通常mode復帰を完了扱いにしない。

## 15. Open decisions before implementation

- mode recordをrepository artifact、resident local state、または両方のpointer構成のどこに置くか。
- `fallback_read_only`へ自動進入できるavailability evidenceの最小条件。
- 未検収unit数や経過時間に上限を設け、追加mutable workを止めるか。
- collaboratorが長期不在の場合、別のindependent reviewerを割り当てる契約。
- reconciliation完了を誰が記録し、どのartifactを正本とするか。
- host-neutral mode contractとCodex adapterのversion関係。

これらの決定前にruntime enforcementやdefault mode変更を開始しない。

## 16. 一時欠損と恒久的な単独運用を分ける

collaboratorの不在には、性質の異なる二つの場合がある。

### 16.1 一時的な欠損

quota、障害、transport、session等によって、通常のexternal manager／reviewerが一時的に
利用できない状態である。これは通常体制のdegraded operationであり、availability低下だけを
理由にauthorityをresident Codexへ自動移譲しない。

- 既承認spec内の独立作業は、既存authorityと§6の条件を満たす範囲で継続できる。
- collaborator固有のdecision、approval、acceptanceはqueueへ残す。
- 別文脈のSolは判断材料やreviewを提供できるが、明示的な委譲なしに不在collaboratorの
  approvalを代行しない。
- collaborator復帰後は§10のreconciliationを行う。

### 16.2 最初から単独運用

external managerを前提にしない構成では、欠損したroleを仮想的に再現するのではなく、
開始時にauthority mapを組み直す。

標準的な個人運用では、userがproduct directionと不可逆判断を保持し、resident Codexが通常の
engineering判断、scope設定、worker委譲、actual diff review、verification、最終報告を担う。
独立reviewはすべての作業へ要求せず、高リスク時だけ任意のfresh-context reviewerを利用する。

別文脈のGPT-5.6 Solを継続的なmanagerとして使う場合は、単なる別sessionではなく、少なくとも
authority contract、担当範囲、durable inbox、正本pointer、decision log、handoff、escalation条件を
与える。これらがない場合、そのsessionはmanagerではなくadvisory reviewerとして扱う。

## 17. Supported governance topologies

### 17.1 `resident-only`

公開版と通常の個人利用における最小構成。

```text
User
  -> direction / exceptional decisions
Resident Codex
  -> direct implementation or bounded Luna packet
Luna
  -> actual diff and evidence
Resident Codex review
```

- product direction、scope拡張、不可逆操作はuserが所有する。
- settled policy内の通常実装判断はresident Codexが所有する。
- 小規模変更までexternal reviewerを必須化しない。
- self-reviewをindependent reviewと表示しない。

### 17.2 `resident-plus-fresh-reviewer`

resident-onlyへ、高リスク作業だけ認知的に独立したreviewを追加する。

典型trigger:

- credential、privacy、retention、data loss。
- migration、identity、host handoff、memory merge。
- core policyまたは重大なpublic contract変更。
- worker scope violation後の再検収。
- residentが作成したproblem framing自体を再検討する必要がある場合。

reviewerには原依頼、正本、packet、actual diff、fresh verification、non-goalsを渡し、workerの
成功要約は初回入力から外す。fresh reviewerは、userが別途authorityを与えない限りadvisoryである。

### 17.3 `externally-managed`

external managerが、複数repositoryまたは長期研究を横断してproduct management、
spec調整、独立acceptanceを担う構成。

この構成は高い継続性と独立性を提供する一方、quota、transport、handoff、reconciliationの
運用費用を持つ。公開harnessの必須runtime条件にはしない。

external managerが一時的に不在になっても、自動的に`resident-only`へ移行しない。
§4のfallback stateを使い、恒久的なtopology変更はuserが明示的に決める。

## 18. Quota-aware role allocation

external managerのquotaが縮小した場合、各agentへ同じ量の作業を残したままmodelだけを
置き換えるのではなく、external managerを高い判断価値がある箇所へ集中させる。
この節はquota縮小時の追加配分を扱う。quotaは運用上の制約であり、authorityを変更する理由ではない。

quota低下はauthorityを自動変更しない。現行governanceがexternal managerのspecまたはacceptanceを要求する
repositoryでは、その規程をuserまたは正当なownerが明示的に改訂するまで維持する。

### 18.1 external managerへ優先的に残すwork

- product visionをobservable contractへ変換する判断。
- core policy、identity、memory semantics、migration policy。
- 複数repositoryへ波及するarchitectureと優先順位。
- 複数の妥当案があり、選択がcompatibility、failure semantics、data modelを変える判断。
- milestone単位の独立acceptanceと、residentが見落とした前提の監査。
- userへ上げるべき論点の選別。

### 18.2 resident Codexへ移しやすいwork

- repository現物調査、status取得、再現、証拠収集。
- 既決定contract内のimplementation spec具体化。
- Luna packet作成、実装orchestration、actual diff review。
- focused testとbroader verification。
- 文書同期、handoff、review packet、decision候補の整理。
- 既存patternから一意に導ける局所判断。
- milestone未満の低リスクunitに対する`verified_by_codex`判定。

### 18.3 Lunaへ残すwork

- acceptance criteriaが確定したbounded implementation。
- 反復的なtest／fix loop。
- 既存patternに沿う局所変換。

Lunaはquota対策によってproduct judgmentやacceptance ownerへ昇格しない。

### 18.4 external manager呼出しを減らす運用

- 細切れの質問を送らず、判断点、根拠、選択肢、推奨、停止範囲を一つのdecision packetへまとめる。
- 実装roundごとのacceptanceではなく、意味のあるmilestone境界でまとめて独立reviewを依頼する。
- status polling、test log要約、diff inventoryはresidentが行い、external managerにはpointerと判断対象だけを渡す。
- 低リスクunitはresidentが完了させ、独立reviewが必要なものだけqueueする。
- quota末期にroutine workで枠を使い切らず、core-policy判断、障害、重大なregression用のreserveを残す。
- 同じ前提説明を繰り返さず、versioned source of truthとdecision logを再利用する。

### 18.5 目標と失敗信号

目標はexternal managerの関与をゼロにすることではなく、1回のturnが変える判断価値を高めることである。

望ましい観測:

- external-manager turnあたりの確定decision数または解消blocker数が増える。
- external managerがstatus収集や実装log読解へ使うcontextが減る。
- resident-onlyで完了した低リスクunitの手戻り率が許容範囲に留まる。
- milestone reviewで重大な前提誤りを引き続き検出できる。

失敗信号:

- residentが未決定のproduct policyを暗黙に決める。
- external-manager review queueが巨大化し、独立検収が形式化する。
- packet作成費用が直接相談より大きくなる。
- quota節約のためにverification、actual diff review、user escalationを省略する。
- 別文脈のSolを、authority contractなしに「external-manager代行」と表示する。

固定のturn比率やtoken配分は、現在のquota表示だけから決めない。数週間の実測で、
external managerが処理した判断class、resident側の手戻り、待ち時間、未処理review数を記録し、
それからrole境界を調整する。
この観測のために専用ledger、counter、集計基盤を作らず、既存のdecision logと会話・review記録から比例的に確認する。

## 19. Public harness implication

公開harnessは`resident-only`で安全に成立することを必須とする。external manager、external transport、memory system、
fresh-context reviewerはoptional integrationであり、不在時に権限を緩和したり偽の独立検収を
生成したりしない。

公開版へ外部manager連携を追加する場合も、特定の人格やmodel名を必須にせず、
authority、decision packet、result、reconciliationのcontractとして接続する。
