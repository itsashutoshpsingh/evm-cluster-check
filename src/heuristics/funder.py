"""Common gas funder.

A fresh EOA is one whose first-ever transaction (nonce 0) falls inside the window. Its funder
is the sender of the last ETH transfer it received before that first transaction. Fresh EOAs
with the same funder are linked to each other and to the funder.

Variants:
  naive       - as above
  hubfiltered - ignore funders that funded more than `hub_k` fresh EOAs in the window
  aa_sponsor  - naive, plus ERC-4337 smart accounts first seen in the window are linked to the
                paymaster that sponsored their first UserOperation (an analyst reading
                "who paid the gas" on an explorer would see the paymaster or bundler)
"""
import pandas as pd

from src.cluster import components
from src.edges import ZERO


def funding(txs, tr):
    """DataFrame fresh, funder, block, tx_hash (funding transfer)."""
    first = txs[txs.nonce == 0][["from", "block", "tx_index"]].drop_duplicates("from")
    first = first.rename(columns={"from": "fresh", "block": "fb", "tx_index": "fi"})
    eth = tr[tr.kind == "eth"].merge(txs[["hash", "tx_index"]], left_on="tx_hash", right_on="hash")
    m = eth.merge(first, left_on="dst", right_on="fresh")
    m = m[(m.block < m.fb) | ((m.block == m.fb) & (m.tx_index < m.fi))]
    m = m.sort_values(["block", "tx_index"]).drop_duplicates("fresh", keep="last")
    return m[["fresh", "src", "block", "tx_hash"]].rename(columns={"src": "funder"}).reset_index(drop=True)


def clusters(f, variant="naive", hub_k=20, uo=None):
    f = f[f.fresh != f.funder]
    if variant == "hubfiltered":
        n = f.funder.value_counts()
        f = f[f.funder.isin(n[n <= hub_k].index)]
    links = f.rename(columns={"fresh": "a", "funder": "b"})[["a", "b"]]
    if variant == "aa_sponsor" and uo is not None:
        sp = uo[uo.paymaster != ZERO].drop_duplicates("sender")
        links = pd.concat([links, sp.rename(columns={"sender": "a", "paymaster": "b"})[["a", "b"]]])
    return components(links.drop_duplicates()), links
