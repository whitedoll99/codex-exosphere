# 既存Codex環境への導入

対象読者は定義上Codex CLIを持っているため、`$CODEX_HOME/AGENTS.md`が既に存在するのは
標準的な入力です。bootstrapはこれを1個のmanaged targetとして扱います。

## サポートされる入力

```text
$CODEX_HOME/AGENTS.md が存在しない          -> CREATE、plan exit 0
repositoryのconfig/AGENTS.mdとbyte単位で同一 -> SAME、plan exit 0
内容が異なる                                 -> CONFLICT、plan exit 1。applyしない
```

bootstrapはbundle全体をno-clobberで導入し、既存のglobal `AGENTS.md`を自動mergeしません。
異なる内容がある場合、planは`CONFLICT`を表示して**install全体を停止します**。個別の
targetだけをskipするpartial installはサポートしていません。

この挙動は安全側の設計であり、欠陥ではありません。

## `CONFLICT`が出たときの手順

1. `--apply`へ進まない。
2. 既存の`$CODEX_HOME/AGENTS.md`をbackupする。
3. 既存fileとrepositoryの`config/AGENTS.md`の内容を比較する。
4. 判断する。
   - **repository版のglobal guidanceを採用する場合** — 既存fileをmanaged destinationの
     外へ移してから、planを再実行する。
   - **既存guidanceをそのまま残す場合** — その環境への適用を停止する。bootstrapは
     自動mergeもpartial installもサポートしていません。

`CONFLICT`はforce-overwriteの合図ではありません。repository版とdeployment版の両方を
確認して、意図したsourceを手動で選んでください。

## 確認方法

```bash
python3 bootstrap/install.py
```

planフェーズは何も書き込みません。各managed targetについて`CREATE` / `SAME` /
`CONFLICT`のいずれかを表示します。

## 関連

- [Managed paths](managed-paths.md) — 書き込み先の一覧
- [Verified scope and limitations](verified-scope.md) — 3状態の検証状況
