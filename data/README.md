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

## Row counts (Ethereum, fetched 2026-11-11/12)

| Table | Rows |
|---|---|
| Transactions | 5,440,040 |
| Logs kept (ERC-20/721 `Transfer` + ERC-4337 `UserOperationEvent`) | 9,615,381 |
| of which 3-topic `Transfer` (ERC-20) | 9,349,041 |
| of which 4-topic `Transfer` (ERC-721, not used) | 264,699 |
| of which `UserOperationEvent` | 94,438 |
| Blocks with at least one transaction | 21,532 of 21,534 (blocks 26332566 and 26334467 are empty on chain, checked) |

Raw Parquet size: 1.3 GB.

## Other inputs

| Input | Source | Fetched | Notes |
|---|---|---|---|
| Exchange PoR wallets | DefiLlama-Adapters @ `02aeae1` (one file per exchange) | 2026-11-11 | URLs, counts and SHA-256 of each list in `groundtruth/sources.json`; addresses not committed |
| Bitfinex cross-check | `bitfinexcom/pub` @ `83d06bd`, `wallets.txt` | 2026-11-11 | identical to the copied list |
| OFAC SDN list | sanctionslistservice.ofac.treas.gov, `SDN.XML` | 2026-11-11 | publish date 11/09/2026; 127 Ethereum-format addresses |
| EIP-7702 sweepers | `liziwei1/SweeperHunter` @ `b623678`, `dataset/` | 2026-11-11 | 508 contracts; `attack_results.csv` capped at 1,048,575 rows (see what-went-wrong) |
