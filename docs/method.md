# Method

Every rule, threshold and metric is defined below exactly as the code runs it. File references are to `src/`.

## 1. Data (`fetch.py`, `edges.py`)

| Item | Ethereum | Base |
|---|---|---|
| Window | 2026-11-01 00:00 to 2026-11-03 23:59:59 UTC | 2026-11-01 00:00 to 05:59:59 UTC |
| Blocks | 26,316,189 – 26,337,722 (21,534) | 53,350,927 – 53,361,726 (10,800) |
| Transactions | `eth_getBlockByNumber(n, true)` | same |
| Logs | `eth_getLogs`, topic0 ∈ {ERC-20 `Transfer`, ERC-4337 `UserOperationEvent`}, 5 blocks per call | `eth_getBlockReceipts`, filtered to the same two topics |
| Providers | ethereum-rpc.publicnode.com and eth.drpc.org for blocks; eth.drpc.org for logs | base-rpc.publicnode.com |

A chunk of 100 blocks is written only when every call in it succeeded. Any error (rate limit, timeout, null result) is retried with back-off on the next provider. A provider hiccup therefore cannot turn into missing data. The only possible outcomes are complete data or a run that stops.

**Transfers** (`edges.transfers`):
- every transaction with value > 0 and a recipient, as an ETH transfer;
- every 3-topic `Transfer` log (ERC-20; 4-topic logs are ERC-721 and are skipped).

Self-transfers are dropped. Amounts keep the exact integer (`raw`) alongside a float.

**Not included:**
- Internal ETH transfers made by contracts. These need `trace_*`/`debug_*` calls that free endpoints do not serve.
- Ethereum transaction status: the block body has none. On Base, reverted transactions are dropped using receipts. On Ethereum, a value transfer from a reverted transaction stays in the data (see what-went-wrong.md).

## 2. Ground truth (`groundtruth.py`)

Exchange proof-of-reserves wallet lists, as copied into the DefiLlama-Adapters repository at commit `02aeae1`:
- one file per exchange;
- the `owners` array of the `ethereum` (or `base`) section;
- for Bitget, the shared `evmOwners` list.

| Exchange | Ethereum addresses | Base addresses |
|---|---|---|
| OKX | 238 | 4 |
| Bitget | 83 | 83 |
| KuCoin | 61 | 10 |
| HTX | 36 | – |
| CoinEx | 14 | – |
| Gate | 9 | – |
| Gemini | 5 | – |
| Bitfinex | 4 | – |
| Bitrue | 2 | – |
| **Total** | **452** | **97** |

- **Same owner:** two addresses on one exchange's list.
- **Different owner:** two addresses on two exchanges' lists.

An address on two lists would be dropped; none was. Bitfinex's copied list was checked against the list Bitfinex publishes itself (`bitfinexcom/pub/wallets.txt`) and is identical.

Binance and Bitstamp could not be used. Their adapters fetch addresses at run time from the exchange's site, which this environment cannot reach. Binance wallets are therefore present in the data as **unlabelled** exchange wallets. This is realistic, because every label set has gaps, and it matters for the results.

## 3. Rules

All rules output links between addresses. Clusters are the connected components of those links (`cluster.py`).

### Deposit-address reuse (`heuristics/dar.py`), Victor 2020 Algorithm 1

A path `vu → vd → ve` where:
- `ve` is a known exchange address;
- both hops move the same asset;
- `e1.amount − e2.amount ∈ [0, amax]`, with `amax` = 0.01 ETH for ETH and 0 (exact forward) for tokens;
- `e2.block − e1.block ∈ [0, 3200]`.

`vd` is then a deposit address and `vu` is linked to it. Deposit addresses are removed from the user clusters afterwards.

| Variant | Extra conditions |
|---|---|
| `dar_naive` | none |
| `dar_victor` | as published: `vu` not an exchange address and not a block fee recipient; `vd` not an exchange address; `vd` forwards to exactly one exchange address; clusters > 1,000 addresses dropped |
| `dar_hubfiltered` | `dar_victor`, plus drop any `vu` that used more than 10 deposit addresses in the window (a service hot wallet behaves this way; a person rarely does) |

### Common gas funder (`heuristics/funder.py`)

A fresh EOA is one whose nonce-0 transaction falls in the window. Its funder is the sender of the last ETH transfer it received before that transaction. Fresh EOAs are linked to their funder.

| Variant | Extra conditions |
|---|---|
| `funder_naive` | none |
| `funder_hubfiltered` | funders of more than 20 fresh EOAs are ignored |
| `funder_aa_sponsor` | ERC-4337 smart accounts are also linked to the paymaster of their first sponsored UserOperation in the window |

