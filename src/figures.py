"""Draw every figure in docs/img from results/*.csv (dark theme shared with the project site)."""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

# Portfolio chart style (BUILD_RULES.md, "Charts"): solid colours, Carlito, capitalised labels.
BG, FG, FG2, GRID = "#0C1421", "#FFFFFF", "#C9D4E2", "#1F2E45"
BLUE, GREEN, RED, YELLOW, WHITE = "#3B82F6", "#22C55E", "#EF4444", "#FACC15", "#FFFFFF"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": FG,
    "axes.labelcolor": FG, "xtick.color": FG2, "ytick.color": FG2, "axes.edgecolor": GRID,
    "grid.color": GRID, "font.family": "Carlito", "font.size": 11, "axes.titlesize": 15, "axes.titleweight": "bold",
    "figure.titlesize": 15, "figure.titleweight": "bold", "axes.labelsize": 12, "xtick.labelsize": 11,
    "ytick.labelsize": 11, "legend.fontsize": 11, "legend.labelcolor": FG, "lines.linewidth": 2,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.linewidth": 0.6, "grid.alpha": 1,
})
NAMES = {"dar_naive": "DAR naive", "dar_victor": "DAR (Victor)", "dar_hubfiltered": "DAR hub-filtered",
         "funder_naive": "Gas funder", "funder_hubfiltered": "Gas funder hub-filt.", "funder_aa_sponsor": "Funder + 4337 sponsor",
         "cospend": "Same-sender-in-tx", "all": "Combined"}
CHAIN = {"eth": "Ethereum, 3 days", "base": "Base, 6 hours"}
OUT = "docs/img"


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(f"{OUT}/{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def label_bars(ax, bars, fmt="{:,.0f}"):
    for b in bars:
        h = b.get_height()
        if np.isfinite(h) and h > 0:
            ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h), ha="center", va="bottom", fontsize=11, color=FG,
                        xytext=(0, 2), textcoords="offset points")


def hero(tag):
    r = pd.read_csv(f"results/rules_{tag}.csv")
    r = r[r.protocol == "full"]
    rules = [x for x in NAMES if x in set(r.rule)]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(rules))
    for i, (h, col) in enumerate((("included", RED), ("excluded", YELLOW))):
        v = r[r.hubs == h].set_index("rule").cross_exchange_pairs_linked.reindex(rules)
        label_bars(ax, ax.bar(x + (i - 0.5) * 0.38, v, 0.38, color=col, label=f"Hubs {h}"))
    ax.set_xticks(x, [NAMES[k] for k in rules], rotation=20, ha="right")
    ax.set_ylabel("Pairs of exchange wallets\nfrom two different exchanges, linked")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylim(0, max(10, r.cross_exchange_pairs_linked.max()) * 6)  # headroom for labels under the title
    n_link = int((r[r.hubs == "included"].set_index("rule").cross_exchange_pairs_linked.reindex(rules) > 0).sum())
    ax.set_title(f"Only {n_link} of {len(rules)} rules link wallets of two different exchanges ({CHAIN[tag]})")
    ax.legend(frameon=False)
    save(fig, f"false_merges_by_rule_{tag}")


def infra(tag):
    d = pd.read_csv(f"results/infra_{tag}.csv")
    d = d[d.false_pairs > 0]
    if d.empty:
        return
    cats = [("poisoning", RED), ("sweeper", YELLOW), ("aa_bundler_paymaster", BLUE), ("all_infrastructure", GREEN)]
    cat_names = {"poisoning": "Poisoning", "sweeper": "Sweeper", "aa_bundler_paymaster": "AA bundler or paymaster",
                 "all_infrastructure": "All infrastructure"}
    fig, ax = plt.subplots(figsize=(10, 4.4))
    x = np.arange(len(d))
    w = 0.2
    for i, (c, col) in enumerate(cats):
        label_bars(ax, ax.bar(x + (i - 1.5) * w, 100 * d[f"share_caused_by_{c}"], w, color=col, label=cat_names[c]), "{:.0f}%")
    ax.set_xticks(x, [NAMES[k] for k in d.rule], rotation=20, ha="right")
    ax.set_ylabel("False merges that disappear\nwhen these transfers are removed (%)")
    ax.set_ylim(0, 130)  # headroom so 100% labels clear the legend
    ax.set_title(f"Poisoning, not sweepers or paymasters, causes the explained false merges ({CHAIN[tag]})")
    ax.legend(frameon=False, ncol=4, loc="upper left")
    save(fig, f"infra_causes_{tag}")


