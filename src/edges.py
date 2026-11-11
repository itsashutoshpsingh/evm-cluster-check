"""Turn fetched Parquet into one table of value transfers.

Columns: block, ts, tx_hash, log_index, src, dst, asset, raw (exact integer as string),
amount (float, native units: ETH for 'ETH', raw token units otherwise), kind ('eth'|'erc20').
"""
import glob

import pandas as pd

TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USEROP = "0x49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f"
ZERO = "0x" + "0" * 40


def read(chain, what, blocks=None):
    files = sorted(glob.glob(f"data/raw/{chain}/{what}/*.parquet"))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    if blocks is not None:
        df = df[df.block.between(*blocks)]
    return df.reset_index(drop=True)


def word(data, i=0):
    """i-th 32-byte word of ABI data as an int (0 if absent)."""
    s = data[2 + 64 * i: 2 + 64 * (i + 1)]
    return int(s, 16) if s else 0


def transfers(txs, logs):
    eth = txs[(txs.value_wei != "0") & (txs.to != "")]
    eth = pd.DataFrame({
        "block": eth.block, "ts": eth.ts, "tx_hash": eth.hash, "log_index": -1,
        "src": eth["from"], "dst": eth.to, "asset": "ETH",
        "raw": eth.value_wei, "amount": eth.value_eth, "kind": "eth",
    })
    lg = logs[(logs.topic0 == TRANSFER) & (logs.ntopics == 3)]  # 3 topics = ERC-20; 4 = ERC-721
    raw = lg.data.map(word)
    ts = txs.drop_duplicates("block").set_index("block").ts
    tok = pd.DataFrame({
        "block": lg.block, "ts": lg.block.map(ts), "tx_hash": lg.tx_hash, "log_index": lg.log_index,
        "src": lg.a1, "dst": lg.a2, "asset": lg.address,
        "raw": raw.astype(str), "amount": raw.astype(float), "kind": "erc20",
    })
    out = pd.concat([eth, tok], ignore_index=True)
    return out[(out.src != out.dst)].reset_index(drop=True)


def userops(logs, txs):
    """ERC-4337 UserOperationEvent rows with the bundler (outer tx sender) attached."""
    u = logs[logs.topic0 == USEROP]
    sender_of = txs.set_index("hash")["from"]
    return pd.DataFrame({
        "block": u.block, "tx_hash": u.tx_hash, "entrypoint": u.address,
        "sender": u.a2, "paymaster": u.a3, "bundler": u.tx_hash.map(sender_of),
    }).reset_index(drop=True)
