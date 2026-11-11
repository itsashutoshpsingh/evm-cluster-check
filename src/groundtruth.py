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
OWNERS_RE = r"{chain}\s*:\s*\{{[^{{}}]*?owners\s*:\s*\[(.*?)\]"
CHAIN_KEY = {"eth": "ethereum", "base": "base"}
ADDR = re.compile(r"0x[0-9a-fA-F]{40}\b")


def strip_comments(js):
    return re.sub(r"//[^\n]*", "", js)


def extract(js, pattern=None, chain="eth"):
    """Return the lower-cased owner addresses for `chain` in one adapter file."""
    js = strip_comments(js)
    blocks = re.findall(pattern or OWNERS_RE.format(chain=CHAIN_KEY[chain]), js, flags=re.S)
    return sorted({a.lower() for b in blocks for a in ADDR.findall(b)})


BITFINEX_OWN = "https://raw.githubusercontent.com/bitfinexcom/pub/83d06bdb5f5a2ce05d5ba2db5a426dd44c9f5128/wallets.txt"


def verify_bitfinex(addrs):
    """Cross-check the copied Bitfinex list against the list Bitfinex itself publishes."""
    own = {l.split()[0].lower() for l in requests.get(BITFINEX_OWN, timeout=60).text.splitlines()
           if "ETH/ERC20" in l and l.startswith("0x")}
    return {"url": BITFINEX_OWN, "exchange_list": len(own), "copied_list": len(addrs), "identical": own == set(addrs)}


def load(fetch=True, chain="eth"):
    out = "data/raw/groundtruth/por.parquet" if chain == "eth" else f"data/raw/groundtruth/por_{chain}.parquet"
    if os.path.exists(out) and not fetch:
        return pd.read_parquet(out)
    rows, meta = [], {}
    for ex, (path, pat) in SOURCES.items():
        url = f"{BASE}/{path}"
        js = requests.get(url, timeout=60).text
        addrs = extract(js, pat, chain)
        if not addrs:
            continue
        meta[ex] = {"url": url, "n_addresses": len(addrs),
                    "sha256_of_sorted_list": hashlib.sha256("\n".join(addrs).encode()).hexdigest()}
        rows += [{"address": a, "exchange": ex} for a in addrs]
    df = pd.DataFrame(rows)
    df, overlaps = drop_overlaps(df)
    checks = {"Bitfinex": verify_bitfinex(sorted(df[df.exchange == "Bitfinex"].address))} if chain == "eth" else {}
    meta = {"commit": COMMIT, "verification": checks, "fetched_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "overlapping_addresses_dropped": overlaps, "exchanges": meta}
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_parquet(out)
    with open("data/groundtruth/sources.json" if chain == "eth" else f"data/groundtruth/sources_{chain}.json", "w") as f:
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
    for ch in CHAIN_KEY:
        d = load(chain=ch)
        print(ch, d.exchange.value_counts().to_dict())
