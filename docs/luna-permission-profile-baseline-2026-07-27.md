# Luna permission profile 能力測定 baseline

## 結論

2026-07-27、Linux上のCodex CLI 0.145.0で、Phase Bの8項目はすべてconfigまたは
CLIで表現でき、意図した境界が実測で強制された。unsupported profileとmalformed
configはいずれもcommand実行前に失敗し、広いsandboxへのfallbackは観測されなかった。
したがって、permission profileを使う次roundの前提は維持できる。

実装時に重要な結果は次の3点である。

1. `codex exec --sandbox ...`はconfigの`sandbox_mode`と`default_permissions`の
   両方に勝つ。profileを有効にするlauncherから`--sandbox`を除去する必要がある。
2. CLI指定がない場合、0.145.0では`default_permissions`が同じconfig内の
   `sandbox_mode`より有効だった。これは測定時点のofficial manualの説明と異なるため、
   この差へ依存せず、隔離`CODEX_HOME`から旧設定を除去する。
3. `/tmp`配下の`CODEX_HOME`では、CLIがsandbox helper aliasの自動生成を拒否した。
   実験では同じCodex installationのnative binaryを一時領域へ
   `codex-linux-sandbox`として複製し、profileからread可能にして測定した。次roundでは
   helper解決を明示的なcapability checkとし、解決不能時はfail closedにする必要がある。

本書は能力測定の記録であり、permission profile、launcher、agent、configの実装変更を
承認または実施するものではない。

## 測定環境と封じ込め

- 対象: Codex CLI `0.145.0`、Linux x86_64
- repository HEAD: `4bdf7ba`
- fixture、一時`CODEX_HOME`、fake provider、dummy credential、write target:
  `/tmp`配下の実行ごとの一時directory
- model応答が必要な`codex exec`測定: loopback上のlocal fake Responses provider
- credential測定: 実credentialではなく、`codex login --with-api-key`へ渡したdummy値
- network測定: loopback listenerへsandbox外controlとsandbox内接続を順に実行
- 終了時: fixtureと実験scriptを削除済み

実repository、実`~/.codex`、実credentialの内容は測定targetにしていない。secret、
raw token、実pathの機微な部分は本書へ記録していない。

手順上の経緯として、helper解決の診断中に`codex doctor --json --all`を一度実行した。
このcommandは既存のCodex認証状態で動作したが、credentialの内容は測定commandへ
渡さず、本書にも診断出力を転記していない。brief task revision 2のacceptanceは、
「実credentialの内容を測定面で読まず、成果物へ転記しない」であり、この境界は維持した。

## 使用したprofileの要点

pathはすべて実行ごとの`$LAB`へ置換して示す。

```toml
default_permissions = "luna-measurement"

[shell_environment_policy]
inherit = "all"
include_only = ["PATH", "SAFE_ALLOWED"]

[permissions.luna-measurement.filesystem]
":minimal" = "read"
"$LAB/profile-home/auth.json" = "deny"
"$LAB/helper-bin" = "read"

[permissions.luna-measurement.filesystem.":workspace_roots"]
"." = "read"
"allowed" = "write"
".git" = "deny"
".codex" = "deny"
".env" = "deny"

[permissions.luna-measurement.network]
enabled = false
```

`allowed`はpacketの`allowed_changes`を単一のreview unitへ解決した場合の代表である。
実装時にはpacket pathを検証・正規化してから同等のexact subtree ruleへ変換する。

## 判定表

| # | 測定 | 表現可能か | 強制されるか | 実測結果 |
| --- | --- | --- | --- | --- |
| 1 | 隔離`CODEX_HOME`のconfig読込み | **可能**。`CODEX_HOME=$LAB/profile-home`と`codex sandbox -P luna-measurement`で選択 | **される** | profileだけがwriteを許した`allowed/measurement-1`の作成がexit 0で成功 |
| 2 | allowed pathだけwrite | **可能**。`:workspace_roots`をreadとし、`allowed`だけwrite | **される** | allowedはexit 0で作成。隣接pathはexit 1 / read-only filesystem、workspace外はexit 1 / sandboxから不可視。両targetとも未作成 |
| 3 | `.git`、`.codex`、credential pathのdeny | **可能**。exact pathとworkspace相対pathへ`deny`を指定可能 | **される** | dummyを置いた`.git/dummy`、`.codex/dummy`、`.env`はすべてread testがexit 1。dummy `auth.json`も測定8でexit 1 |
| 4 | network disabled | **可能**。profileの`network.enabled = false`で表現 | **される** | 同じlistenerへのsandbox外control接続は成功。sandbox内socket生成はexit 1 / `Operation not permitted`で、listener側acceptなし |
| 5 | shell environment allowlist | **可能**。`inherit`と`include_only`を併用 | **される** | `PATH`と`SAFE_ALLOWED`は存在し、未許可のdummy secret markerは不存在というtestがexit 0 |
| 6 | configとCLI sandboxの優先順位 | **可能**。config `sandbox_mode`、`default_permissions`、CLI `--sandbox`で表現 | **される** | config read-only + CLI workspace-writeはwrite成功。config workspace-write + CLI read-onlyはwrite失敗。CLIなしでは`default_permissions`がconfig `sandbox_mode`より有効 |
| 7 | unsupported / malformed profileのfail closed | **可能**。存在しない`-P`名と壊れたTOMLで検査 | **される** | missing profile、malformed configともexit 1。fallback検知markerはどちらも未作成 |
| 8 | Codex認証とsandboxの`auth.json`読取り分離 | **可能**。Codex clientのauth storageとfilesystem denyは別境界 | **される** | dummy loginはexit 0。local fake providerはAuthorization headerの存在だけを確認。sandbox内のdummy `auth.json` readはexit 1 |

