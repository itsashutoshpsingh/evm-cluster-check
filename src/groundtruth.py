"""Same-owner ground truth from exchanges' proof-of-reserves (PoR) wallet lists.

Source: the DefiLlama-Adapters repository, which copies each exchange's published PoR
wallets into a per-exchange file. We pin one commit so the lists are reproducible.
Addresses are NOT committed to git; only the URLs, the commit, counts and a hash of
each derived list are (see data/groundtruth/sources.json).

Usage: python -m src.groundtruth   -> writes data/raw/groundtruth/por.parquet
"""
import hashlib
import itertools
import json
import os
import re
import datetime as dt

import pandas as pd
import requests

COMMIT = "02aeae14d3696810f01a16bd8b66666ea2871e4f"  # DefiLlama-Adapters main, 2026-11-11
BASE = f"https://raw.githubusercontent.com/DefiLlama/DefiLlama-Adapters/{COMMIT}/projects"
# exchange -> (file, regex that captures the Ethereum owners array)
SOURCES = {
    "OKX": ("okex/index.js", None),
    "Bitfinex": ("bitfinex/index.js", None),
    "KuCoin": ("kucoin/index.js", None),
    "Gemini": ("gemini/index.js", None),
    "HTX": ("huobi/index.js", None),
    "Gate": ("gate-io/index.js", None),
    "CoinEx": ("coinex/index.js", None),
    "Bitrue": ("bitrue-cex/index.js", None),
    "Bitget": ("bitget/index.js", r"evmOwners\s*=\s*\[(.*?)\]"),
}
ETH_OWNERS = r"ethereum\s*:\s*\{[^{}]*?owners\s*:\s*\[(.*?)\]"
ADDR = re.compile(r"0x[0-9a-fA-F]{40}\b")


def strip_comments(js):
    return re.sub(r"//[^\n]*", "", js)


def extract(js, pattern=None):
    """Return the lower-cased Ethereum owner addresses in one adapter file."""
    js = strip_comments(js)
    blocks = re.findall(pattern or ETH_OWNERS, js, flags=re.S)
    return sorted({a.lower() for b in blocks for a in ADDR.findall(b)})


def load(fetch=True):
    out = "data/raw/groundtruth/por.parquet"
    if os.path.exists(out) and not fetch:
        return pd.read_parquet(out)
    rows, meta = [], {}
    for ex, (path, pat) in SOURCES.items():
        url = f"{BASE}/{path}"
        js = requests.get(url, timeout=60).text
        addrs = extract(js, pat)
        meta[ex] = {"url": url, "n_addresses": len(addrs),
                    "sha256_of_sorted_list": hashlib.sha256("\n".join(addrs).encode()).hexdigest()}
        rows += [{"address": a, "exchange": ex} for a in addrs]
    df = pd.DataFrame(rows)
    df, overlaps = drop_overlaps(df)
    meta = {"commit": COMMIT, "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "overlapping_addresses_dropped": overlaps, "exchanges": meta}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_parquet(out)
    with open("data/groundtruth/sources.json", "w") as f:
        json.dump(meta, f, indent=2)
    return df


def drop_overlaps(df):
    """An address listed by two exchanges cannot be ground truth for either; drop it."""
    n = df.groupby("address").exchange.nunique()
    bad = set(n[n > 1].index)
    return df[~df.address.isin(bad)].drop_duplicates().reset_index(drop=True), len(bad)


def pairs(df):
    """All labelled pairs: same exchange -> same owner (1); different exchanges -> different owner (0)."""
    a = df.sort_values("address").to_records(index=False)
    for (x, ex), (y, ey) in itertools.combinations(a, 2):
        yield x, y, int(ex == ey)


if __name__ == "__main__":
    d = load()
    print(d.exchange.value_counts().to_string())
    print(json.load(open("data/groundtruth/sources.json"))["overlapping_addresses_dropped"], "overlaps dropped")
