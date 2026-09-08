# rei-meta-mcp — Phase 進行

このドキュメントは README §5 の詳細版。README 側は要約のみ、判断待ち項目や
実装先行のずれはここで追跡する。

## 現在の位置

| Phase | 状態 | 対象 |
|---|---|---|
| Phase 1 | 動作中 (spike) | 3 adapter × 1 object × 3 tool |
| Phase 2A | 実装済み | `_check_contract` (warning-only) |
| Phase 2 (元記載) | 未着手 | 履歴・定期実行・通知 |
| Phase 3 | 未着手 | スキーマ推論・射の一般化 |
| 判断待ち枠 | 未確定 | contract 違反の `status` 昇格 |

## Phase 1 — 現在の spike

- 3 adapter: `sqlite` (full fingerprint) / `mcp_stdio` (partial fingerprint) / `unreachable_placeholder` (§4 露出機構)
- 1 object: `seed_kernel`
- 3 MCP tool: `meta_list_sources` / `meta_check_coherence` / `meta_compose`
- 中核: §4「unchecked is not coherent」+ `unreachable_placeholder` による盲点閉塞

Honest scope §4 で書かれている「対象が増えるほど価値が増す構造」の初期状態。

## Phase 2A — 先行実装した contract check

`_check_contract` (`src/rei_meta_mcp/coherence.py`) が `expected_fields` (registry) と `source_payload_keys` (adapter) の突合を担う。

**warning-only 規律**: `status` enum (`coherent / divergent / unreachable / single_source`) は絶対に変えない。`warnings: ["CONTRACT: ..."]` として surface するのみ。`tests/test_contract.py::test_check_coherence_end_to_end_finding30` が「status を汚さないこと」を凍結。

**経緯**: README §5 元記載の Phase 2 リスト（履歴・定期実行・通知）には含まれていない。finding30 系対応として先行実装。README の Phase 進行と実装順が同期していないことを、このドキュメントで追跡する。

### 補助ツール: coherence dashboard (2026-08-25 追加)

`rei-meta-dashboard` CLI として同梱。CHECKER (別 repo) の `stats()` と本パッケージの `check_coherence()` を並置表示する読み取り専用ツール。Phase 1 + 2A の実運用データを 1 画面で眺めるための補助で、以下は **意図的に含まれない**:

- 定期実行・履歴永続化 → Phase 2 で判断
- 通知 (Slack / mail) → Phase 2 で判断
- 両者の合成指標化 → Phase 3 で判断

`stats()` と `check_coherence()` を並べて眺めた結果として合成の設計判断が自然に浮上するのを待つ。

## Phase 2 — 元記載（未着手）

- **履歴**: coherence 実行結果の永続化。今は毎回 in-memory で probe している。
- **定期実行**: cron / systemd timer 等での自動再検査。
- **通知**: divergent 検出時の外部通知（Slack, mail, etc.）。

Honest scope §1「検出のみ、修復は行わない」と摩擦しない範囲で設計する。

## Phase 3 — 未着手

- **スキーマ推論**: `src/rei_meta_mcp/compose.py` docstring 参照。sqlite の `PRAGMA table_info` や MCP tool の `inputSchema` から canonical schema を導出。`fingerprint_canonical` と同種の決定性 floor が要る。`theory_canonical(T)` (CID 用) とは別関数として維持 (`src/rei_meta_mcp/fingerprint.py` の module docstring 参照)。
- **射の一般化**: Honest scope §3「関手・随伴・モナドは書かない」を維持したまま、多段射・射の方向付け等を検討。判断は Phase 2 の時間軸が入ってから（「時間を跨いだ射」が意味を持ちうる）。

## 判断待ち枠 — contract 違反の status 昇格

Phase 2A は warning-only。将来 `status: contract_mismatch` 等に昇格すべきか、しないままか、は以下 3 signal で判断する:

1. 警告が読まれず埋没する頻度
2. contract mismatch と実データ divergent の相関
3. object 数（現状 1 → 10 超えで警告埋没が現実問題化）

このどれも実運用データが揃うまで判断できない。Honest scope §5「Phase 1 が実運用で機能した後に判断」の姿勢を、この項目にも適用する。

## Phase 進行と README §5 のずれについて

README §5 は Phase 進行の要約であり、実装順に応じて更新される。ずれが生じた場合は、まずこのドキュメントに事実を記録し、README §5 の書き換えは事後に行う（README 更新のオーバーヘッドで Phase 2A のような先行実装が遅れないため）。