表現不可能な項目は0件である。測定7はfail closedであり、本round固有のuser
escalation条件は発火しない。

## 実測commandと結果

以下は再現用のcommand形である。`$LAB`は毎回新しい一時directory、`$WORKSPACE`は
その配下のfixtureを表す。実験では各commandの終了codeとtargetの存在を別々に確認した。

### 測定1・2: config読込みとwrite scope

```bash
CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P luna-measurement -C "$WORKSPACE" \
  bash -c 'touch "$WORKSPACE/allowed/measurement-1"'

CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P luna-measurement -C "$WORKSPACE" \
  bash -c 'touch "$WORKSPACE/adjacent/measurement-2"'

CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P luna-measurement -C "$WORKSPACE" \
  bash -c 'touch "$LAB/outside/measurement-2"'
```

結果:

- `allowed`: exit 0、target作成
- `adjacent`: exit 1、`Read-only file system`、targetなし
- workspace外: exit 1、targetなし

### 測定3: deny read

```bash
CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P luna-measurement -C "$WORKSPACE" \
  bash -c 'test -r "$WORKSPACE/.env" && head -c 1 "$WORKSPACE/.env" >/dev/null'
```

同じ形で`.git/dummy`と`.codex/dummy`を測定した。3件ともexit 1だった。dummy
`auth.json`のexact denyは測定8で同じ結果になった。

### 測定4: network

sandbox外でloopback listenerへ接続できることをcontrolとして確認後、同じlistenerへ
profile内から接続した。

```bash
CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P luna-measurement -C "$WORKSPACE" \
  python3 -c 'import socket; socket.create_connection(("127.0.0.1", PORT), 2)'
```

controlは成功し、sandbox commandはsocket生成時にexit 1 /
`PermissionError: Operation not permitted`となった。listenerはsandbox側接続をaccept
しなかった。

### 測定5: shell environment

```bash
SAFE_ALLOWED=visible SECRET_SHOULD_BE_HIDDEN=dummy-marker \
CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P luna-measurement -C "$WORKSPACE" \
  bash -c \
  'test "$SAFE_ALLOWED" = visible &&
   test -n "$PATH" &&
   test -z "${SECRET_SHOULD_BE_HIDDEN+x}"'
```

exit 0。allowlist対象だけがsandbox commandへ到達した。

### 測定6: `codex exec`の優先順位

modelの判断揺らぎと実credentialを排除するため、local fake providerが決定論的に
`exec_command`でwrite marker作成を要求し、そのtool outputを受けて終了する構成を使った。

```bash
CODEX_HOME="$LAB/config-read-only" \
  codex exec --sandbox workspace-write -C "$WORKSPACE" ...

CODEX_HOME="$LAB/config-workspace-write" \
  codex exec --sandbox read-only -C "$WORKSPACE" ...
```

| config | CLI | permission profile | marker |
| --- | --- | --- | --- |
| `sandbox_mode = "read-only"` | `--sandbox workspace-write` | なし | 作成 |
| `sandbox_mode = "workspace-write"` | `--sandbox read-only` | なし | 未作成 |
| `sandbox_mode = "read-only"` | なし | workspace write | 作成 |
| `sandbox_mode = "workspace-write"` | なし | workspace read | 未作成 |
| `sandbox_mode`なし | `--sandbox read-only` | workspace write | 未作成 |

各caseでfake providerは2 requestを受け、2回目にtool outputが含まれた。したがって、
marker差はmodelがtool callを省略した結果ではない。

