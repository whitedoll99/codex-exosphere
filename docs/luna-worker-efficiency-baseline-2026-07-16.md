# Luna worker 効率改善 初回baseline

## 結論

構造化log配管は、結果品質とLunaの実質的なtoken量をほぼ維持したまま、親へ流れる出力量を大幅に削減した。soft work budgetは、明確でも多componentな実装をSolが保持する判断と、Lunaが互換性配置を勝手に決めず無変更返却する動作を実証した。

一方、log抑制だけではLuna自身のtokensは減らない。委譲packetにbudgetが明記されていない場合、同じfixtureでもLunaが設計選択を実装し、tool stepとtokensが膨らむ実行が観測された。したがって、配管改善とwork unit管理は両方必要であり、Solの事後diff reviewも引き続きhard gateである。

## A/B測定

2026-07-16、Codex CLI 0.144.4、GPT-5.6 Luna xhighで実施した。`非cached入力+出力`は比較用派生値であり、料金そのものではない。

### Read-only Skill列挙smoke

deploy済み旧launcherと改修中launcherへ、同じworkspaceとread-only packetを与えた。

| 指標 | 旧launcher | 新launcher |
| --- | ---: | ---: |
| 結果 | 3 Skillを列挙 | 同じ3 Skillをnamespace付きで列挙 |
| token比較値 | `tokens used` 2,566 | 非cached入力+出力 2,882 |
| 親stdout | 65 bytes | 152 bytes |
| 親stderr | 1,391 bytes | 96 bytes |
| 親出力合計 | 1,456 bytes | 248 bytes |

親出力は約83%減った。token比較値の約12%差は、result表現とmodel揺らぎを含み、JSONL化による桁違いの増加は観測されなかった。

### 公開CLI境界fixture

| 指標 | 旧launcher baseline | 新launcher + 明示budget |
| --- | ---: | ---: |
| 結果 | 無変更decision packet | 無変更decision packet |
| token比較値 | `tokens used` 14,359 | 非cached入力+出力 14,520 |
| 親stdout | 568 bytes | 579 bytes |
| 親stderr | 13,435 bytes | 96 bytes |
| 親出力合計 | 14,003 bytes | 675 bytes |
| 所要時間 | 未記録 | 46秒 |

親出力は約95%減り、token比較値は約1.1%増に留まった。新launcherはraw JSONL 13,044 bytesとraw stderr 192 bytesを一時領域だけで処理し、内容を永続化しなかった。metricsにはusage、byte数、event count、実読取Skill名だけを保存した。

## 途中で観測した失敗

最初の新launcher実行では、eval packetが「bounded」と称しながらallowed path、read-only context、stop conditionを明記していなかった。Lunaは共有parserの意味を変更し、legacy adapterへtranslationを追加して互換性を保つ案を自分で選んだ。

- 13 tool steps
- input 155,474 tokens中、cached input 132,352
- 非cached入力+出力 26,833相当
- 3ファイルを変更
- 親出力は403 bytesまで抑制されたが、scope返却には失敗

これは「静かなlauncher」と「安いworker」を混同してはいけない反例である。原因はJSONL配管ではなく、model揺らぎを許す曖昧なwork budgetと、互換translationの配置を実装判断とみなしたことだった。

対処として、delegation packetへ次を追加した。

- 一つのSol review unit
- allowed change paths
- read-only context paths
- stop conditions
- 互換adapter／translation配置をLunaが未承認で決めない規則

同じfixtureの再実行では無変更返却に戻った。

## 大規模routing

`routing-large-defined-subsystem` を追加した。runner、schema、fixture、scorer、tests、日英README、live baselineを一括構築する、要件確定済みの依頼である。

live結果はroute=`sol`でpassした。要件が明確でも、異なるfailure modeを持つ複数componentを一つのLuna roundへ渡さず、Solが保持して順序づけるという新規則が機能した。

## 実装したcontract

```text
run-luna-worker \
  --cd WORKSPACE \
  --packet-file PACKET.json \
  --output RESULT \
  [--metrics METRICS_JSON]
```

- 成功時は最終resultだけをstdoutと`--output`へ返す。
- stderrは開始・完了のlifecycle lineだけにする。
- raw JSONLとraw stderrは0700の一時`CODEX_HOME`内で処理し、終了時に削除する。
- 任意metricsはmode 0600で原子的に配置し、prompt、command、diff、session IDを含めない。
- failure時はCodex exit codeを保持し、redact・長さ制限した診断だけを返す。
- malformed JSONLは成功扱いせずfail closedする。
- output／metrics symlinkと同一pathを拒否する。

## メリット

- 親contextへraw command、Skill本文、test output、累積diffが流れ込まない。
- result fileとstdoutの既存用途を保つ。
- token、elapsed、event count、raw byte数を内容非依存で比較できる。
- failure診断を完全破棄せず、秘密値を抑制できる。
- 明確だが過大な依頼を「Luna適格」と誤判定しにくくなる。

## デメリットと残余リスク

- 成功raw logは削除するため、後日の詳細forensicsはできない。
- JSONL event形式変更時はmetrics抽出が劣化し得る。
- launcherは開始・完了だけを出すため、単独利用時の細かなlive進捗は見えない。
- soft budgetの意味判断はmodelに残るが、必須fieldとallowed Git pathはhost guardが検査する。違反diff自体は残り得るが成功扱いにはせずexit 78にする。
- 固定行数limitを採らないため、Solの事前判断品質が必要である。
- 小さなwork unitでは起動・plugin準備の固定costが相対的に大きい。
- Luna自身のtoken削減は、大規模依頼を委譲しない／分割することで初めて得られる。launcherのlog抑制だけによる削減は期待しない。

## 運用判断

1. 一つの独立review unitならLunaへ渡す。
2. packetにallowed path、read-only context、stop conditionを含める。
3. 複数componentならSolが保持し、依存順にroundを切る。
4. 各round後にSolが実diffとmetricsを検分する。
5. metricsの非cached入力+出力が想定外に増えた場合、次roundを始める前に分割を見直す。
6. Lunaのscope違反時は自動的に正当化せず、実装を採用するかどうかをSolが改めて判断する。

## 判定

- **構造化log配管**: 採用。高いconfidenceで目的を達成。
- **soft work budget**: 採用。packet存在とGit scopeはhost強制し、意味的な適切さはSol reviewで担保する。
- **token削減効果**: bounded caseではほぼ中立。大規模taskをLunaへ渡さないことで得る間接効果として扱う。
- **今後の改善**: 複数roundの実プロジェクトbaseline、同一case反復、JSONL互換testを継続する。

## v1 packet guard follow-up

budget未記載の自由形式packetがmodel呼出まで進めた残余リスクに対し、v1 JSON packetとGit scope guardを追加した。

- soft budget、allowed changes、verification、authorizationなどをschemaとして必須化した。
- 不完全packet、旧`--prompt-file`、undeclared dirty stateをmodel起動前にexit 2で拒否する。
- 検証済みpacketを一時領域へ固定し、実行中のpacket改変でscopeを広げられないようにした。
- 実行後のHEADとdirty stateを比較し、範囲外変更を非revertのままexit 78にする。
- read-only packetではCodex sandboxもread-onlyへ切り替える。

公開CLI境界fixtureのlive再検証は23秒、非cached入力＋出力7,461相当だった。Lunaは変更もcommitも行わず、互換性translationの配置判断をSolへ返した。host scope reportは`passed=true`、touched pathは空で、evalの全checkに合格した。
