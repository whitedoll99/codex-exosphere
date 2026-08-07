# Luna worker 効率改善設計

## 決定対象

`run-luna-worker` の成功result互換と障害診断能力を保ちながら、親セッションへ流れる進行logを抑制し、過大な実装をLunaへ一括委譲しない運用境界を定める。

この決定は二つに分ける。

1. **transport efficiency**: Codex CLIのraw進行logを親へ無加工で流さない。
2. **work-unit efficiency**: Luna自身のcontextを肥大化させる過大なwork unitをresident Codexが分割する。

前者だけでは親contextは軽くなるがLuna使用tokensは減らない。後者だけではLuna tokensを抑えられても親へのlog汚染が残る。両方が必要である。

## 現行baseline

2026-07-16、Codex CLI 0.144.4で観測した。

| workload | Luna tokens | final result | raw進行log |
| --- | ---: | ---: | ---: |
| 公開CLI境界を発見して無変更返却 | 14,359 | 568 bytes | stderr 13,435 bytes |
| eval基盤一式の実装 | 196,294 | 762 bytes | 親側で大量の累積diffを反復表示 |

大規模ケースはrunner、schema、fixture、tests、READMEを一つのworkerへ委譲した。要求は明確だったが、一つの局所behaviorではなく、複数の独立検分可能なcomponentを含んでいた。

## 品質scenario

| 属性 | 刺激 | 期待応答 | 測定 |
| --- | --- | --- | --- |
| 互換性 | 既存callerがlauncherを成功実行 | `--output`へ最終resultを書き、stdoutにも同じresultを返す | result一致、exit 0 |
| 診断性 | Codex CLIまたはmodelが失敗 | raw全量を流さず、redact済みの原因とexit codeを返す | bounded stderr、秘密値不在 |
| 親context効率 | 長いworker実行 | 親へcommand outputやdiff全量を中継しない | captured stdout+stderr bytes |
| Luna token効率 | 複数componentの明確な実装依頼 | resident Codexが保持または独立review可能なroundへ分割 | routing result、round別usage |
| 安全性 | prompt、tool output、認証警告に機密値が含まれる | 永続metricsと親出力へ秘密値を残さない | adversarial redaction test |
| 可観測性 | 成功・失敗を比較 | usage、elapsed、raw byte数、event countを任意metricsへ保存 | schema化されたJSON |
| portability | 別VMへbootstrap | stdlib、bash、既存Codex CLIだけで動く | isolated install test |

## 選択肢

### A. 現状維持

実装は不要で診断情報が最大だが、親contextと画面へraw log・diffを全量流し続ける。今回の実測問題を解消しないため不採用。

### B. stdout/stderrを単純に破棄

最小変更で静かになるが、CLI failure、plugin failure、model errorの診断根拠を失う。成功したように見える偽陰性も生み得るため不採用。

### C. raw logを永続保存し、親には要約だけ返す

診断性は高いが、promptやtool outputを含むraw logが新たな機密artifactになる。retention、権限、削除責任が増えるため既定値にはしない。

### D. 一時raw log + 構造化metrics + bounded failure診断

Codex CLIを`--json`で実行し、raw JSONLとstderrは0700の一時`CODEX_HOME`内だけに置く。成功時は最終resultと短いsummaryだけを返す。任意の`--metrics FILE`には内容を持たない計数値だけを書く。失敗時はredact・長さ制限した診断だけを返す。これを採用する。

## Launcher contract

### Input

```text
run-luna-worker --cd GIT_ROOT --packet-file FILE.json --output FILE [--metrics FILE]
```

- v1 JSON packet、Git root、worktree外のoutputを必須とする。
- `--metrics`は任意で、指定しなければ永続metricsを作らない。
- packet shape、dirty state、allowed pathをmodel起動前に検査する。
- 実行後にHEADとdirty stateを比較し、scope違反をexit 78にする。

### Success

- exit `0`
- `--output`に最終model messageを保存する。
- stdoutへ同じ最終messageを一度だけ出す。
- stderrは開始・完了の短いlifecycle summaryだけとする。
- `--metrics`指定時は、schema version、status、model、reasoning effort、elapsed、JSONL/stderr/result byte数、event count、実読取Skill名、usage、および比較用の非cached入力派生値をJSONで保存する。派生値は課金額そのものとはみなさない。

### Failure

- Codex CLIの非zero exitを保持する。
- raw JSONLとraw stderrは一時領域の削除とともに破棄する。
- stderrへexit codeと、最大長を制限しredactしたerror event／stderr tailを出す。
- 不完全なresultを成功resultとしてstdoutへ出さない。
- metrics指定時は`status=failed`と観測できた計数値を保存する。

### Invariants

- 認証情報をコピーしない。
- raw log、session ID、prompt、command、diff、絶対workspace pathをmetricsへ含めない。
- filter／metrics生成の失敗をmodel成功へ変換しない。
- commit・push権限を変更しない。
- scope違反を自動revertせず、Codex review用の証拠を残す。

## Luna soft budget

数値による絶対上限ではなく、独立検分可能性を境界にする。

Lunaへ渡すwork unitは原則として、次をすべて満たす。

- 一つのobservable behavior、または分離すると不自然な密結合behavior群である。
- 変更可能pathとnon-goalを列挙できる。
- 一つの焦点化したtest loopで主な正しさを証明できる。
- diff全体をresident Codexが一回のreview unitとして理解できる。
- code、public contract、schema、migration、運用policyの複数判断を束ねていない。

次の場合はresident Codexが保持するか、順序づけた複数roundへ分割する。

- 複数の独立componentを同時に新設する。
- runner、schema、fixture、tests、利用文書のように別々の失敗modeを持つ成果物を一括構築する。
- 実装途中の発見によりallowed path、acceptance criteria、互換性判断を広げる必要がある。
- workerが一つのdecision packetで説明できない複数の未決定点を発見した。

ファイル数や行数はreview triggerとして記録してよいが、言語や変更内容を無視したhard limitにはしない。予想を超えた場合、Lunaは既存変更を増やさずSolへ分割判断を返す。

## リスクと緩和

- **JSONL event形式の変更**: 未知eventは計数するだけで無視し、usage欠落をlauncher failureにしない。CLI更新時にcontract testを再実行する。
- **診断不足**: failure時だけerror eventとstderr tailをbounded表示し、同じ失敗をdebug modeなしで再現可能か確認する。
- **秘密漏洩**: API key、Bearer、token assignment、`auth.json` pathをredactし、metricsに内容を入れない。
- **exit codeの消失**: pipeline filterを置かず、Codex出力を直接fileへredirectして終了codeを捕捉する。
- **静かな長時間実行**: 開始lineを即時出し、resident Codexが通常のcommentary cadenceを所有する。launcherは偽の進捗を生成しない。
- **過剰分割**: soft budgetとし、密結合behaviorは一roundを許容する。round数自体を成功指標にしない。
- **起動overhead増加**: 同一の小修正を不必要に分割しない。token実測で総費用を比較する。

## 検証計画

1. fake Codexでsuccess、model failure、malformed JSONL、秘密を含むstderrをcontract testする。
2. `bash -n`、bootstrap isolated install、repository verificationを行う。
3. 改修前と同じ公開CLI境界fixtureをlive実行し、結果品質、usage、親出力byte数を比較する。
4. 複数componentの明確な実装依頼をrouting evalへ追加し、Sol保持または分割判断を確認する。
5. launcher変更だけではLuna tokensが減らないことを明示し、soft budgetの効果と混同しない。
