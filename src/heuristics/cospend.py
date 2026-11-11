"""Same-sender-in-transaction ("co-spend", the account-model cousin of Bitcoin's multi-input rule).

If one transaction moves ERC-20 tokens out of several externally owned accounts, the rule
assumes one party controlled all of them (it held their approvals or keys) and links them.
Only addresses that also sign transactions somewhere in the window are treated as EOAs, so
pools and routers that appear as token senders are left out.

This is exactly the pattern a zero-value poisoning batch produces: one attacker transaction
emits Transfer events "from" many unrelated victims.
"""
import pandas as pd

from src.cluster import components


def links(tr, eoas, min_n=2):
    t = tr[(tr.kind == "erc20") & tr.src.isin(eoas)][["tx_hash", "src"]].drop_duplicates()
    n = t.groupby("tx_hash").src.transform("size")
    t = t[n >= min_n]
    head = t.drop_duplicates("tx_hash").rename(columns={"src": "b"})
    return t.merge(head, on="tx_hash").rename(columns={"src": "a"})[["a", "b", "tx_hash"]]


def clusters(lk, drop_txs=()):
    lk = lk[~lk.tx_hash.isin(set(drop_txs))]
    return components(lk[["a", "b"]].drop_duplicates())
