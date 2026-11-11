"""Reproduce what can be reproduced from Victor (2020) and Tutela (2022) on this window.

Full-history cluster counts need every block since 2015 (BigQuery-scale), so they are not
attempted. What is checked instead:
  1. Victor's parameter estimation: rerun DAR with tmax=10,000 blocks and amax=1 ETH and take the
     95th percentile of the amount and block differences for ETH forwards made by EOAs.
     Victor found 0.0083 ETH and 3,185 blocks.
  2. Victor's share of deposit-address users that share a deposit with another account (44.3%).
  3. Tutela's DAR cluster shape: mean size 4.3 (sd 8.6), largest 2.1k EOAs.
"""
import json

import numpy as np

from src import groundtruth
from src.heuristics import dar
from src.run import Window

VICTOR = {"amax_p95_eth": 0.0083, "tmax_p95_blocks": 3185, "share_users_sharing_deposit": 0.443}
TUTELA = {"mean_cluster_size": 4.3, "sd_cluster_size": 8.6, "largest_cluster": 2100}


def main(chain="eth"):
    w = Window(chain)
    exch = set(groundtruth.load(fetch=False).address)
    p = dar.paths(w.tr, exch, tmax=10_000, amax=1.0)  # Victor's first, loose pass
    eth = p[p.asset == "ETH"]
    eth = eth[eth.vd.isin(w.eoas)]
    m = eth.assign(da=eth.a1 - eth.a2, dt=eth.b2 - eth.b1)
    s, deps, used = dar.clusters(dar.paths(w.tr, exch), "victor", exch=exch, miners=w.miners)
    users = used.drop_duplicates(["vu", "vd"])
    n_users_per_dep = users.groupby("vd").vu.nunique()
    shared = users[users.vd.isin(n_users_per_dep[n_users_per_dep > 1].index)].vu.nunique()
    sizes = s.value_counts()
    multi = sizes[sizes > 1]
    out = {
        "window_blocks": [int(w.tr.block.min()), int(w.tr.block.max())],
        "eth_eoa_forward_paths_loose": int(len(m)),
        "amax_p95_eth": float(np.percentile(m.da, 95)) if len(m) else None,
        "tmax_p95_blocks": float(np.percentile(m.dt, 95)) if len(m) else None,
        "deposit_addresses": len(deps),
        "deposit_users": int(users.vu.nunique()),
        "share_users_sharing_deposit": shared / users.vu.nunique() if len(users) else None,
        "multi_address_clusters": int(len(multi)),
        "mean_cluster_size_multi": float(multi.mean()) if len(multi) else None,
        "sd_cluster_size_multi": float(multi.std()) if len(multi) > 1 else None,
        "largest_cluster": int(sizes.max()) if len(sizes) else 0,
        "victor_2020": VICTOR, "tutela_2022": TUTELA,
    }
    json.dump(out, open(f"results/reproduce_{chain}.json", "w"), indent=2)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