### Same-sender-in-transaction (`heuristics/cospend.py`)

If one transaction moves ERC-20 tokens out of two or more addresses that also sign transactions somewhere in the window (a proxy for EOA), those addresses are linked. This is the closest account-model analogue of Bitcoin's multi-input rule.

### Combined (`all`)

The union of the `dar_victor`, `funder_aa_sponsor` and same-sender-in-transaction links.

## 4. Infrastructure labels (`infra_labels.py`)

| Label | Definition |
|---|---|
| `poison_zero` | ERC-20 transfer of value 0 |
| `poison_lookalike` | Transfer between account V and address L, where V earlier paid an address R that shares L's first 3 and last 4 hex characters (Tsuchiya et al.'s a≥3, b≥4). L ≠ R, L first seen after R, and V has ≤ 2,000 counterparties |
| `sweeper` | Transfer touching any of: one of the 508 sweeper contracts released with SweeperHunter (commit `b623678`); a victim listed in its `attack_results.csv`; an account seen in this window signing an EIP-7702 authorization to such a contract (authority recovered from the signed tuple) |
| `aa_infra` | Transfer touching an ERC-4337 EntryPoint (v0.6, v0.7, v0.8), a bundler (sender of a transaction to an EntryPoint, or the outer sender of a `UserOperationEvent`) or a paymaster |

**Infrastructure attribution:** each rule is re-run with one class of labelled transfers removed. The share of false merges that disappear is attributed to that class.

## 5. Metrics (`score.py`)

"False merges", the headline, is the number of **pairs of exchange wallets from two different exchanges that end up in one cluster**. The nine metrics of Müller et al. 2026 are also reported:

| Metric | Computed on | Definition |
|---|---|---|
| Pairwise P / R / F1 | labelled domain | same-cluster decisions on labelled pairs |
| Per-wallet P / R / F1 | full clusters | per labelled seed, excluding the seed; singletons score 0 precision; macro-averaged over exchanges |
| NMI / aNMI | labelled domain | geometric normalisation; aNMI with Vinh's chance correction (scikit-learn) |
| AER | labelled → clusters | mean over exchanges of 1 − (largest share of the exchange in one cluster) |

The labelled domain is the PoR addresses that are active (send or receive) in the window.

## 6. Two reporting axes

**Hubs.** Every number appears twice:
- `included`: as is;
- `excluded`: all transfers touching an address with ≥ 1,000 distinct counterparties in the window are removed first. Exchange hot wallets and big routers are such hubs.

**Label protocol.**
- `full`: the rule knows every PoR address, which is used both as `ve` and for the exclusions, and is scored on all of them.
- `split50`: in each of 10 random splits, the rule knows a random half of each exchange's addresses and is scored on the other half. This mimics the real situation, where an analyst's exchange labels are incomplete.

## 7. Taint (`taint.py`)

Sources are the 127 Ethereum-format addresses in OFAC's SDN list, published 11/09/2026.

- **n-hop:** time-respecting. An address is tainted at hop k from the first block it receives anything from a hop k−1 address, and only via transfers at or after that address's own taint block.
- **Haircut:** ETH only. Each address carries the share of its in-window ETH received from tainted addresses.

Both are run with all transfers, then without zero-value transfers, without any poisoning transfers, and without any infrastructure transfers.

## 8. Uncertainty

The window is cut into 12 six-hour segments. Each of 200 bootstrap samples draws 12 segments with replacement; segments drawn twice add nothing new to a graph. The full rule is recomputed on each sample, and the 2.5–97.5 percentile range is reported. With 3 days of data this captures day-to-day variation, not long-run variation. The per-day table shows the same thing directly.

## 9. Hand-checks (`handcheck.py`)

For 20 cross-exchange pairs drawn across exchange pairs (at most 3 per exchange pair, fixed seed), the shortest chain of links between the two wallets is extracted. The chain uses the union of naive DAR, same-sender and gas-funder links. Each hop is then classified from what created it. The committed file uses SHA-256 prefixes of addresses. A raw copy for block-explorer checks stays in the git-ignored `data/raw/`.

## 10. Injected ground truth (`anvil/`)

These scenarios run on a local Foundry `anvil` fork of mainnet and stay on the machine. The wallets are derived from fixed seeds, so every owner is known. Each scenario is a real transaction on the fork (see `anvil/inject.py` for S1–S7). These results are synthetic and are reported separately from the mainnet ones.
