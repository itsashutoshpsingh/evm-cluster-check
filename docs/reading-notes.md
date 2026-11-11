# Reading notes

Read before writing any code. Each note says what the paper does, what I take from it, and what it leaves open.

## 1. Victor, "Address Clustering Heuristics for Ethereum" (Financial Cryptography 2020)

Source read: the FC 2020 pre-proceedings PDF (ifca.ai/fc20/preproceedings/31.pdf).

Three rules: deposit-address reuse (DAR), airdrop multi-participation, and self-authorization (an `approve` to an address you also control). DAR is the one that matters in practice. Exchanges give each customer a deposit address that forwards to a main wallet. So if two addresses pay the same deposit address, they are probably one customer.

Algorithm 1 defines it precisely. It looks for a path `vu -> vd -> ve` where:
- `ve` is a known exchange address;
- both hops move the same asset;
- the received minus forwarded amount is in `[0, amax]`;
- the forward happens within `tmax` blocks.

Exclusions: `vu` must not be an exchange or a miner, `vd` must not be an exchange, and `vd` must forward to a single exchange address. Weakly connected components give the clusters, and deposit addresses are then removed from the user clusters.

Parameters were estimated empirically. Victor first ran with `tmax` = 10,000 blocks and `amax` = 1 ETH. The 95th percentiles came out at `amax` = 0.0083 ETH and `tmax` = 3,185 blocks, so he reran with `amax` = 0.01 ETH and `tmax` = 3,200. For tokens `amax` is 0.

Headline numbers on the full history to 2020:
- 6,670,392 deposit addresses.
- 3,261,091 addresses used a deposit address, and 1,446,715 (44.3%) shared one with another account.
- 333,107 multi-address entities.
- Four entities with more than 1,000 addresses were "ignored" as implausible.

**What I take:** Algorithm 1 verbatim as `dar_victor`, the same parameters, and the 1,000-address cap.

**What it leaves open:** there is no error rate against ground truth. Victor's own limitations paragraph describes a rogue forwarder that pays an exchange whatever it receives and so gets treated as a deposit address. I reproduce that attack in the injected tests (S2).

## 2. Wu et al., "Tutela" (arXiv 2201.06811)

An open-source Ethereum and Tornado Cash privacy tool. It implements DAR with the exchange list taken from a public Kaggle label set. It adds a confidence score that decays with the amount and time differences, plus a node-embedding rule (Diff2Vec).

Result: 26M EOAs in 2.5M DAR clusters, mean size 4.3 (± 8.6), largest cluster 2.1k addresses. Against a held-out test set of 1,028 ENS-derived clusters, DAR recall is 39.4%, and 44.8% combined with the embedding.

**What I take:** Tutela reports recall only. A precision or false-merge figure is exactly what is missing. Its test set comes from ENS names, which tells you whether one user's addresses are found, not whether two users are wrongly joined.

**What it leaves open:** precision and false merges. That is this repository's question.

## 3. Müller et al., "How Reliable Is the Multi-Input Heuristic for Bitcoin Address Clustering in Law Enforcement Contexts?" (arXiv 2607.07414)

This paper evaluates Bitcoin's multi-input heuristic against address-to-entity ground truth from European service providers under legal reporting duties. It reimplements nine metrics that earlier studies reported only piecemeal:

- **Pairwise precision, recall and F1** on the labelled domain only.
- **Per-wallet precision, recall and F1**, following Nick. For each labelled seed address, how pure and how complete the full computed cluster is. The seed itself is excluded, so a singleton recovers nothing. Results are macro-averaged over entities.
- **NMI and aNMI** (geometric, Vinh's adjustment) on the labelled domain.
- **AER**, a one-to-best coverage error per entity.

Key result: pairwise precision is 1.0, yet per-wallet precision is 0.36 and recall 0.44, because clusters absorb unlabelled addresses. Some services fail almost completely.

**What I take:** the exact metric definitions (`src/score.py`). Results are reported per metric family, so Ethereum numbers here can sit next to theirs. The paper also gives the main warning for this project: pairwise scores on labelled data alone can look perfect while full clusters are contaminated.

**What it leaves open:** account-model chains. Their ground truth is not public; mine has to be.

## 4. Tsuchiya et al., "Blockchain Address Poisoning" (USENIX Security 2025; arXiv 2501.16681)

Two years of Ethereum and BSC data: 270M poisoning attempts against 17M victims, and at least $83.8M lost. There are three transfer types:
- **tiny transfers**, from a look-alike address to the victim;
- **zero-value transfers**, a `transferFrom(victim, lookalike, 0)` that the victim never signed but that shows up in their history;
- **counterfeit-token transfers.**

Look-alike detection compares each recently used counterparty with addresses the victim really paid. It needs a prefix match of at least 3 and a suffix match of at least 4 hex characters (case-insensitive). Victims with so many counterparties that chance matches become likely are excluded. Attackers bundle more than 100 poisoning transfers into one transaction.

**What I take:** the zero-value rule and the a≥3, b≥4 look-alike rule (`src/infra_labels.py`). I also take the observation that one transaction can carry spoofed transfers "from" many victims. That is exactly the input a same-sender-in-transaction rule uses to link addresses.

**What it leaves open:** the counterfeit-token list. They used Etherscan reputation and Coinranking lists, and I don't have an Etherscan key. I therefore label counterfeit transfers only when they also involve a look-alike address.

## 5. Chainalysis, "Defining the Cluster: A Formal Ontology for Blockchain Address Analysis and Intelligence Claims" (June 2026)

Source read: the report landing page, plus the summary of the three claims quoted in the companion post "Machine Learning Has a Specific Role in Blockchain Intelligence". The full report sits behind a contact form, and I did not submit it, so these notes rest on the public summary only.

The report splits "cluster" into three claims:
- **structural:** these addresses are controlled by the same key or party;
- **attribution:** this address belongs to this named entity;
- **operator:** this entity's relationship to the address, e.g. an exchange operating a deposit address for a customer.

Structural claims "must be deterministic and reproducible". Attribution and intelligence claims need explicit source characterisation and confidence levels.

**What I take:** the three-way split, used to label every link in the evidence breakdown (`results/evidence_breakdown_eth.csv`). Applied to these rules:
- a DAR link is a structural inference;
- the exchange label that makes a deposit address a deposit address is attribution;
- treating the deposit address as the exchange's, not the customer's, is an operator claim.

**What it leaves open:** any error profile. The industry says claims need one, and this repository measures one for open rules only. It is not a measurement of any vendor's product.

## Also read

- **Li et al., "Who Swept My ETH?"** (arXiv 2610.41153, SweeperHunter). The authors released `ETH_sweeper_contracts.csv` (508 contracts) and `attack_results.csv` at commit `b623678`; I use only these. `attack_results.csv` holds exactly 1,048,575 data rows, the Excel row limit, so it is very likely truncated. I use it only as a victim list and say so.
- **"On-Chain Behavioral Signatures for Classifying CEX Addresses Using Proof-of-Reserves"** (arXiv 2610.41888). Its 3,033,857 PoR-labelled addresses from 15 exchanges would be far better ground truth than mine. Their repository (dunamu-labs/cex-address-classification) releases only a feature dataset on request, not the address list, so I could not use it. Its `docs/data_sources.md` was still useful as a list of where each exchange publishes PoR addresses.
