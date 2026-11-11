"""Draw every figure in docs/img from results/*.csv (dark theme shared with the project site)."""
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

BG, FG, GRID = "#0b0f14", "#c9d1d9", "#1f2a36"
GREEN, AMBER, RED, BLUE, GREY = "#00e5a0", "#ffb000", "#ff4d6d", "#5ab0ff", "#6e7681"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": FG,
    "axes.labelcolor": FG, "xtick.color": FG, "ytick.color": FG, "axes.edgecolor": GRID,
    "grid.color": GRID, "font.family": "DejaVu Sans Mono", "font.size": 10, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.linewidth": 0.6,
})
NAMES = {"dar_naive": "DAR naive", "dar_victor": "DAR (Victor)", "dar_hubfiltered": "DAR hub-filtered",
         "funder_naive": "gas funder", "funder_hubfiltered": "gas funder hub-filt.", "funder_aa_sponsor": "funder + 4337 sponsor",
         "cospend": "same-sender-in-tx", "all": "combined"}
OUT = "docs/img"


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    fig.savefig(f"{OUT}/{name}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def label_bars(ax, bars, fmt="{:,.0f}"):
    for b in bars:
        h = b.get_height()
        if np.isfinite(h) and h > 0:
            ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h), ha="center", va="bottom", fontsize=8, color=FG,
                        xytext=(0, 2), textcoords="offset points")


def hero(tag):
    r = pd.read_csv(f"results/rules_{tag}.csv")
    r = r[r.protocol == "full"]
    rules = [x for x in NAMES if x in set(r.rule)]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(rules))
    for i, (h, col) in enumerate((("included", RED), ("excluded", AMBER))):
        v = r[r.hubs == h].set_index("rule").cross_exchange_pairs_linked.reindex(rules)
        label_bars(ax, ax.bar(x + (i - 0.5) * 0.38, v, 0.38, color=col, label=f"hubs {h}"))
    ax.set_xticks(x, [NAMES[k] for k in rules], rotation=20, ha="right")
    ax.set_ylabel("pairs of exchange wallets\nfrom two different exchanges, linked")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_title(f"False merges by rule ({tag}, 3-day window, PoR ground truth)" if tag == "eth" else f"False merges by rule ({tag})")
    ax.legend(frameon=False)
    save(fig, f"false_merges_by_rule_{tag}")


def infra(tag):
    d = pd.read_csv(f"results/infra_{tag}.csv")
    d = d[d.false_pairs > 0]
    if d.empty:
        return
    cats = [("poisoning", RED), ("sweeper", AMBER), ("aa_bundler_paymaster", BLUE), ("all_infrastructure", GREEN)]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    x = np.arange(len(d))
    w = 0.2
    for i, (c, col) in enumerate(cats):
        label_bars(ax, ax.bar(x + (i - 1.5) * w, 100 * d[f"share_caused_by_{c}"], w, color=col, label=c.replace("_", " ")), "{:.0f}%")
    ax.set_xticks(x, [NAMES[k] for k in d.rule], rotation=20, ha="right")
    ax.set_ylabel("% of false merges that disappear\nwhen these transfers are removed")
    ax.set_ylim(0, 110)
    ax.set_title("What causes the false merges")
    ax.legend(frameon=False, ncol=4, loc="upper left")
    save(fig, f"infra_causes_{tag}")


def poisoning_effect(tag):
    d = pd.read_csv(f"results/infra_{tag}.csv")
    d = d[d.false_pairs > 0]
    if d.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 4))
    x = np.arange(len(d))
    label_bars(ax, ax.bar(x - 0.2, d.false_pairs, 0.4, color=RED, label="all transfers"))
    label_bars(ax, ax.bar(x + 0.2, d.false_pairs_without_poisoning, 0.4, color=GREEN, label="poisoning transfers removed"))
    ax.set_xticks(x, [NAMES[k] for k in d.rule], rotation=20, ha="right")
    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylabel("cross-exchange pairs linked")
    ax.set_title("Before / after removing zero-value and look-alike transfers")
    ax.legend(frameon=False)
    save(fig, f"poisoning_before_after_{tag}")


def sizes(tag):
    d = pd.read_csv(f"results/cluster_sizes_{tag}.csv")
    d = d[d.hubs == "included"]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for rule, col in (("dar_victor", GREEN), ("dar_naive", AMBER), ("cospend", RED), ("funder_naive", BLUE), ("all", FG)):
        g = d[d.rule == rule].sort_values("size")
        if g.empty:
            continue
        ccdf = g.n_clusters[::-1].cumsum()[::-1]
        ax.step(g["size"], ccdf, where="post", color=col, label=NAMES[rule], lw=1.6)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("cluster size (addresses)")
    ax.set_ylabel("clusters with at least this size")
    ax.set_title("Cluster size distribution (CCDF)")
    ax.legend(frameon=False)
    save(fig, f"cluster_sizes_{tag}")


