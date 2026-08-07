# Luna delegation packet contract v1

## 目的

自由形式の委譲文だけでwrite-capable Lunaを起動すると、soft budgetやallowed pathの記載漏れをmodel呼出前に検出できない。本contractは、guarded launcherで利用するversioned packetを定義し、入力不備をfail closedにし、実行後のGit差分をhost側で検査する。native Lunaのread-only支援にも同じscope fieldを利用できるが、native Lunaを等価なwrite経路またはhost側で強制された境界とは扱わない。

## Packet

UTF-8 JSON、最大64 KiBとする。

```json
{
  "version": 1,
  "mode": "implementation",
  "objective": "Implement one approved parser behavior.",
  "acceptance_criteria": ["The focused regression test passes."],
  "allowed_changes": ["src/parser.py", "tests/test_parser.py"],
  "read_only_context": ["docs/contract.md"],
  "non_goals": ["Do not redesign the public CLI."],
  "verification": ["python3 -m unittest tests.test_parser -v"],
  "authorization": {"commit": false, "push": false},
  "existing_changes": [],
  "soft_budget": {
    "review_unit": "One parser behavior and its focused test.",
    "stop_conditions": ["A compatibility adapter must change."]
  }
}
```

### 必須条件

- top-levelとnested objectは未知fieldを拒否する。
- `version`は`1`のみ。
- `mode`は`implementation`または`read-only`。
- objectiveとreview unitは非空。
- acceptance criteria、non-goals、verification、stop conditionsは非空list。
- implementationではallowed changesが非空、read-onlyでは空。
- allowed changesはGit root相対のexact pathまたはterminal `path/**` subtreeだけを許可する。`*`などの任意glob、絶対path、`..`、`.git`を拒否する。
- read-only contextもGit root相対exact pathまたはterminal `path/**` subtreeとする。
- existing changesは起動時に存在するdirty pathのexact listであり、globを許可しない。
- v1ではcommitとpushをともに`false`に固定する。commit・pushはSolのreview後に行う。
- packetで宣言した既存dirty pathとallowed changesが重なる場合、Lunaへ渡さずSolが保持する。

## Launcher CLI

```text
run-luna-worker \
  --cd GIT_ROOT \
  --packet-file PACKET.json \
  --output RESULT \
  [--metrics METRICS.json]
```

旧`--prompt-file`はwrite-capableなfail-open経路を残すため廃止する。指定時はmodelを呼ばずmigration errorを返す。

## Preflight

1. packet size、JSON shape、field、pathを検証する。
2. workspaceがGit worktree rootであることを確認する。
3. `git status --porcelain -z --untracked-files=all --no-renames`を取得する。
4. 実dirty pathとexisting changesが完全一致することを要求する。
5. existing changeとallowed changeが重ならないことを要求する。
6. 検証済みpacketを一時領域へ正規化コピーし、model向けMarkdownへrenderする。preflightとpostflightは以後この固定コピーだけを参照する。

不一致時はexit `2`で終了し、Codex modelを呼ばない。

## Postflight

preflight snapshotと実行後snapshotを比較する。

- 新しくdirtyになったpath
- 消えた、追加された、内容・mode・symlink先が変わった既存dirty path
- HEAD変更

をLunaが触れた候補とする。候補がallowed changesに一致しなければexit `78`とし、相対pathだけを診断へ含める。自動revert、reset、checkoutは行わない。Solがactual diffを検分して採否を決める。

read-only modeはallowed changesが空なので、どの変更もscope violationになる。sandboxも`read-only`を選ぶ。

## 限界

- host guardはmodelがtoolを実行する前にsemantic scope違反を予測できない。
- postflight検出は変更を防止せず、違反として止める。Sol reviewは必須のまま。
- 外部systemへの副作用はGit snapshotでは検出できない。v1はpushを禁止し、launcherの既存sandboxとapproval policyを維持する。
- Git statusに現れない生成物やignore対象fileは検出対象外である。allowed taskがignored artifactを扱う場合はSolが保持する。
- token hard capやtimeoutは途中diffを残すためv1に含めない。

## Exit taxonomy

- `0`: model成功かつscope check合格
- `2`: CLI、packet、preflight不正
- `65`: Codex JSONL不正
- `70`: launcher内部処理不正
- `78`: postflight scope／commit violation
- その他: Codex CLI自身の非zero exitを保持

## 検証scenario

- 正常なimplementation packetをrenderし、allowed fileだけの変更を許可する。
- budget、authorization、allowed changes欠落をmodel呼出前に拒否する。
- undeclared dirty pathを拒否する。
- allowed path外の新規fileと既存dirty fileの改変をexit 78にする。
- read-only packetでworkspace-writeを使わず、変更を拒否する。
- commit作成をexit 78にする。
- path traversal、`.git`、oversized packet、symlink packetを拒否する。
- scope違反時も自動revertせず証拠を残す。
