"""Build notebooks/01_week1_result.ipynb (it reads results/*, so it runs in seconds)."""
import nbformat as nbf

cells = [
    ("md", "# evm-cluster-check: week-1 result\n\nEverything here is read from `results/`, produced by `make run`. "
           "Re-run `make notebook` after a new run."),
    ("code", "import os, json\nimport pandas as pd\nfrom IPython.display import Image, display\nos.chdir('..')  # run from the repository root\npd.set_option('display.width', 200)"),
    ("md", "## The window"),
    ("code", "json.load(open('results/stats_eth.json'))"),
    ("md", "## False merges by rule (full labels, hubs included and excluded)"),
    ("code", "r = pd.read_csv('results/rules_eth.csv')\n"
             "cols = ['hubs','rule','clustered_addresses','labelled_linked','cross_exchange_pairs_linked','clusters_with_2plus_exchanges','pair_precision','pw_precision','aer']\n"
             "r[r.protocol=='full'][cols]"),
    ("code", "display(Image('docs/img/false_merges_by_rule_eth.png'))"),
    ("md", "## Incomplete labels: the 50/50 split protocol (mean over splits)"),
    ("code", "s = r[r.protocol=='split50'].groupby(['hubs','rule'])[['cross_exchange_pairs_linked','clusters_with_2plus_exchanges','pair_precision','pw_precision']].agg(['mean','min','max'])\ns"),
    ("md", "## What causes them"),
    ("code", "pd.read_csv('results/infra_eth.csv')"),
    ("code", "display(Image('docs/img/infra_causes_eth.png'))"),
    ("md", "## Uncertainty"),
    ("code", "b = pd.read_csv('results/bootstrap_eth.csv'); b.cross_exchange_pairs_linked.describe(percentiles=[.025,.5,.975])"),
    ("code", "pd.read_csv('results/per_day_eth.csv')[['day','rule','cross_exchange_pairs_linked','pair_precision']]"),
    ("md", "## Taint"),
    ("code", "pd.read_csv('results/taint_eth.csv')"),
    ("code", "json.load(open('results/haircut_eth.json'))"),
    ("md", "## Hand-checked false merges"),
    ("code", "pd.read_csv('results/handcheck_eth.csv')[['case','exchange_a','exchange_b','hops','link_kinds','cause']]"),
    ("md", "## Reproduction against Victor (2020) and Tutela (2022)"),
    ("code", "json.load(open('results/reproduce_eth.json'))"),
    ("md", "## Injected ground truth (synthetic, local fork)"),
    ("code", "pd.read_csv('results/injected.csv')"),
]
nb = nbf.v4.new_notebook()
nb.cells = [nbf.v4.new_markdown_cell(c) if k == "md" else nbf.v4.new_code_cell(c) for k, c in cells]
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
nbf.write(nb, "notebooks/01_week1_result.ipynb")
