# Skill・モデルルーティング評価 初回baseline

## 判定

2026-07-16 に代表4ケースをlive実行し、現在のrunnerとscorerで次の5点を確認できた。

1. 局所的で要件・テストが明確な修正はLunaへrouteされる。
2. 曖昧な機能要求はSolが保持する。
3. それぞれ必要なSkillだけが実際に読み取られ、routingケースで過剰発火は観測されない。
4. Lunaは実装中に公開契約の未決定境界を発見すると、変更せずdecision packetを返す。
5. Solはworker報告を鵜呑みにせず、実status・diff・テストからscope逸脱、regression、coverage不足を独立検出する。

これは単発sampleによる環境smoke testであり、モデル一般の性能や将来実行の成功率を保証する統計評価ではない。

## 実行結果

| ケース | 観測結果 | 判定 |
| --- | --- | --- |
| `routing-local-bug` | route=`luna`、実読取Skill=`bounded-tdd`のみ | pass |
| `routing-ambiguous-feature` | route=`sol`、実読取Skill=`problem-framing`のみ | pass |
| `luna-discovered-public-boundary` | `bounded-tdd`と報告前検証を使用し、公開CLI契約の衝突を検出。diffなし、commitなし、決定主体と2案を返却 | pass |
| `sol-review-seeded-defects` | 空入力regression、空入力test欠落、scope外untracked fileを検出。fixtureはread-onlyのまま | pass |

live artifactは認証情報やsession stateをGit管理へ持ち込まないため、一時ディレクトリにのみ保存した。baselineには判定に必要な要約だけを残している。

## 評価中に見つかり修正した基盤側の欠陥

- 外側のsandbox内から起動した `codex exec` が通常のCodex state directoryへ書けなかった。認証・設定をコピーせずsymlinkする、一時 `CODEX_HOME` をrunnerごとに用意した。
- structured output schemaに任意propertyがあり、APIの厳格schema検証に拒否された。全propertyをrequiredにするか、不要propertyを除去した。
- JSONLのcommand outputに列挙されたSkillまで発火扱いしていた。実際のcommand引数が `SKILL.md` を指定した場合だけを証拠とするよう狭めた。
- 最初のLuna fixtureでは新旧挙動が両立でき、未決定境界が実在しなかった。共有parserの既存契約と新しいtestが実際に衝突するfixtureへ直した。
- Sol findingを事前登録IDとの完全一致だけで採点し、同じ事実を別の妥当なIDで報告すると不合格になった。期待ラベルをpromptへ漏らさず、IDまたは事前定義した根拠signalで意味的に採点するよう改めた。

この経緯は失敗を隠すものではない。初回evalがモデル挙動だけでなく、評価器自身の妥当性を検証する役割も果たした記録である。

## 運用手順

通常はモデルを呼ばない3コマンドから始める。

```bash
python3 evals/run.py list
python3 evals/run.py validate
python3 evals/run.py plan --case routing-local-bug
```

live実行は1ケースずつ明示し、空の出力先を指定する。

```bash
python3 evals/run.py live \
  --case routing-local-bug \
  --output /tmp/codex-eval-routing-local-bug
```

- exit `0`: case pass
- exit `1`: モデル出力または観測結果が期待を満たさない
- exit `2`: case、schema、fixture、launcherなどrunner側の障害

exit `1`を直ちにモデル品質の失敗と断定しない。`report.json`、`final.json`、JSONLまたはworker log、Git evidenceを見て、モデル・fixture・観測器・scorerのどこで期待と分岐したかを確認する。

## 次回以降

- 残るrouting 4ケースを少なくとも1回ずつbaseline化する。追加した大規模subsystem routing caseはlive合格済み。
- 同一ケースを複数回実行し、単発揺らぎと再現するrouting欠陥を分離する。
- Codex CLI更新後はstructured output schemaとJSONL event形式を再確認する。
- Skill追加・説明変更、Luna routing規則変更、launcher変更後は該当caseを再実行する。
- exactなtoken量やlatencyは環境・cache・モデル更新で変動するため、固定合否閾値にはまだ使わない。
