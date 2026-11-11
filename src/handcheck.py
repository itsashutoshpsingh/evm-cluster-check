"""Explain individual false merges: the chain of links that joins two different exchanges.

For a sample of cross-exchange pairs that end up in one cluster, find the shortest chain of links
between them and classify the cause from the transactions on that chain. Output uses short
SHA-256 ids, never raw addresses. A local, git-ignored copy with raw addresses is written to
data/raw/handcheck_raw.csv for checking on a block explorer.
"""
import hashlib
import itertools

import networkx as nx
import pandas as pd

from src.heuristics import cospend, dar, funder


def hid(a):
    return hashlib.sha256(a.encode()).hexdigest()[:8]


def link_graph(w, tr, exch):
    """Graph of every link the 'all' rule plus naive DAR would use, with what created each link."""
    g = nx.Graph()
    p = dar.paths(tr, exch)
    for r in p.drop_duplicates(["vu", "vd"]).itertuples():
        g.add_edge(r.vu, r.vd, kind="dar", asset=r.asset, tx=r.tx1, ve=r.ve)
    lk = cospend.links(tr, w.eoas)
    # a co-spend link is a poisoning artefact when BOTH addresses' outgoing transfers in that tx are flagged
    t = tr[tr.kind == "erc20"]
    zero = set(t[t.poison_zero].groupby(["tx_hash", "src"]).size().index)
    look = set(t[t.poison_lookalike].groupby(["tx_hash", "src"]).size().index)
    for r in lk.itertuples():
        ka, kb = (r.tx_hash, r.a), (r.tx_hash, r.b)
        g.add_edge(r.a, r.b, kind="cospend", tx=r.tx_hash, zero=ka in zero and kb in zero,
                   lookalike=ka in look and kb in look)
    f = w.funding[w.funding.tx_hash.isin(set(tr.tx_hash))]
    for r in f.itertuples():
        g.add_edge(r.fresh, r.funder, kind="funder", tx=r.tx_hash)
    return g, set(p.vd)


def classify(path, g, labels, hubs, deposits):
    lab = dict(zip(labels.address, labels.exchange))
    kinds, causes = [], set()
    for x, y in zip(path, path[1:]):
        e = g[x][y]
        kinds.append(e["kind"])
        if e["kind"] == "cospend" and (e.get("zero") or e.get("lookalike")):
            causes.add("poisoning transfers in one transaction")
        if e["kind"] == "dar":
            user, dep = (x, y) if y in deposits else (y, x)
            if user in lab:
                causes.add("exchange wallet paid a deposit address (treated as a customer)")
            if dep in lab:
                causes.add("exchange-to-exchange transfer read as deposit forwarding")
        if e["kind"] == "funder" and (x in lab or y in lab):
            causes.add("exchange withdrawal read as gas funding")
    mids = path[1:-1]
    if any(m in hubs and m not in deposits for m in mids):
        causes.add("unlabelled high-degree hub on the chain")
    if any(m in lab for m in mids):
        causes.add("chain passes through a third exchange's wallet")
    return kinds, sorted(causes) or ["unexplained by these rules"]


def run(w, labels, n=20, seed=7):
    exch = set(labels.address)
    g, deposits = link_graph(w, w.tr, exch)
    lab = labels[labels.address.isin(g.nodes)]
    comp = {a: i for i, c in enumerate(nx.connected_components(g)) for a in c}
    lab = lab.assign(c=lab.address.map(comp))
    pairs = []
    for _, grp in lab.groupby("c"):
        for (a, ea), (b, eb) in itertools.combinations(zip(grp.address, grp.exchange), 2):
            if ea != eb:
                pairs.append((a, ea, b, eb))
    pairs = pd.DataFrame(pairs, columns=["a", "ea", "b", "eb"])
    # spread the sample over exchange pairs so one hub cluster does not supply all 20
    shuffled = pairs.sample(frac=1, random_state=seed)
    sample = shuffled.groupby(["ea", "eb"]).head(3).head(n)
    rows, raw = [], []
    for i, r in enumerate(sample.itertuples(), 1):
        path = nx.shortest_path(g, r.a, r.b)
        kinds, causes = classify(path, g, labels, w.hubs, deposits)
        rows.append({"case": i, "exchange_a": r.ea, "exchange_b": r.eb, "a_id": hid(r.a), "b_id": hid(r.b),
                     "hops": len(path) - 1, "link_kinds": " > ".join(kinds), "cause": "; ".join(causes),
                     "txs_on_chain": len({g[x][y]["tx"] for x, y in zip(path, path[1:])})})
        raw.append({"case": i, "path": " ".join(path), "txs": " ".join(g[x][y]["tx"] for x, y in zip(path, path[1:]))})
    out = pd.DataFrame(rows)
    pd.DataFrame(raw).to_csv("data/raw/handcheck_raw.csv", index=False)
    summary = {"cross_exchange_pairs_in_link_graph": int(len(pairs)), "sampled": int(len(out))}
    return out, summary


def evidence(w, labels):
    """Chainalysis-style split for every multi-address cluster of the combined rule.

    structural   links inferred from on-chain behaviour (DAR user->deposit, co-spend, funder)
    attribution  distinct exchange labels the clustering relied on (each DAR deposit needs one)
    operator     deposit addresses assumed to be operated by the exchange for a customer
    """
    exch = set(labels.address)
    g, deposits = link_graph(w, w.tr, exch)
    rows = []
    for c in nx.connected_components(g):
        if len(c) < 3:
            continue
        sub = g.subgraph(c)
        kinds = pd.Series([d["kind"] for _, _, d in sub.edges(data=True)]).value_counts()
        ves = {d["ve"] for _, _, d in sub.edges(data=True) if d["kind"] == "dar"}
        rows.append({"addresses": len(c), "structural_links": int(kinds.sum()),
                     "dar_links": int(kinds.get("dar", 0)), "cospend_links": int(kinds.get("cospend", 0)),
                     "funder_links": int(kinds.get("funder", 0)),
                     "attribution_claims": len(ves), "operator_claims": len(c & deposits),
                     "labelled_exchanges_inside": int(labels[labels.address.isin(c)].exchange.nunique())})
    return pd.DataFrame(rows)
