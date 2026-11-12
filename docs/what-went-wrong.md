# What went wrong

The misses, dead ends and limits of this project, in the order I hit them. Each one says what it does to the numbers.

## Data collection

1. **One provider for Ethereum logs.**
   - `ethereum-rpc.publicnode.com` refuses `eth_getLogs` on blocks more than about 128 behind the head ("Archive requests require a personal token").
   - `1rpc.io` refuses the method outright.
   - Only `eth.drpc.org` served the logs, so every ERC-20 transfer in this study comes from a single provider with no second source to compare against.
   - The companion project `chain-evidence` exists to check exactly this. Its cross-check on this window is reported in its own repository.
2. **1rpc.io hit a daily cap** after roughly 2,000 calls ("You've reached the usage limit for your current plan"). I removed it from the block providers. Blocks came from publicnode and drpc only.
3. **mainnet.base.org rate-limited within a few calls**, and publicnode's Base endpoint refuses `eth_getLogs` without an address filter. Base logs were taken from `eth_getBlockReceipts` instead. That call happens to also give transaction status, so Base data is cleaner than Ethereum data on point 5.
4. **I restarted the Ethereum fetch four times in the first ten minutes.** Each time I realised a field was missing: the nonce (needed for "fresh" addresses), the block fee recipient (Victor excludes miners), the paymaster topic of `UserOperationEvent`, and the full EIP-7702 authorisation tuples (needed to recover who delegated). The lesson is to decide the schema from the rules before fetching anything.
5. **No transaction status on Ethereum.** Block bodies carry no status. A value transfer from a transaction that later reverted is counted as if it happened. Simple ETH transfers between EOAs essentially never revert, but transfers into contracts can.
6. **No internal transfers.** ETH moved by contract code (traces) is invisible to every rule here, which has three effects:
   - Contract deposit addresses that forward automatically are missed by deposit-address reuse.
   - EIP-7702 sweeps are missed too. The injected test S7 shows the transfer table crediting 0.1 ETH to a swept wallet whose balance did not change.
   - Haircut taint does not follow those flows.

   BigQuery's `traces` table would fix all three.

## Ground truth

7. **Binance and Bitstamp are missing.** Their DefiLlama adapters fetch addresses at run time from the exchange's own site, which this environment could not reach.
   - Binance is the largest exchange on Ethereum. Its wallets are therefore in the data as unlabelled addresses.
   - This makes false merges *harder* to detect, not easier. Every number here is a lower bound on what a complete label set would show.
8. **The PoR lists are copies.** Only Bitfinex could be checked against a list the exchange publishes itself (identical, 4 addresses). The other lists are as good as DefiLlama's copying of each exchange's PoR page. A shared custodian could in principle appear on two exchanges' lists. No address did, but that does not prove no custodian is shared.
9. **The 3-million-address PoR dataset of arXiv 2610.41888 is not public.** The authors release only a feature table, on request. It would have given ground truth for 15 exchanges.

## Other inputs

10. **SweeperHunter's `attack_results.csv` has exactly 1,048,575 data rows,** which is Excel's row limit, so it was almost certainly truncated when exported. I use it only as a list of victims and collectors and treat that list as incomplete.
11. **No counterfeit-token list.** Tsuchiya et al. separate genuine from counterfeit tokens using Etherscan reputation and Coinranking. I have no Etherscan key, so counterfeit-token poisoning is caught only when it also involves a look-alike address.
12. **OFAC's list is mostly dormant on chain.** See the taint results in the README for how many of the 127 listed Ethereum addresses were active in the window. I added SweeperHunter's attacker collector addresses as a second seed set so the taint rule had something to propagate from.
13. **The anvil fork is at the latest block, not inside the study window.** Forking at a past block needs archive state, and the free endpoints refuse that without a token. This does not matter for the injected tests, which only need real contracts (USDT, Multicall3) to exist.

## Method

14. **NMI rewards doing nothing.** A rule that links nothing leaves every labelled address as a singleton, and geometric NMI is still about 0.5, because the singleton partition "explains" the exchange labels. aNMI corrects for this and sits near 0. Read the metrics table with that in mind; it is the same caution Müller et al. raise.
15. **Victor's 1,000-address cap hides the worst merges.** `dar_victor` drops clusters with more than 1,000 addresses, exactly as published. Those are the clusters most likely to contain two exchanges. Its low false-merge count is partly this cap at work. The `naive` variant shows what the cap removes.
16. **Three days is short.** Victor's `tmax` of 3,200 blocks is about 10.7 hours, so a deposit made in the last 10 hours of the window can be missed. The bootstrap interval covers day-to-day variation in this window only, not seasonality.
17. **The hub threshold (1,000 distinct counterparties in the window) is my choice,** not taken from a paper. It is reported as a separate variant, never folded into the main number.
18. **Full-history reproduction of Victor and Tutela was not possible.** They ran on every block since 2015, and three days cannot reproduce cluster counts. What I could reproduce is Victor's parameter estimation and the share of deposit users who share a deposit address (`results/reproduce_eth.json`). The numbers agree in some respects and not others, and the README says which.

19. **The taint stage ran the machine out of memory.** It built four full copies of the 11-million-row transfer table at once, one per edge variant. The process was killed and took the whole working environment down with it, losing the in-progress run. It now keeps one three-column copy and filters it per variant, and every stage resumes from its saved output.
20. **The 20 "hand-checks" were classified by script.** `handcheck.py` follows each sampled link chain and labels it from the transactions on it. I did not open each case on a block explorer and judge it by eye, which the plan called for. Two chains came out as "unexplained by these rules" and need that manual look.

## What I would do with more access

- **BigQuery** (`bigquery-public-data.crypto_ethereum`): two months instead of three days, plus internal transfers from `traces` and transaction status from `receipts`.
- **An Etherscan key:** the token reputation list for counterfeit-token poisoning.
- **The 2610.41888 address list:** ground truth for 15 exchanges instead of 9.
