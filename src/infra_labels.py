"""Label transfers that come from infrastructure rather than from the owner's own choices.

poison_zero      zero-value ERC-20 Transfer (Tsuchiya et al.'s zero-value poisoning pattern)
poison_lookalike any transfer between an account V and a look-alike L of an address R that V
                 had already paid: same first 3 and last 4 hex characters (a>=3, b>=4, as in
                 Tsuchiya et al. 2025), L != R, L first seen after R
sweeper          transfer touching an EIP-7702 sweeper contract from the SweeperHunter release,
                 a victim listed there, or an account seen delegating to such a contract here
aa_infra         transfer touching an ERC-4337 EntryPoint, bundler (outer sender of handleOps)
                 or paymaster
"""
import json

import pandas as pd
import rlp
from eth_hash.auto import keccak
from eth_keys import keys

ENTRYPOINTS = {
    "0x5ff137d4b0fdcd49dca30c7cf57e578a026d2789",  # v0.6
    "0x0000000071727de22e5e9d8baf0edac6f37da032",  # v0.7
    "0x4337084d9e255ff0702461cf8895ce9e3b5ff108",  # v0.8
}
SWEEPER_COMMIT = "b623678970ef6aa2e61c27720a9da9c58267fea2"
SWEEPER_BASE = f"https://raw.githubusercontent.com/liziwei1/SweeperHunter/{SWEEPER_COMMIT}/dataset"
HUB_LIMIT = 2000  # Tsuchiya exclude victims with so many counterparties that look-alikes occur by chance


def key(a):
    return a[2:5] + a[-4:]


def lookalike_edges(tr):
    """Index of transfers between a victim and a look-alike of one of its earlier payees."""
    paid = tr[tr.raw != "0"][["src", "dst", "block"]]
    first_paid = paid.groupby(["src", "dst"]).block.min().reset_index().rename(columns={"src": "v", "dst": "r", "block": "rb"})
    cp = pd.concat([
        tr[["src", "dst", "block"]].rename(columns={"src": "v", "dst": "c"}),
        tr[["dst", "src", "block"]].rename(columns={"dst": "v", "src": "c"}),
    ])
    first_seen = cp.groupby(["v", "c"]).block.min().reset_index()
    deg = first_seen.groupby("v").size()
    first_seen = first_seen[first_seen.v.isin(deg[deg <= HUB_LIMIT].index)]
    first_seen["k"] = first_seen.c.map(key)
    first_paid["k"] = first_paid.r.map(key)
    m = first_seen.merge(first_paid, on=["v", "k"])
    m = m[(m.c != m.r) & (m.block > m.rb)]
    pairs = pd.MultiIndex.from_arrays([m.v, m.c])
    fwd = pd.MultiIndex.from_arrays([tr.src, tr.dst]).isin(pairs)
    rev = pd.MultiIndex.from_arrays([tr.dst, tr.src]).isin(pairs)
    return pd.Series(fwd | rev, index=tr.index), m[["v", "c", "r"]].drop_duplicates()


def recover_authorities(txs):
    """(authority, delegate) for every EIP-7702 authorization tuple in the window."""
    out = []
    for blob in txs.loc[txs.auth != "", "auth"]:
        for a in json.loads(blob):
            try:
                msg = b"\x05" + rlp.encode([int(a["chainId"], 16), bytes.fromhex(a["address"][2:]), int(a["nonce"], 16)])
                sig = keys.Signature(vrs=(int(a["yParity"], 16), int(a["r"], 16), int(a["s"], 16)))
                auth = sig.recover_public_key_from_msg_hash(keccak(msg)).to_checksum_address().lower()
                out.append((auth, a["address"].lower()))
            except Exception:  # malformed or high-s signatures are invalid on chain too
                continue
    return pd.DataFrame(out, columns=["authority", "delegate"]).drop_duplicates()


def sweeper_sets(txs, sweeper_csv, victims_csv=None):
    contracts = set(pd.read_csv(sweeper_csv).contract.str.lower())
    auth = recover_authorities(txs)
    victims = set(auth[auth.delegate.isin(contracts)].authority)
    if victims_csv is not None:
        victims |= set(pd.read_csv(victims_csv, usecols=["address_to"], dtype=str).address_to.dropna().str.lower())
    return contracts, victims, auth


def aa_sets(txs, uo):
    bundlers = set(txs[txs.to.isin(ENTRYPOINTS)]["from"]) | set(uo.bundler.dropna())
    paymasters = set(uo.paymaster) - {"0x" + "0" * 40}
    return ENTRYPOINTS | bundlers | paymasters, bundlers, paymasters


def label(tr, txs, uo, sweeper_csv, victims_csv=None):
    tr = tr.copy()
    tr["poison_zero"] = (tr.kind == "erc20") & (tr.raw == "0")
    tr["poison_lookalike"], la = lookalike_edges(tr)
    contracts, victims, auth = sweeper_sets(txs, sweeper_csv, victims_csv)
    sw = contracts | victims
    tr["sweeper"] = tr.src.isin(sw) | tr.dst.isin(sw)
    aa, bundlers, paymasters = aa_sets(txs, uo)
    tr["aa_infra"] = tr.src.isin(aa) | tr.dst.isin(aa)
    info = {"lookalike_pairs": len(la), "sweeper_contracts": len(contracts), "sweeper_victims": len(victims),
            "delegations_in_window": len(auth), "bundlers": len(bundlers), "paymasters": len(paymasters)}
    return tr, info, {"sweeper": sw, "aa": aa, "bundlers": bundlers, "paymasters": paymasters}
