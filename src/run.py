"""Run every rule on one chain's window and write results/*.csv|json.

python -m src.run --chain eth [--blocks START END] [--splits 10]
"""
import argparse
import json
import os
import time

import numpy as np
import pandas as pd

from src import edges, groundtruth, handcheck, score, taint
from src.cluster import components
from src.heuristics import cospend, dar, funder
from src.infra_labels import label

SWEEPERS = "data/raw/sweeperhunter/ETH_sweeper_contracts.csv"
VICTIMS = "data/raw/sweeperhunter/attack_results.csv"
HUB_DEGREE = 1000  # an address with this many distinct counterparties in the window is a hub
INFRA = {"poisoning": ["poison_zero", "poison_lookalike"], "sweeper": ["sweeper"], "aa_bundler_paymaster": ["aa_infra"]}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


class Window:
    """Everything one evaluation needs, built once per chain."""

    def __init__(self, chain, blocks=None):
        cache = f"data/raw/cache/{chain}_{blocks[0]}_{blocks[1]}" if blocks else f"data/raw/cache/{chain}"
        if os.path.exists(f"{cache}/meta.json"):  # labelled tables from an earlier run of the same window
            self.txs, self.tr, self.uo, self.funding = (pd.read_parquet(f"{cache}/{n}.parquet") for n in ("txs", "tr", "uo", "funding"))
            meta = json.load(open(f"{cache}/meta.json"))
            self.n_logs, self.infra_info, self.hubs = meta["n_logs"], meta["infra_info"], set(meta["hubs"])
        else:
            self.txs, tr, self.uo, self.n_logs = edges.load(chain, blocks)
            tr, self.infra_info, _ = label(tr, self.txs, self.uo, SWEEPERS, VICTIMS if os.path.exists(VICTIMS) else None)
            tr["infra_any"] = tr[[c for v in INFRA.values() for c in v]].any(axis=1)
            self.tr = tr
            lo, hi = np.minimum(tr.src.to_numpy(object), tr.dst.to_numpy(object)), np.maximum(tr.src.to_numpy(object), tr.dst.to_numpy(object))
            u = pd.DataFrame({"a": lo, "b": hi}).drop_duplicates()  # undirected pairs, so each counterparty counts once
            deg = pd.concat([u.a, u.b]).value_counts()
            del lo, hi, u
            self.hubs = set(deg[deg >= HUB_DEGREE].index)
            self.funding = funder.funding(self.txs, tr)
            os.makedirs(cache, exist_ok=True)
            for n in ("txs", "tr", "uo", "funding"):
                getattr(self, n).to_parquet(f"{cache}/{n}.parquet")
            json.dump({"n_logs": self.n_logs, "infra_info": self.infra_info, "hubs": sorted(self.hubs)}, open(f"{cache}/meta.json", "w"))
        self.miners = set(self.txs.miner)
        self.eoas = set(self.txs["from"])
        self.active = set(self.tr.src) | set(self.tr.dst)
        self.memo = {}


def dar_paths(w, tr, exch):
    """DAR paths for (tr, exch), computed once on the full window and then restricted."""
    exch = set(exch)
    if not hasattr(w, "dar_all") or not exch <= w.dar_exch:
        w.dar_exch = exch | getattr(w, "dar_exch", set())
        w.dar_all = dar.paths(w.tr, w.dar_exch)
    if tr is w.tr and exch == w.dar_exch:
        return w.dar_all
    return dar.restrict(w.dar_all, tr, exch)


