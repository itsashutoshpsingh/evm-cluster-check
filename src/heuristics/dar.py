"""Deposit-address reuse (Victor 2020, Algorithm 1).

A path vu -> vd -> ve where ve is a known exchange address, both hops move the same asset,
the forwarded amount is at most `amax` less than the received amount, and the forward happens
within `tmax` blocks, marks vd as a deposit address. Addresses that used the same deposit address
are clustered; the deposit addresses themselves are then removed from the user clusters.

Three variants are exposed:
  naive         - only the path test; no sender exclusions, no single-target rule, no size cap
  victor        - as published: vu not an exchange or block producer, vd not an exchange,
                  vd forwards to exactly one exchange address, clusters > 1,000 addresses ignored
  hubfiltered   - victor, plus drop senders that used more than `hub_k` deposit addresses
                  (unlabelled service hot wallets behave like this)
"""
import pandas as pd

from src.cluster import cap, components

AMAX_ETH = 0.01     # Victor's 95th-percentile fee difference
AMAX_TOKEN = 0      # tokens cannot pay their own fee, so forwards are exact
TMAX = 3200         # blocks (~10.7 h at 12 s slots; Victor measured 3,185 at the 95th percentile)


def paths(tr, exch, tmax=TMAX, amax=AMAX_ETH):
    """All (vu, vd, ve, asset, b1, b2, tx1) forwarding paths satisfying the amount and time tests."""
    e2 = tr[tr.dst.isin(exch) & ~tr.src.isin(exch)]
    e1 = tr[tr.dst.isin(set(e2.src))]
    out = []
    # tokens: exact forward -> join on equal raw amount
    t1, t2 = e1[e1.kind == "erc20"], e2[e2.kind == "erc20"]
    m = t1.merge(t2, left_on=["dst", "asset", "raw"], right_on=["src", "asset", "raw"], suffixes=("_1", "_2"))
    out.append(m)
    # ETH: e1 - e2 in [0, amax]; bucket by amax so the join stays small
    x1, x2 = e1[e1.kind == "eth"].copy(), e2[e2.kind == "eth"].copy()
    x1["bk"] = (x1.amount // amax).astype("int64")
    x2["bk"] = (x2.amount // amax).astype("int64")
    for shift in (0, 1):
        y2 = x2.assign(bk=x2.bk + shift)
        m = x1.merge(y2, left_on=["dst", "asset", "bk"], right_on=["src", "asset", "bk"], suffixes=("_1", "_2"))
        d = m.amount_1 - m.amount_2
        out.append(m[(d >= 0) & (d <= amax)])
    m = pd.concat(out, ignore_index=True)
    db = m.block_2 - m.block_1
    m = m[(db >= 0) & (db <= tmax)]
    return pd.DataFrame({
        "vu": m.src_1, "vd": m.dst_1, "ve": m.dst_2, "asset": m.asset,
        "b1": m.block_1, "b2": m.block_2, "tx1": m.tx_hash_1, "li1": m.log_index_1, "tx2": m.tx_hash_2, "li2": m.log_index_2, "raw1": m.raw_1,
        "a1": m.amount_1, "a2": m.amount_2,
    }).drop_duplicates(["vu", "vd", "ve", "tx1", "li1"]).reset_index(drop=True)


def restrict(p, tr, exch):
    """Paths that `paths(tr, exch)` would return, given p = paths(T, E) with tr a subset of T, exch of E."""
    keep = pd.MultiIndex.from_arrays([tr.tx_hash, tr.log_index])
    ok = pd.MultiIndex.from_arrays([p.tx1, p.li1]).isin(keep) & pd.MultiIndex.from_arrays([p.tx2, p.li2]).isin(keep)
    return p[ok & p.ve.isin(exch) & ~p.vd.isin(exch)]


def clusters(p, variant="victor", exch=(), miners=(), hub_k=10, max_size=1000):
    """Return (Series address->cluster, set of deposit addresses, the user->deposit link pairs used)."""
    p = p[p.vu != p.vd]
    if variant in ("victor", "hubfiltered"):
        p = p[~p.vu.isin(set(exch) | set(miners)) & ~p.vd.isin(set(exch))]
        n_targets = p.groupby("vd").ve.nunique()
        p = p[p.vd.isin(n_targets[n_targets == 1].index)]
    if variant == "hubfiltered":
        n_dep = p.groupby("vu").vd.nunique()
        p = p[p.vu.isin(n_dep[n_dep <= hub_k].index)]
    links = p[["vu", "vd"]].drop_duplicates().rename(columns={"vu": "a", "vd": "b"})
    deposits = set(p.vd)
    s = components(links, drop=deposits)
    if variant in ("victor", "hubfiltered"):
        s = cap(s, max_size)
    return s, deposits, p
