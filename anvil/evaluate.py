"""Run every rule on the injected fork blocks and list which wallet pairs each rule links.

python -m anvil.evaluate  -> results/injected.csv and results/injected_links.csv
"""
import itertools
import json

import pandas as pd

from src import edges
from src.infra_labels import label
from src.run import rule_links

OWNERS = json.load(open("anvil/owners.json"))
META = json.load(open("anvil/blocks.json"))
CONTROLLED = {a: o for a, o in OWNERS.items() if not o.startswith("exchange")}


class W:
    pass


def window():
    w = W()
    w.txs = edges.read("anvil", "txs", META["blocks"])
    w.logs = edges.read("anvil", "logs", META["blocks"])
    tr = edges.transfers(w.txs, w.logs)
    w.uo = edges.userops(w.logs, w.txs)
    pd.DataFrame({"contract": [META["sweeper"]]}).to_csv("anvil/sweeper.csv", index=False)
    w.tr, w.infra_info, _ = label(tr, w.txs, w.uo, "anvil/sweeper.csv")
    w.tr["infra_any"] = w.tr[["poison_zero", "poison_lookalike", "sweeper", "aa_infra"]].any(axis=1)
    w.miners = set(w.txs.miner)
    w.eoas = set(w.txs["from"])
    from src.heuristics import funder
    w.funding = funder.funding(w.txs, w.tr)
    return w


def linked_pairs(s):
    out = []
    for _, g in s.groupby(s):
        members = sorted(a for a in g.index if a in OWNERS)
        for x, y in itertools.combinations(members, 2):
            out.append((x, y))
    return out


def main():
    w = window()
    exch = {META["exch"], META["exch2"]}
    rows, links = [], []
    for rule in ["dar_naive", "dar_victor", "dar_hubfiltered", "funder_naive", "funder_hubfiltered", "funder_aa_sponsor", "cospend", "all"]:
        for edges_ in ("all", "infra_removed"):
            tr = w.tr if edges_ == "all" else w.tr[~w.tr.infra_any]
            s, _, _ = rule_links(w, tr, rule, exch)
            pairs = linked_pairs(s)
            tp = [(x, y) for x, y in pairs if OWNERS[x] == OWNERS[y]]
            fp = [(x, y) for x, y in pairs if OWNERS[x] != OWNERS[y]]
            rows.append({"rule": rule, "edges": edges_, "true_links": len(tp), "false_links": len(fp),
                         "false_link_owner_pairs": "; ".join(sorted({f"{OWNERS[x]}~{OWNERS[y]}" for x, y in fp}))})
            links += [{"rule": rule, "edges": edges_, "a_owner": OWNERS[x], "b_owner": OWNERS[y], "correct": OWNERS[x] == OWNERS[y]} for x, y in pairs]
    pd.DataFrame(rows).to_csv("results/injected.csv", index=False)
    pd.DataFrame(links).to_csv("results/injected_links.csv", index=False)
    print(pd.DataFrame(rows).to_string(index=False))
    swept = w.tr[(w.tr.dst == next(a for a, o in OWNERS.items() if o == "dave")) & (w.tr.kind == "eth")].amount.sum()
    print("ETH the transfer table credits to the swept wallet:", swept, "balance change on chain:", META["dave_balance_change_wei"] / 1e18)


if __name__ == "__main__":
    main()