def poisoning_effect(tag):
    d = pd.read_csv(f"results/infra_{tag}.csv")
    d = d[d.false_pairs > 0]
    if d.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(len(d))
    label_bars(ax, ax.bar(x - 0.2, d.false_pairs, 0.4, color=RED, label="All transfers"))
    label_bars(ax, ax.bar(x + 0.2, d.false_pairs_without_poisoning, 0.4, color=GREEN, label="Poisoning transfers removed"))
    ax.set_xticks(x, [NAMES[k] for k in d.rule], rotation=20, ha="right")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylim(0, max(10, d.false_pairs.max()) * 6)  # headroom for labels and legend under the title
    ax.set_ylabel("Cross-exchange pairs linked")
    ax.set_title(f"Removing poisoning transfers cuts the same-sender false merges ({CHAIN[tag]})")
    ax.legend(frameon=False, loc="upper left")
    save(fig, f"poisoning_before_after_{tag}")


def sizes(tag):
    d = pd.read_csv(f"results/cluster_sizes_{tag}.csv")
    d = d[d.hubs == "included"]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for rule, col in (("dar_victor", GREEN), ("dar_naive", YELLOW), ("cospend", RED), ("funder_naive", BLUE), ("all", WHITE)):
        g = d[d.rule == rule].sort_values("size")
        if g.empty:
            continue
        ccdf = g.n_clusters[::-1].cumsum()[::-1]
        ax.step(g["size"], ccdf, where="post", color=col, label=NAMES[rule], lw=1.6)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Cluster size (addresses)")
    ax.set_ylabel("Clusters with at least this size")
    ax.set_title(f"Combined rules build clusters of up to {d['size'].max():,} addresses ({CHAIN[tag]})")
    ax.legend(frameon=False)
    save(fig, f"cluster_sizes_{tag}")


def bootstrap(tag):
    p = f"results/bootstrap_{tag}.csv"
    if not os.path.exists(p):
        return
    d = pd.read_csv(p)
    rules = list(dict.fromkeys(d.rule))
    full_all = pd.read_csv(f"results/rules_{tag}.csv").query("protocol=='full' and hubs=='included'").set_index("rule")
    fig, axes = plt.subplots(1, len(rules), figsize=(6 * len(rules), 3.8), squeeze=False)
    for ax, rule in zip(axes[0], rules):
        g = d[d.rule == rule]
        lo, hi = np.percentile(g.cross_exchange_pairs_linked, [2.5, 97.5])
        full = full_all.cross_exchange_pairs_linked[rule]
        ax.hist(g.cross_exchange_pairs_linked, bins=30, color=BLUE)
        ax.axvline(lo, color=GREEN, lw=2, ls="--", label=f"95% interval {lo:,.0f} to {hi:,.0f}")
        ax.axvline(hi, color=GREEN, lw=2, ls="--")
        ax.axvline(full, color=YELLOW, lw=2, label=f"Full window {full:,.0f}")
        ax.set_xlabel(f"Cross-exchange pairs linked, {NAMES[rule]}")
        ax.set_ylabel("Bootstrap samples")
        ax.set_title(f"95% of 6-hour block resamples fall in {lo:,.0f} to {hi:,.0f} (B={len(g)})")
        ax.legend(facecolor=BG, edgecolor=GRID, framealpha=1)
    fig.tight_layout()
    save(fig, f"bootstrap_{tag}")


def taint_fig(tag):
    d = pd.read_csv(f"results/taint_{tag}.csv")
    seeds = list(dict.fromkeys(d.seeds))
    fig, axes = plt.subplots(len(seeds), 2, figsize=(11, 3.6 * len(seeds)), squeeze=False)
    cols = {"all_transfers": RED, "no_zero_value": YELLOW, "no_poisoning": GREEN, "no_infrastructure": BLUE}
    edge_names = {"all_transfers": "All transfers", "no_zero_value": "No zero-value", "no_poisoning": "No poisoning",
                  "no_infrastructure": "No infrastructure"}
    seed_names = {"ofac_sdn": "OFAC SDN addresses", "sweeperhunter_collectors": "SweeperHunter collectors"}
    for i, sd in enumerate(seeds):
        for e, col in cols.items():
            g = d[(d.seeds == sd) & (d.edges == e)]
            axes[i, 0].plot(g.hops, g.tainted_addresses, "o-", color=col, label=edge_names[e])
            axes[i, 1].plot(g.hops, g.exchange_por_wallets_tainted, "o-", color=col, label=edge_names[e])
        axes[i, 0].set_title(f"Addresses within n hops of {seed_names.get(sd, sd)}")
        axes[i, 1].set_title("Exchange PoR wallets within n hops")
        for a in axes[i]:
            a.set_xticks([1, 2, 3])
            a.set_yscale("symlog", linthresh=10)
        axes[i, 0].legend(frameon=False)
    for a in axes[-1]:
        a.set_xlabel("Hops")
    one = d[d.hops == 1].pivot_table(index="seeds", columns="edges", values="tainted_addresses")
    top = one.all_transfers.idxmax()
    fig.suptitle(f"Dropping zero-value transfers cuts one-hop taint from {one.at[top, 'all_transfers']:,.0f} "
                 f"to {one.at[top, 'no_zero_value']:,.0f} addresses ({CHAIN[tag]})")
    fig.tight_layout()
    save(fig, f"taint_{tag}")


