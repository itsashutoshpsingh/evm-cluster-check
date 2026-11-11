"""Pull blocks (with transactions) and selected event logs into Parquet.

Usage:
  python -m src.fetch blocks --chain eth --start 26316189 --end 26337722
  python -m src.fetch find-window --chain eth --day 2026-11-01

Output: data/raw/<chain>/{txs,logs}/<chunkstart>.parquet, one file per CHUNK blocks.
A chunk file only exists once every block in it was fetched without error, so a
re-run resumes where it stopped and a rate-limit error can never become missing data.
"""
import argparse
import datetime as dt
import itertools
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

PROVIDERS = {
    "eth": ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org", "https://1rpc.io/eth"],
    "base": ["https://base-rpc.publicnode.com", "https://mainnet.base.org"],
}
# Only some free endpoints serve eth_getLogs for blocks older than ~128 blocks
# (publicnode asks for a token, 1rpc refuses the method), found on 2026-11-11.
LOG_PROVIDERS = {"eth": ["https://eth.drpc.org"], "base": ["https://base-rpc.publicnode.com", "https://mainnet.base.org"]}
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
# ERC-4337 UserOperationEvent(bytes32 userOpHash, address sender, address paymaster, uint256 nonce, bool success, uint256 actualGasCost, uint256 actualGasUsed)
USEROP = "0x49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f"
CHUNK = 100
LOG_SPAN = 5  # blocks per eth_getLogs call; keeps responses well under provider caps
RATE = float(os.environ.get("FETCH_RATE", "6"))  # total requests/second across providers


class Rpc:
    """Round-robin JSON-RPC client with a global rate limit and retry on any error."""

    def __init__(self, urls):
        self.urls = itertools.cycle(urls)
        self.lock = threading.Lock()
        self.next_t = 0.0
        self.s = requests.Session()

    def _wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next_t)
            self.next_t = t + 1.0 / RATE
        time.sleep(max(0.0, t - now))

    def call(self, method, params, tries=12):
        for i in range(tries):
            with self.lock:
                url = next(self.urls)
            self._wait()
            try:
                r = self.s.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=60)
                j = r.json()
                if "error" in j or j.get("result") is None:
                    raise RuntimeError(f"{url}: {j.get('error') or 'null result'}")
                return j["result"]
            except Exception as e:  # rate limits, timeouts, bad JSON: back off and try another provider
                if i == tries - 1:
                    raise
                print(f"retry {i+1} {method} {params[:1]}: {str(e)[:120]}", file=sys.stderr)
                time.sleep(min(30, 1.5 ** i))


def h(x):
    return int(x, 16) if x else 0


def tx_rows(block):
    ts = h(block["timestamp"])
    n = h(block["number"])
    miner = block["miner"].lower()
    for t in block["transactions"]:
        auth = t.get("authorizationList") or []
        yield {
            "block": n,
            "ts": ts,
            "miner": miner,
            "hash": t["hash"],
            "tx_index": h(t["transactionIndex"]),
            "nonce": h(t["nonce"]),
            "from": t["from"].lower(),
            "to": (t.get("to") or "").lower(),
            "value_wei": str(h(t["value"])),
            "value_eth": h(t["value"]) / 1e18,
            "type": h(t.get("type", "0x0")),
            "selector": (t.get("input") or "0x")[:10],
            "delegates": ",".join(a["address"].lower() for a in auth),
        }


def log_rows(logs):
    for g in logs:
        tp = g["topics"]
        row = {
            "block": h(g["blockNumber"]),
            "tx_hash": g["transactionHash"],
            "log_index": h(g["logIndex"]),
            "address": g["address"].lower(),
            "topic0": tp[0],
            "ntopics": len(tp),
            "a1": ("0x" + tp[1][-40:]) if len(tp) > 1 else "",
            "a2": ("0x" + tp[2][-40:]) if len(tp) > 2 else "",
            "a3": ("0x" + tp[3][-40:]) if len(tp) > 3 else "",  # paymaster for UserOperationEvent
            "data": g["data"][:2 + 64 * 3],  # value for ERC-20; first 3 words for UserOperationEvent
        }
        yield row


def fetch_chunk(rpc, lrpc, chain, start, end):
    out = f"data/raw/{chain}"
    tf, lf = f"{out}/txs/{start}.parquet", f"{out}/logs/{start}.parquet"
    if os.path.exists(tf) and os.path.exists(lf):
        return start, "skip"
    txs, logs = [], []
    for b in range(start, end + 1):
        blk = rpc.call("eth_getBlockByNumber", [hex(b), True])
        txs.extend(tx_rows(blk))
    for b in range(start, end + 1, LOG_SPAN):
        e = min(end, b + LOG_SPAN - 1)
        res = lrpc.call("eth_getLogs", [{"fromBlock": hex(b), "toBlock": hex(e), "topics": [[TRANSFER, USEROP]]}])
        logs.extend(log_rows(res))
    os.makedirs(f"{out}/txs", exist_ok=True)
    os.makedirs(f"{out}/logs", exist_ok=True)
    # write logs last-but-atomically so a crash never leaves a half chunk that looks complete
    pd.DataFrame(txs).to_parquet(tf + ".tmp")
    pd.DataFrame(logs).to_parquet(lf + ".tmp")
    os.replace(tf + ".tmp", tf)
    os.replace(lf + ".tmp", lf)
    return start, f"{len(txs)} txs {len(logs)} logs"


def blocks(chain, start, end, workers):
    rpc, lrpc = Rpc(PROVIDERS[chain]), Rpc(LOG_PROVIDERS[chain])
    chunks = [(s, min(end, s + CHUNK - 1)) for s in range(start, end + 1, CHUNK)]
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        for i, (s, msg) in enumerate(ex.map(lambda c: fetch_chunk(rpc, lrpc, chain, *c), chunks)):
            print(f"[{i+1}/{len(chunks)}] {s}: {msg} ({time.time()-t0:.0f}s)", flush=True)


def find_window(chain, day):
    rpc = Rpc(PROVIDERS[chain][:1])
    t = int(dt.datetime.fromisoformat(day + "T00:00:00+00:00").timestamp())
    head = h(rpc.call("eth_blockNumber", []))
    lo, hi = 0, head
    while lo < hi:
        m = (lo + hi) // 2
        if h(rpc.call("eth_getBlockByNumber", [hex(m), False])["timestamp"]) < t:
            lo = m + 1
        else:
            hi = m
    print(day, lo)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["blocks", "find-window"])
    ap.add_argument("--chain", default="eth")
    ap.add_argument("--start", type=int)
    ap.add_argument("--end", type=int)
    ap.add_argument("--day")
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    if a.cmd == "blocks":
        blocks(a.chain, a.start, a.end, a.workers)
    else:
        find_window(a.chain, a.day)
