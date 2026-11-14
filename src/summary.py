"""Write results/summary.json (read by the project site) from the committed Ethereum results."""
import json

import pandas as pd

R = "results"


def build():
    rules = pd.read_csv(f"{R}/rules_eth.csv")
    rules = rules[(rules.protocol == "full") & (rules.hubs == "included")].set_index("rule")
    infra = pd.read_csv(f"{R}/infra_eth.csv").set_index("rule")
    taint = pd.read_csv(f"{R}/taint_eth.csv")
    stats = json.load(open(f"{R}/stats_eth.json"))
    dar, co, comb = (int(rules.loc[r].pairs_false_linked) for r in ("dar_naive", "cospend", "all"))
    co_poison = infra.loc["cospend"].share_caused_by_poisoning
    t = taint[(taint.seeds == "sweeperhunter_collectors") & (taint.hops == 1)].set_index("edges").tainted_addresses
    infra_pct = lambda r: round(100 * float(infra.loc[r].share_caused_by_all_infrastructure), 1)  # noqa: E731
    return {
        "project": "evm-cluster-check",
        "headline": (f"On 3 days of Ethereum ({stats['transactions'] / 1e6:.2f}M transactions), naive deposit-address reuse merged "
                     f"{dar} pairs of addresses from two different exchanges, none caused by poisoning, sweepers or fee services; "
                     f"the same-sender rule merged {co}, and {co_poison:.0%} of those came only through poisoning transfers."),
        "metrics": [
            {"label": "Cross-exchange false merges, deposit-address reuse", "value": dar},
            {"label": "Share of deposit-reuse false merges caused by infrastructure", "value": f"{infra.loc['dar_naive'].share_caused_by_all_infrastructure:.0%}"},
            {"label": "Cross-exchange false merges, same sender in one tx", "value": co},
            {"label": "Share of same-sender false merges caused by poisoning", "value": f"{co_poison:.0%}"},
            {"label": "Ethereum transactions analysed", "value": f"{stats['transactions']:,}"},
            {"label": "Exchange PoR addresses as ground truth", "value": stats["por_labels"]},
        ],
        "charts": [
            {"path": "docs/img/false_merges_by_rule_eth.png", "label": "False merges by rule",
             "alt": "Bar chart of cross-exchange false merges per clustering rule, with hubs included and excluded"},
            {"path": "docs/img/infra_causes_eth.png", "label": "Causes",
             "alt": "Share of false merges that disappear when poisoning, sweeper and paymaster transfers are removed"},
            {"path": "docs/img/taint_eth.png", "label": "Taint", "alt": "Addresses tainted at 1 to 3 hops, with and without zero-value transfers"},
            {"path": "docs/img/injected.png", "label": "Injected tests", "alt": "False links made by each rule on wallets I control on a local fork"},
        ],
        "viz": [
            {"title": "Naive deposit reuse and the same-sender rule wrongly merge addresses of two different exchanges", "unit": "count", "bars": [
                {"label": "Deposit reuse, naive", "value": dar, "tone": "bad"},
                {"label": "Deposit reuse, Victor 2020", "value": int(rules.loc["dar_victor"].pairs_false_linked), "tone": "good"},
                {"label": "Same sender in one tx", "value": co, "tone": "bad"},
                {"label": "All rules combined", "value": comb, "tone": "bad"}]},
            {"title": "Poisoning and other infrastructure cause most same-sender false merges and none from deposit reuse", "unit": "%", "bars": [
                {"label": "Deposit reuse, naive", "value": infra_pct("dar_naive"), "tone": "neutral"},
                {"label": "Same sender in one tx", "value": infra_pct("cospend"), "tone": "warn"},
                {"label": "All rules combined", "value": infra_pct("all"), "tone": "warn"}]},
            {"title": "Zero-value transfers inflate the addresses a one-hop taint rule flags", "unit": "count", "bars": [
                {"label": "All transfers", "value": int(t["all_transfers"]), "tone": "bad"},
                {"label": "Zero-value removed", "value": int(t["no_zero_value"]), "tone": "good"}]},
        ],
    }


if __name__ == "__main__":
    s = build()
    json.dump(s, open(f"{R}/summary.json", "w"), indent=1, ensure_ascii=False)
    print(s["headline"])