def rule_links(w, tr, rule, exch, drop_aa=False):
    """(clusters, link pairs a,b, addresses dropped after linking) for one rule on transfers `tr`.

    drop_aa: also drop links that come from ERC-4337 UserOperation events (sponsor links).
    """
    if rule.startswith("dar_"):
        p = dar_paths(w, tr, exch)
        variant = rule[4:]
        s, deps, used = dar.clusters(p, variant, exch=exch, miners=w.miners)
        return s, used.rename(columns={"vu": "a", "vd": "b"})[["a", "b"]], deps
    if rule.startswith(("funder_", "cospend")):
        # these rules ignore the exchange labels, so reuse them across label splits of the same transfers
        which = "full" if tr is w.tr else "nohub" if tr is getattr(w, "tr_nohub", None) else None
        if which is None:
            return _exch_free(w, tr, rule, drop_aa)
        key = (rule, which, drop_aa)
        if key not in w.memo:
            w.memo[key] = _exch_free(w, tr, rule, drop_aa)
        return w.memo[key]
    if rule == "all":
        parts = [rule_links(w, tr, r, exch, drop_aa) for r in ("dar_victor", "funder_aa_sponsor", "cospend")]
        lk = pd.concat([p[1] for p in parts], ignore_index=True).drop_duplicates()
        drop = set().union(*[p[2] for p in parts])
        return components(lk, drop=drop), lk, drop
    raise ValueError(rule)


def _exch_free(w, tr, rule, drop_aa):
    if rule.startswith("funder_"):
        f = w.funding[w.funding.tx_hash.isin(set(tr.tx_hash))]
        s, lk = funder.clusters(f, rule[7:], uo=None if drop_aa else w.uo)
        return s, lk, set()
    lk = cospend.links(tr, w.eoas)
    return cospend.clusters(lk), lk[["a", "b"]], set()


SLIM = ["block", "tx_hash", "log_index", "src", "dst", "asset", "raw", "amount", "kind", "poison_zero", "poison_lookalike"]
RULES = ["dar_naive", "dar_victor", "dar_hubfiltered", "funder_naive", "funder_hubfiltered", "funder_aa_sponsor", "cospend", "all"]


def evaluate_rules(w, labels_all, splits, seed=0, sizes_out=None):
    rows, sizes = [], []
    for hubs in ("included", "excluded"):
        tr = w.tr if hubs == "included" else w.tr[~w.tr.src.isin(w.hubs) & ~w.tr.dst.isin(w.hubs)]
        w.tr_nohub = tr
        active = set(tr.src) | set(tr.dst)
        lab = labels_all[labels_all.address.isin(active)].reset_index(drop=True)
        for rule in RULES:
            s, _, _ = rule_links(w, tr, rule, set(labels_all.address))
            m = score.evaluate(s, lab)
            vc = s.value_counts().value_counts().rename_axis("size").reset_index(name="n_clusters")
            sizes.append(vc.assign(rule=rule, hubs=hubs))
            rows.append({"hubs": hubs, "protocol": "full", "rule": rule, "split": -1, **m,
                         "clustered_addresses": len(s), "clusters": int(s.nunique()) if len(s) else 0})
            log(hubs, "full", rule, m["cross_exchange_pairs_linked"], m["pair_precision"])
        rng = np.random.default_rng(seed)
        for k in range(splits):
            known = labels_all.groupby("exchange", group_keys=False).apply(lambda g: g.sample(frac=0.5, random_state=int(rng.integers(1 << 31))))
            held = lab[~lab.address.isin(set(known.address))].reset_index(drop=True)
            for rule in ("dar_naive", "dar_victor", "dar_hubfiltered", "all"):
                s, _, _ = rule_links(w, tr, rule, set(known.address))
                m = score.evaluate(s, held)
                rows.append({"hubs": hubs, "protocol": "split50", "rule": rule, "split": k, **m,
                             "clustered_addresses": len(s), "clusters": int(s.nunique()) if len(s) else 0})
        log(hubs, "splits done")
    if sizes_out:
        pd.concat(sizes).to_csv(sizes_out, index=False)
    w.tr_nohub, w.memo = None, {}  # free the hub-filtered copy before the next stage
    return pd.DataFrame(rows)


