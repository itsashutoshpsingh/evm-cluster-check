# Data

No raw chain data is committed. `data/raw/` is git-ignored and rebuilt by `make fetch`.

## Ethereum mainnet window (fixed)

| Field | Value |
|---|---|
| Start | 2026-11-01 00:00:00 UTC, block **26316189** (first block with timestamp >= start) |
| End | 2026-11-03 23:59:59 UTC, block **26337722** (last block before 2026-11-04 00:00 UTC, which is block 26337723) |
| Day boundaries | 2026-11-02 starts at block 26323365, 2026-11-03 at block 26330541 |
| Blocks | 21,534 |
| Finalised when fetched | yes (finalised head was 26394735 on 2026-11-11) |

Block numbers were found by binary search on block timestamps against `ethereum-rpc.publicnode.com` (`src/fetch.py find-window`).