測定時点のofficial [Permissions documentation](https://learn.chatgpt.com/docs/permissions)
は、loaded configに`sandbox_mode`があればpermission profileと合成せず旧設定を使うと
説明していた。一方、0.145.0実測ではconfig内の`default_permissions`が
`sandbox_mode`より有効だった。CLI `--sandbox`がprofileより有効な点は実測で一貫した。
次roundはdocumentまたは実装のどちらか一方へ依存せず、旧settingを隔離configとCLIの
両方から除去し、capability testで有効境界を確認する必要がある。

`codex sandbox -P`はpermission profileを明示選択する専用surfaceであり、そこで
top-level `--sandbox`を併記した結果は`codex exec`の優先順位判定に使わなかった。

### 測定7: fail closed

```bash
CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P profile-does-not-exist -C "$WORKSPACE" \
  bash -c 'touch "$LAB/outside/missing-profile-fallback-marker"'

CODEX_HOME="$LAB/malformed-home" \
  codex sandbox -P broken -C "$WORKSPACE" \
  bash -c 'touch "$LAB/outside/malformed-profile-fallback-marker"'
```

- missing profile: exit 1、undefined profile error、markerなし
- malformed TOML: exit 1、parse error、markerなし

commandへ到達した形跡はなく、広いsandboxへのfallbackもなかった。

### 測定8: auth境界

一時`CODEX_HOME`へdummy API keyを保存し、`requires_openai_auth = true`のlocal fake
providerへ`codex exec`を実行した。providerはAuthorization headerの**存在だけ**を
記録し、値は保存・表示していない。

```bash
printf '%s\n' 'DUMMY_VALUE' |
  CODEX_HOME="$LAB/profile-home" codex login --with-api-key

CODEX_HOME="$LAB/profile-home" \
  codex sandbox -P luna-measurement -C "$WORKSPACE" \
  bash -c \
  'test -r "$LAB/profile-home/auth.json" &&
   head -c 1 "$LAB/profile-home/auth.json" >/dev/null'
```

dummy loginとlocal provider requestは成功し、sandbox readはexit 1だった。これは
Codex clientが認証情報を利用する境界と、model起動commandがcredential fileを読む
境界を分離できることを示す。実credentialの内容は使用していない。

## 次roundへの設計入力

1. launcherの`codex exec --sandbox "$worker_sandbox"`はprofileを無効化するため除去候補。
2. 隔離`CODEX_HOME`には`default_permissions`と`[permissions.<name>]`だけを生成し、
   `sandbox_mode`と`[sandbox_workspace_write]`を含めない。
3. `allowed_changes`から生成する初版ruleはexact path / subtreeへ限定し、glob変換器を
   先行実装しない。
4. workspace全体はread、許可subtreeだけwrite、`.git`、`.codex`、credential pathは
   exact denyとする。
5. networkはprofileの`enabled = false`を既定にし、shell environmentは
   `include_only`または`inherit = "none"`と明示的`set`で構成する。
6. missing profile、malformed config、helper解決不能、境界smoke失敗はmodel起動前に
   fail closedとする。
7. packet guardとGit postflightは、permission profileとは独立した検収層として残す。
8. 実authはCodex clientだけが利用し、sandbox commandからはdenyする。次roundのfixture
   もdummy authとlocal providerを使う。
9. native `luna_worker`の権限は本roundでは変更しない。親runtime継承とprofile選択を
   別fixtureで確認してから、read-only補助用途の機械的強制方法を決める。

## Standing challenge record

1. **既存概念の修正か、新概念の追加か**: 既存のguarded launcherへ事前権限制約を
   足すための能力測定であり、新しい製品役割は追加していない。
2. **元の製品思想にこの境界は存在したか**: allowed changes、credential非露出、
   network制約、fail closedは既存roadmap Phase Bの境界である。
3. **test都合を製品要件へ昇格していないか**: marker、dummy auth、fake providerは
   観測手段であり、公開contractにはしない。
4. **ユーザーが実際に望んだことか**: 公開前に現行環境で作り込み、実証済み境界だけを
   公開coreへ抽出する方針に沿う。
5. **現状比較で何を防ぐgateか**: 存在しないCLI能力を前提にfixtureとlauncher実装を
   作ること、およびprofile失敗時に広い旧sandboxへ落ちることを防ぐ。

## 判定

- 測定1〜8: **全項目、表現可能かつ強制を実測**
- 測定7: **fail closed**
- 表現不可能項目: **0**
- Phase B後段: **設計可能**。本書を入力として別briefで承認する
- 本roundの実装変更: **なし**
- commit / push: **未実施**
