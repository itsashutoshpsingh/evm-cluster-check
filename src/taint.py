"""Taint rules over the transfer graph, started from OFAC-listed Ethereum addresses.

nhop     time-respecting n-hop exposure: an address is tainted at hop k at the first block it
         receives anything from an address tainted at hop k-1 (at or after that address's own
         taint block). Any asset, any amount; this is the rule that dust and poisoning abuse.
haircut  proportional taint on ETH only: each address carries the share of its received ETH that
         came from tainted sources; outgoing ETH carries the sender's share at that moment.
"""
import numpy as np
import pandas as pd


def ofac_eth(xml_path):
    import re
    s = open(xml_path, encoding="utf-8").read()
    ids = re.findall(r"<idType>Digital Currency Address - (\w+)</idType>\s*<idNumber>([^<]+)</idNumber>", s)
    return sorted({n.strip().lower() for t, n in ids if re.fullmatch(r"0x[0-9a-fA-F]{40}", n.strip())})


def nhop(tr, sources, hops=3):
    """DataFrame address, hop, block for every address reached within `hops`."""
    e = tr[["src", "dst", "block"]]
    reached = pd.DataFrame({"address": list(sources), "hop": 0, "block": 0})
    frontier = reached
    for k in range(1, hops + 1):
        m = e.merge(frontier[["address", "block"]], left_on="src", right_on="address", suffixes=("", "_t"))
        m = m[m.block >= m.block_t]
        new = m.groupby("dst").block.min().reset_index().rename(columns={"dst": "address"})
        new = new[~new.address.isin(set(reached.address))]
        new["hop"] = k
        reached = pd.concat([reached, new], ignore_index=True)
        frontier = new
        if new.empty:
            break
    return reached


def haircut(tr, sources):
    """Final tainted-ETH share per address (only addresses with a share > 0)."""
    e = tr[tr.kind == "eth"].sort_values(["block", "log_index"])
    src = set(sources)
    # shortcut: balances start at zero at the window start, so shares are of in-window ETH only;
    # seed `bal` from eth_getBalance at the start block to turn this into a full-history haircut.
    bal, dirty = {}, {}
    for s, d, a in zip(e.src, e.dst, e.amount):
        share = 1.0 if s in src else (dirty.get(s, 0.0) / bal[s] if bal.get(s, 0) > 0 else 0.0)
        if s in bal:
            bal[s] = max(0.0, bal[s] - a)
            dirty[s] = max(0.0, dirty.get(s, 0.0) - a * share)
        bal[d] = bal.get(d, 0.0) + a
        dirty[d] = dirty.get(d, 0.0) + a * share
    out = pd.Series({k: dirty[k] / bal[k] for k in dirty if dirty[k] > 0 and bal.get(k, 0) > 0 and k not in src})
    return out.clip(upper=1.0)
