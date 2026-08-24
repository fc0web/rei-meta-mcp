# rei-meta-mcp

コネクタ群の上に立つメタ層。個々の MCP コネクタを **対象**、対象へのアクセス経路を **射** とみなし、その構造を扱う。

Phase 1 の唯一の実用目的は **整合性検査 (coherence check)** — 同じ対象を指す複数のソース間で内容が一致しているかを機械的に突き合わせる。

## なぜ作ったか

2026-08-19、`rei-memory-mcp` の実装過程で SEED_KERNEL が **1,677 vs 1,675** で 11 日間ずれたまま気づかれていなかったことが判明した。気づけたのは人間が両方の数字を偶然見比べたからで、機械には検出手段が無かった。

このコネクタの最初の仕事は、これを機械が先に見つけることである。詳細は [`docs/incident-2026-08-19.md`](docs/incident-2026-08-19.md)。

## 提供する tool (3 本)

### `meta_list_sources(object_name?: str)`

登録済みの source を列挙し、各々の到達状態・件数・git HEAD ハッシュ (freshness の手がかり) を返す。

### `meta_check_coherence(object_name: str, detail: bool = False)`

同一対象を指す source の指紋を突き合わせ、以下のいずれかの verdict を返す:

| verdict | 意味 |
|---|---|
| `coherent` | 到達できた全 source の指紋一致 |
| `divergent` | 到達できた source 間で不一致 |
| `unreachable` | 到達できた source がゼロ |
| `single_source` | 到達できた source が 1 つのみ (比較不能) |

**§4 中核ルール**: 「到達できなかった」は「一致した」ではない。`unreachable` と `single_source` は常に警告として surface される。

`detail=True` で不一致 ID の実リスト (最大 100 件) を返す。

### `meta_compose(from_source: str, to_source: str)`

Phase 1 は registry 内の `output_schema` / `input_schema` 文字列突合のみ。実スキーマ推論は Phase 3 以降。

## Phase 1 でやらないこと

- **自動修復** (意図的な除外。どちらが正しいかの判断は人間が行う)
- 検査履歴の永続化 (Phase 2)
- スキーマ推論 (Phase 3)
- 関手・随伴・モナド等の圏論構成 (必要になったときに)

## 現時点の registered source

`config/sources.example.yaml` を参照:

| source | kind | 状態 |
|---|---|---|
| `rei-memory-local` | `sqlite` | full fingerprint (`~/rei-memory-mcp/data/seed_kernel.db`) |
| `rei-aios-local-mcp` | `mcp_stdio` | partial fingerprint (`node dist/mcp/start-mcp.js` を subprocess で起動し `get_kernel_status` を叩く) |
| `rei-aios-remote` | `unreachable_placeholder` | claude.ai remote-devices 経由の deploy は Python から直接 probe 不可 — 常に `unreachable` を明示する |

## Install & 使用

```bash
uv pip install -e ".[dev]"
cp config/sources.example.yaml config/sources.yaml   # パスを埋める
uv run pytest                                        # 全 PASS を確認
uv run rei-meta-mcp                                  # stdio で MCP server 起動
```

registry のパスは環境変数 `REI_META_MCP_REGISTRY` で上書き可能。

## Honest scope

1. **検出のみ、修復は行わない** — 判断を人間の外に出さない
2. **partial fingerprint** の source (mcp_stdio) 間の一致は「不一致がない」ことの確認であって「完全一致」の証明ではない (`content_hash` レベルで見られない部分がある)
3. 圏論用語は 5 つだけ (対象・射・等化子・合成・恒等射) 荷重を負う。他は避ける
4. 現状 3 source の Phase 1 spike。対象が増えるほど価値が増す構造
5. Phase 進行は [`docs/ROADMAP.md`](docs/ROADMAP.md) を参照。Phase 1 spike + Phase 2A (contract check) が現状。Phase 2 / Phase 3 は Phase 1 + Phase 2A の実運用結果で判断。

## License

AGPL-3.0-or-later.

## 関連

- `docs/incident-2026-08-19.md` — 事故の記録
- `tests/test_incident_2026_08_19.py` — 事故を再現するテスト