def injected():
    p = "results/injected.csv"
    if not os.path.exists(p):
        return
    d = pd.read_csv(p)
    rules = list(dict.fromkeys(d.rule))
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(len(rules))
    for i, (e, col) in enumerate((("all", RED), ("infra_removed", GREEN))):
        g = d[d.edges == e].set_index("rule").reindex(rules)
        label_bars(ax, ax.bar(x + (i - 0.5) * 0.38, g.false_links, 0.38, color=col, label={"all": "False links, all transfers", "infra_removed": "False links, infrastructure removed"}[e]))
    t = d[d.edges == "all"].set_index("rule").reindex(rules).true_links
    ax.scatter(x, t, marker="D", color=WHITE, zorder=3, label="True links found")
    ax.set_xticks(x, [NAMES[k] for k in rules], rotation=20, ha="right")
    ax.set_ylabel("Wallet pairs")
    ax.set_title("On a local mainnet fork, removing infrastructure transfers cuts false links (synthetic)")
    ax.legend(frameon=False)
    save(fig, "injected")


def metrics_table(tag):
    r = pd.read_csv(f"results/rules_{tag}.csv")
    r = r[(r.protocol == "full") & (r.hubs == "included")].set_index("rule")
    cols = ["pair_precision", "pair_recall", "pair_f1", "pw_precision", "pw_recall", "pw_f1", "nmi", "anmi", "aer"]
    m = r[cols].reindex([k for k in NAMES if k in r.index])
    fig, ax = plt.subplots(figsize=(10, 3.8))
    # the only gradient: it encodes the metric value, red (0) to blue (1)
    cmap = LinearSegmentedColormap.from_list("red_blue", [RED, BLUE])
    im = ax.imshow(m.to_numpy(dtype=float), cmap=cmap, vmin=0, vmax=1, aspect="auto")
    col_names = {"pair_precision": "Pair precision", "pair_recall": "Pair recall", "pair_f1": "Pair F1",
                 "pw_precision": "Wallet precision", "pw_recall": "Wallet recall", "pw_f1": "Wallet F1",
                 "nmi": "NMI", "anmi": "ANMI", "aer": "AER"}
    ax.set_xticks(range(len(cols)), [col_names[c] for c in cols], rotation=30, ha="right")
    ax.set_yticks(range(len(m)), [NAMES[k] for k in m.index])
    ax.grid(False)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.iat[i, j]
            ax.text(j, i, "N/A" if pd.isna(v) else f"{v:.2f}", ha="center", va="center", fontsize=11, color=FG)
    ax.set_title(f"Every rule scores low on the nine metrics of Müller et al. (2026) ({CHAIN[tag]})")
    fig.colorbar(im, ax=ax, fraction=0.025)
    save(fig, f"metrics_{tag}")


def per_day_fig():
    p = "results/per_day_eth.csv"
    if not os.path.exists(p):
        return
    d = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for rule, col in (("dar_naive", YELLOW), ("dar_victor", GREEN), ("all", RED)):
        g = d[d.rule == rule]
        ax.plot(g.day, g.cross_exchange_pairs_linked, "o-", color=col, label=NAMES[rule])
    ax.set_xticks([1, 2, 3], ["1 Nov", "2 Nov", "3 Nov"])
    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylim(-1, d.cross_exchange_pairs_linked.max() * 2)  # headroom so the top marker is not clipped
    ax.set_ylabel("Cross-exchange pairs linked")
    ax.set_title("The ranking of rules holds on each of the three days")
    ax.legend(frameon=False)
    save(fig, "per_day_eth")


if __name__ == "__main__":
    for tag in ("eth", "base"):
        if os.path.exists(f"results/rules_{tag}.csv"):
            hero(tag)
            infra(tag)
            poisoning_effect(tag)
            sizes(tag)
            bootstrap(tag)
            taint_fig(tag)
            metrics_table(tag)
    injected()
    per_day_fig()
    print(sorted(os.listdir(OUT)))
