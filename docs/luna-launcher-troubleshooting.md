# Luna launcher の通信失敗と app-server の設定再読み込み

2026-09-18、Linux / Codex CLI 0.154.0 / exosphere `4e2c122` で確認した事例です。
agmsg monitor が管理する長寿命の app-server に、resident の TUI が接続する構成でした。
一般の Codex 起動すべてがこの構成とは限りません。

## 症状と結論

通常端末では同じ pinned launcher と read-only packet が成功する一方、resident の
shell tool からは通信に失敗しました。親の実行経路に launcher 専用の許可を追加し、
**TUI ではなく実行を担当する app-server を再起動**した後、resident からも成功しました。

今回の原因は、親の通信制限を受けた launcher の起動と、新しい許可を読み込んでいない
app-server の再利用だったと判断しています。launcher のコードやモデルの変更は不要でした。
元の別タスクで起きた timeout や、画面の `Conversation interrupted` まで同じ原因と
確定したわけではありません。

| 観測 | 結果と判断できる範囲 |
| --- | --- |
| 通常端末から同じ launcher / packet を実行 | 27秒、exit 0。認証・実モデル呼び出し・command execution・scope check が成功 |
| resident の制限された実行経路 | DNS 失敗、別の実行では `Operation not permitted (os error 1)`。120秒で timeout / exit 124 |
| 明示的な sandbox 外起動要求 | プロセス生成前に `rejected by user`。この文言だけでは人の操作か自動拒否か判別不能 |
| ディスク上の追加ルールを検査 | `codex execpolicy check` は allow。しかし実行環境への読み込みはこれだけでは証明できない |
| TUI 終了・再開後のホスト側 `ps` | ルール追加前から動く古い app-server が残っていた |
| app-server 自体を再起動後 | resident の許可一覧にもルールが現れ、29秒、exit 0、3 tool invocations。scope pass、HEAD・作業ツリー変更なし |

最後の確認は読み取り専用の委譲です。write-capable task、公開版の新規インストール、
他 OS の動作を検証した結果としては扱いません。raw log・認証情報・個人の実パスは本書に含めません。

## 親 launcher と子 worker は別の境界

resident の shell tool から起動した `run-luna-worker` 自体が親 sandbox 内にいると、
その中の Codex client のモデル通信も親の制限を受けます。子の `--sandbox read-only`
または `workspace-write` を選び直しても、親が禁止した通信は許可されません。

この事例では、利用者が固定 launcher の起動だけを sandbox 外で許可しました。
子 worker は引き続き検証済み packet に応じた sandbox を使い、launcher は実行後に
Git scope を検査します。ただし、**launcher 自体にはホストの実行権限が与えられます**。
Git 検査は事後検出であり、あらゆる副作用を防ぐ仕組みではありません。
詳しくは [委譲契約の限界](luna-delegation-contract.md#限界) を参照してください。

## 復旧手順

1. clean な診断用 worktree と read-only packet を用意します。README の先頭を実際に
   command で読み、結果を返す程度で十分です。packet・結果は worktree の外に置きます。
   [packet contract](luna-delegation-contract.md) の必須 field を満たしてください。
2. 同じ launcher / packet を通常端末と resident の実行経路で比較します。
   `started` 表示だけを成功とせず、終了コード・新しい結果・metrics・実際の Git 状態を確認します。
   診断は短い timeout で区切り、同じ制限エラーでモデル呼び出しを繰り返しません。
3. 親の実行権限が原因なら、利用者が必要範囲の許可を選びます。下記は今回使えた
   固定 launcher 向けの例です。自動インストールや自己承認は行いません。
4. 許可を読み込む Codex runtime を再起動します。remote TUI / monitor 構成では、
   TUI を終了しても app-server が残る場合があります。ホスト端末で、現在の server PID を
   `ps -p <PID> -o pid,lstart,args` などで確認してください。記録された PID だけを信用せず、
   対象が該当 app-server だと確認してから通常の終了・起動手順を使います。
   停止すると接続中のセッションは切れるため、進行中の作業を先に区切ってください。
5. 再起動後、resident から同じ診断を実行します。終了コード 0、実 command execution、
   期待する結果、scope pass、clean な作業ツリーを確認して初めて復旧とします。
   まだ失敗する場合は、実行を担当する server と config layer を調べ、再起動だけを繰り返しません。

### 固定 launcher 向け許可の例

以下は説明用の `/home/you` です。**ルールと起動コマンドの両方を実環境の絶対パスへ
置換**し、コマンド配置も確認してください。rule の pattern は shell の `$HOME` を展開しません。
`~/.cache/codex-scratch` を事前に用意し、launcher がその中に作る一時 runtime は終了時に清掃します。

利用者が選んだ場合にのみ、active config layer の `rules/` に専用 `.rules` を追加します。
既存ルールを上書きせず、`bash`、`env`、`timeout`、`codex` 全般を許可する形には広げません。

```python
prefix_rule(
    pattern = [
        "/usr/bin/timeout",
        "--kill-after=10s",
        ["120s", "3600s"],
        "/usr/bin/env",
        "TMPDIR=/home/you/.cache/codex-scratch",
        "/home/you/.codex/bin/run-luna-worker",
    ],
    decision = "allow",
)
```

この例に対応する起動形は次のとおりです。`<...>` も実際の絶対パスへ置換します。
120秒は小さな診断用、3600秒は別途承認された作業単位用です。

```text
/usr/bin/timeout --kill-after=10s 120s /usr/bin/env TMPDIR=/home/you/.cache/codex-scratch /home/you/.codex/bin/run-luna-worker --cd <worktree> --packet-file <packet.json> --output <result.md> --metrics <metrics.json>
```

起動コマンドの前に shell の変数代入や出力リダイレクトを追加すると、ルールの照合単位が
変わることがあります。上記は固定の argv 列として使い、`codex execpolicy check --rules
<rule-file> -- <command...>` で意図したコマンドと別コマンドの照合を確認します。
これはルールの検査であり、実行中 server の読み込みやネットワーク成功の検査ではありません。
より強い禁止ルール・管理ポリシーがあれば、その制限も適用されます。

ロールバックは、このために追加した専用ルールだけを削除し、実行 runtime を再起動します。
`config.toml` 全体の復元や worker sandbox の解除は不要です。

ルールの意味と起動時読み込みについては [Codex Rules](https://learn.chatgpt.com/docs/agent-configuration/rules)
を参照してください。この記述は 0.154.0 の検証時点のもので、将来の版では再確認が必要です。

## どのリポジトリの改善課題か

- **exosphere:** この起動境界と診断方法の文書化が今回の対応です。standalone launcher の
  機能不良は確認していないため、今回だけを根拠に launcher のバグとはしません。
  外側の timeout で終了した際に一時 log が清掃され、最終 metrics を残せなかった点は
  診断改善の候補ですが、別の受入条件を定めて扱います。
- **agmsg monitor:** 調査した実装では app-server が TUI より長生きし、同じ版なら再利用
  されます。設定変更後の明示的な再起動方法、または再利用中であることの表示を改善する
  依頼が有力です。設定変更のたびに server を自動停止する案は、実行中の作業を切るため
  今回の解決からそのまま導きません。
- **Codex:** shell tool / app-server の制限境界は関係しますが、既知の許可機構と server
  再起動で成功しました。本件だけから Codex 本体の不具合とは結論しません。

Issue 化する場合は、上記の症状・比較条件・期待する改善・成功条件を小さくまとめ、
raw session log や個人環境の設定一式を添付しないでください。本書の追加は Issue 投稿の
実施や、launcher・monitor のコード変更を意味しません。