def bootstrap(tag):
    p = f"results/bootstrap_{tag}.csv"
    if not os.path.exists(p):
        return
    d = pd.read_csv(p)
    lo, hi = np.percentile(d.cross_exchange_pairs_linked, [2.5, 97.5])
    full = pd.read_csv(f"results/rules_{tag}.csv").query("protocol=='full' and hubs=='included' and rule=='dar_naive'").cross_exchange_pairs_linked.iloc[0]
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.hist(d.cross_exchange_pairs_linked, bins=30, color=BLUE, alpha=0.85)
    ax.axvspan(lo, hi, color=GREEN, alpha=0.12, label=f"95% interval {lo:,.0f}-{hi:,.0f}")
    ax.axvline(full, color=AMBER, lw=2, label=f"full window {full:,.0f}")
    ax.set_xlabel("cross-exchange pairs linked by naive DAR")
    ax.set_ylabel("bootstrap samples")
    ax.set_title(f"Block bootstrap over 6-hour segments (B={len(d)})")
    ax.legend(frameon=False)
    save(fig, f"bootstrap_{tag}")


def taint_fig(tag):
    d = pd.read_csv(f"results/taint_{tag}.csv")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    cols = {"all_transfers": RED, "no_zero_value": AMBER, "no_poisoning": GREEN, "no_infrastructure": BLUE}
    for e, col in cols.items():
        g = d[d.edges == e]
        axes[0].plot(g.hops, g.tainted_addresses, "o-", color=col, label=e.replace("_", " "))
        axes[1].plot(g.hops, g.exchange_por_wallets_tainted, "o-", color=col, label=e.replace("_", " "))
    axes[0].set_yscale("symlog", linthresh=10)
    axes[0].set_title("addresses within n hops of OFAC list")
    axes[1].set_title("exchange PoR wallets within n hops")
    for a in axes:
        a.set_xlabel("hops")
        a.set_xticks([1, 2, 3])
    axes[0].legend(frameon=False, fontsize=8)
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
        label_bars(ax, ax.bar(x + (i - 0.5) * 0.38, g.false_links, 0.38, color=col, label=f"false links, {e.replace('_', ' ')}"))
    t = d[d.edges == "all"].set_index("rule").reindex(rules).true_links
    ax.scatter(x, t, marker="D", color=FG, zorder=3, label="true links found")
    ax.set_xticks(x, [NAMES[k] for k in rules], rotation=20, ha="right")
    ax.set_ylabel("wallet pairs")
    ax.set_title("Injected ground truth on a local mainnet fork (synthetic)")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "injected")


def metrics_table(tag):
    r = pd.read_csv(f"results/rules_{tag}.csv")
    r = r[(r.protocol == "full") & (r.hubs == "included")].set_index("rule")
    cols = ["pair_precision", "pair_recall", "pair_f1", "pw_precision", "pw_recall", "pw_f1", "nmi", "anmi", "aer"]
    m = r[cols].reindex([k for k in NAMES if k in r.index])
    fig, ax = plt.subplots(figsize=(10, 3.8))
    im = ax.imshow(m.to_numpy(dtype=float), cmap="viridis", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(cols)), [c.replace("pair_", "pair ").replace("pw_", "wallet ") for c in cols], rotation=30, ha="right")
    ax.set_yticks(range(len(m)), [NAMES[k] for k in m.index])
    ax.grid(False)
    for i in range(m.shape[0]):
        for j in range(m.shape[1]):
            v = m.iat[i, j]
            ax.text(j, i, "n/a" if pd.isna(v) else f"{v:.2f}", ha="center", va="center", fontsize=8, color=BG if (not pd.isna(v) and v > 0.6) else FG)
    ax.set_title("Nine metrics of Müller et al. (2026), all rules")
    fig.colorbar(im, ax=ax, fraction=0.025)
    save(fig, f"metrics_{tag}")


def per_day_fig():
    p = "results/per_day_eth.csv"
    if not os.path.exists(p):
        return
    d = pd.read_csv(p)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for rule, col in (("dar_naive", AMBER), ("dar_victor", GREEN), ("all", RED)):
        g = d[d.rule == rule]
        ax.plot(g.day, g.cross_exchange_pairs_linked, "o-", color=col, label=NAMES[rule])
    ax.set_xticks([1, 2, 3], ["1 Nov", "2 Nov", "3 Nov"])
    ax.set_yscale("symlog", linthresh=10)
    ax.set_ylabel("cross-exchange pairs linked")
    ax.set_title("Each day on its own")
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