def infra_attribution(w, labels):
    """Re-run every rule with one class of infrastructure transfers removed (one copy per class)."""
    lab = labels[labels.address.isin(w.active)].reset_index(drop=True)
    exch = set(labels.address)
    rows = {r: {"rule": r, "false_pairs": score.evaluate(rule_links(w, w.tr, r, exch)[0], lab)["cross_exchange_pairs_linked"]} for r in RULES}
    w.memo = {}
    for name, cols in {**INFRA, "all_infrastructure": [c for v in INFRA.values() for c in v]}.items():
        sub = w.tr.loc[~w.tr[cols].any(axis=1), SLIM]
        for r in RULES:
            fp = score.evaluate(rule_links(w, sub, r, exch, drop_aa="aa_infra" in cols)[0], lab)["cross_exchange_pairs_linked"]
            base = rows[r]["false_pairs"]
            rows[r][f"false_pairs_without_{name}"] = fp
            rows[r][f"share_caused_by_{name}"] = (base - fp) / base if base else float("nan")
        del sub
        log("infra", name, {r: rows[r][f"false_pairs_without_{name}"] for r in RULES})
    return pd.DataFrame(rows.values())


def taint_results(w, seed_sets, labels):
    exch = set(labels.address)
    rows, hcs = [], {}
    for seeds, sources in seed_sets.items():
        r, h = _taint_one(w, sources, labels, exch)
        rows += [dict(x, seeds=seeds) for x in r]
        hcs[seeds] = h
    return pd.DataFrame(rows), hcs


def _taint_one(w, sources, labels, exch):
    rows = []
    for name, tr in {"all_transfers": w.tr,
                     "no_zero_value": w.tr[~w.tr.poison_zero],
                     "no_poisoning": w.tr[~(w.tr.poison_zero | w.tr.poison_lookalike)],
                     "no_infrastructure": w.tr[~w.tr.infra_any]}.items():
        r = taint.nhop(tr, sources, hops=3)
        for k in (1, 2, 3):
            hit = r[(r.hop >= 1) & (r.hop <= k)]
            rows.append({"edges": name, "hops": k, "tainted_addresses": len(hit),
                         "exchange_por_wallets_tainted": int(hit.address.isin(exch).sum()),
                         "exchanges_reached": int(labels[labels.address.isin(set(hit.address))].exchange.nunique())})
    hc = taint.haircut(w.tr, sources)
    hc_rows = {"haircut_addresses_any_share": int(len(hc)), "haircut_addresses_share_ge_1pct": int((hc >= 0.01).sum()),
               "haircut_addresses_share_ge_50pct": int((hc >= 0.5).sum()),
               "haircut_por_wallets_any_share": int(hc.index.isin(exch).sum())}
    return rows, hc_rows


def block_bootstrap(w, labels, rule="dar_naive", n_blocks=12, B=200, seed=1):
    """Resample 6-hour blocks of the window with replacement and recompute the false-merge numbers."""
    lab = labels[labels.address.isin(w.active)].reset_index(drop=True)
    exch = set(labels.address)
    lo, hi = w.tr.block.min(), w.tr.block.max() + 1
    edges_ = np.linspace(lo, hi, n_blocks + 1).astype(int)
    seg = np.searchsorted(edges_, w.tr.block.to_numpy(), side="right") - 1
    rng = np.random.default_rng(seed)
    out = []
    if rule == "cospend":  # links are per transaction, so a time subset is exactly a filter on the full list
        lk = cospend.links(w.tr, w.eoas)
        lk_seg = lk.tx_hash.map(pd.Series(seg, index=w.tr.tx_hash).groupby(level=0).first())
    for b in range(B):
        pick = np.unique(rng.integers(0, n_blocks, n_blocks))
        if rule == "cospend":
            s = cospend.clusters(lk[lk_seg.isin(pick)])
        else:
            s = rule_links(w, w.tr[np.isin(seg, pick)], rule, exch)[0]
        m = score.evaluate(s, lab)
        out.append({"b": b, "segments": len(pick), "cross_exchange_pairs_linked": m["cross_exchange_pairs_linked"],
                    "clusters_with_2plus_exchanges": m["clusters_with_2plus_exchanges"], "pair_precision": m["pair_precision"]})
    return pd.DataFrame(out)


