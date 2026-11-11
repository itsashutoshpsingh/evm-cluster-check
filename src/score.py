"""Clustering metrics against exchange ground truth.

The nine metrics follow Müller et al. (arXiv 2607.07414): pairwise precision/recall/F1 and NMI/aNMI
on the labelled domain; per-wallet precision/recall/F1 (macro-averaged over entities, seed excluded,
computed on the full clusters including unlabelled addresses) and AER (one-to-best coverage error).

Plus the number this project is about: false merges, i.e. clusters holding addresses that the
ground truth puts in two different exchanges.

`clusters`: Series address -> cluster id for linked addresses. Labelled addresses missing from it
are singletons. `labels`: DataFrame address, exchange (restricted to the labels being evaluated).
"""
from math import comb

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_mutual_info_score, normalized_mutual_info_score


def assign(clusters, labels):
    """Cluster id for every labelled address; singletons get unique negative ids."""
    c = labels.address.map(clusters)
    single = c.isna()
    c[single] = -np.arange(1, single.sum() + 1)
    return c.astype("int64").to_numpy()


def pairwise(c, y):
    t = pd.crosstab(c, y)
    tp = sum(comb(int(v), 2) for v in t.to_numpy().ravel())
    pred = sum(comb(int(v), 2) for v in t.sum(axis=1))
    true = sum(comb(int(v), 2) for v in t.sum(axis=0))
    p = tp / pred if pred else float("nan")
    r = tp / true if true else float("nan")
    f = 2 * p * r / (p + r) if pred and true and (p + r) else float("nan")
    return p, r, f, tp, pred - tp


def per_wallet(clusters, labels):
    size = clusters.value_counts()
    c = assign(clusters, labels)
    lab = labels.assign(c=c)
    same = lab.groupby(["c", "exchange"]).size()
    ent_size = lab.groupby("exchange").size()
    rows = []
    for a, ex, ci in zip(lab.address, lab.exchange, lab.c):
        others = (size.get(ci, 1) if ci >= 0 else 1) - 1
        hit = same[(ci, ex)] - 1
        prec = hit / others if others else 0.0  # seed excluded; a singleton recovers nothing
        rec = hit / (ent_size[ex] - 1) if ent_size[ex] > 1 else float("nan")
        rows.append((ex, prec, rec))
    d = pd.DataFrame(rows, columns=["exchange", "p", "r"]).groupby("exchange").mean()
    d["f1"] = 2 * d.p * d.r / (d.p + d.r)
    d["f1"] = d.f1.fillna(0.0)
    return d


def aer(c, y):
    t = pd.crosstab(y, c)
    return float((1 - t.max(axis=1) / t.sum(axis=1)).mean())


def false_merges(clusters, labels):
    c = assign(clusters, labels)
    lab = labels.assign(c=c)
    g = lab[lab.c >= 0].groupby("c").exchange.agg(["nunique", "size"])
    bad = g[g["nunique"] > 1]
    t = pd.crosstab(lab.c, lab.exchange)
    t = t[t.index >= 0]
    cross_pairs = int(sum(comb(int(n), 2) - sum(comb(int(v), 2) for v in row) for n, row in zip(t.sum(axis=1), t.to_numpy())))
    exch_pairs = set()
    for _, row in t.iterrows():
        ex = sorted(row[row > 0].index)
        exch_pairs |= {(a, b) for i, a in enumerate(ex) for b in ex[i + 1:]}
    return {"clusters_with_2plus_exchanges": int(len(bad)), "cross_exchange_pairs_linked": cross_pairs,
            "distinct_exchange_pairs_merged": len(exch_pairs), "bad_cluster_ids": list(bad.index)}


def evaluate(clusters, labels):
    c = assign(clusters, labels)
    y = labels.exchange.to_numpy()
    p, r, f, tp, fp = pairwise(c, y)
    pw = per_wallet(clusters, labels)
    fm = false_merges(clusters, labels)
    return {
        "labelled": len(labels), "labelled_linked": int((c >= 0).sum()),
        "pair_precision": p, "pair_recall": r, "pair_f1": f, "pairs_true_linked": tp, "pairs_false_linked": fp,
        "pw_precision": float(pw.p.mean()), "pw_recall": float(pw.r.mean()), "pw_f1": float(pw.f1.mean()),
        "nmi": float(normalized_mutual_info_score(y, c, average_method="geometric")),
        "anmi": float(adjusted_mutual_info_score(y, c, average_method="geometric")),
        "aer": aer(c, y),
        **{k: v for k, v in fm.items() if k != "bad_cluster_ids"},
    }