def per_day(w, labels, rule, day_starts):
    lab = labels[labels.address.isin(w.active)].reset_index(drop=True)
    out = []
    for i, (a, b) in enumerate(zip(day_starts[:-1], day_starts[1:])):
        tr = w.tr[(w.tr.block >= a) & (w.tr.block < b)]
        m = score.evaluate(rule_links(w, tr, rule, set(labels.address))[0], lab)
        out.append({"day": i + 1, "rule": rule, **m})
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", default="eth")
    ap.add_argument("--blocks", nargs=2, type=int)
    ap.add_argument("--splits", type=int, default=10)
    ap.add_argument("--bootstrap", type=int, default=200)
    ap.add_argument("--days", nargs="*", type=int, default=[26316189, 26323365, 26330541, 26337723])
    ap.add_argument("--force", action="store_true", help="recompute stages whose results already exist")
    a = ap.parse_args()
    os.makedirs("results", exist_ok=True)
    tag = a.chain
    labels = groundtruth.load(fetch=False, chain=a.chain)
    sources = taint.ofac_eth("data/raw/ofac/SDN.XML")
    # second seed set: the receiving addresses of EIP-7702 sweeper attacks published by SweeperHunter
    collectors = sorted(set(pd.read_csv(VICTIMS, usecols=["trace_address_to"], dtype=str).trace_address_to.dropna().str.lower())) \
        if os.path.exists(VICTIMS) else []
    log("loading")
    w = Window(a.chain, a.blocks)
    stats = {"chain": a.chain, "blocks": [int(w.txs.block.min()), int(w.txs.block.max())],
             "transactions": len(w.txs), "logs": w.n_logs, "transfers": len(w.tr),
             "eth_transfers": int((w.tr.kind == "eth").sum()), "erc20_transfers": int((w.tr.kind == "erc20").sum()),
             "userops": len(w.uo), "fresh_eoas_funded_in_window": len(w.funding), "hubs": len(w.hubs),
             "por_labels": len(labels), "por_labels_active": int(labels.address.isin(w.active).sum()),
             "ofac_eth_addresses": len(sources), "ofac_active": int(pd.Series(sources).isin(w.active).sum()),
             "sweeper_collectors": len(collectors), "sweeper_collectors_active": int(pd.Series(collectors, dtype=str).isin(w.active).sum()),
             **{f"infra_{k}": v for k, v in w.infra_info.items()},
             **{f"flagged_{c}": int(w.tr[c].sum()) for c in ["poison_zero", "poison_lookalike", "sweeper", "aa_infra", "infra_any"]}}
    json.dump(stats, open(f"results/stats_{tag}.json", "w"), indent=2)
    log(stats)
    todo = lambda f: a.force or not os.path.exists(f)  # noqa: E731  each stage resumes if its output exists
    if todo(f"results/rules_{tag}.csv"):
        evaluate_rules(w, labels, a.splits, sizes_out=f"results/cluster_sizes_{tag}.csv").to_csv(f"results/rules_{tag}.csv", index=False)
    if todo(f"results/infra_{tag}.csv"):
        infra_attribution(w, labels).to_csv(f"results/infra_{tag}.csv", index=False)
    if todo(f"results/taint_{tag}.csv"):
        t, hc = taint_results(w, {"ofac_sdn": sources, "sweeperhunter_collectors": collectors}, labels)
        t.to_csv(f"results/taint_{tag}.csv", index=False)
        json.dump(hc, open(f"results/haircut_{tag}.json", "w"), indent=2)
    if a.bootstrap and todo(f"results/bootstrap_{tag}.csv"):
        pd.concat([block_bootstrap(w, labels, rule=r, B=b).assign(rule=r)
                   for r, b in (("dar_naive", a.bootstrap), ("cospend", max(1, a.bootstrap // 2)))]
                  ).to_csv(f"results/bootstrap_{tag}.csv", index=False)
    if a.chain == "eth" and not a.blocks and todo(f"results/per_day_{tag}.csv"):
        pd.concat([per_day(w, labels, r, a.days) for r in ("dar_naive", "dar_victor", "all")]).to_csv(f"results/per_day_{tag}.csv", index=False)
    hc, hs = handcheck.run(w, labels)
    hc.to_csv(f"results/handcheck_{tag}.csv", index=False)
    json.dump(hs, open(f"results/handcheck_summary_{tag}.json", "w"), indent=2)
    handcheck.evidence(w, labels).to_csv(f"results/evidence_breakdown_{tag}.csv", index=False)
    log("done")


if __name__ == "__main__":
    main()
