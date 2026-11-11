"""Injected ground truth on a local mainnet fork (Foundry anvil). Nothing here touches mainnet.

Start the fork first:   anvil --fork-url <rpc> --hardfork prague --port 8545
Then:                   python -m anvil.inject   (writes anvil/owners.json and anvil/blocks.json)

Every wallet is derived from a fixed seed, so the true owner of every address is known.
Scenarios (each one is a real transaction on the fork):
  S1 true positive   Alice's two wallets pay her own deposit address, which forwards to an exchange
  S2 rogue forwarder Bob and Carol pay a stranger who forwards each payment to the exchange
                     (Victor 2020's own stated limitation)
  S3 exchange-sent   a second exchange's hot wallet withdraws into Alice's deposit address
  S4 poisoning batch an attacker calls USDT.transferFrom(victim, x, 0) for Alice and Bob in one
                     transaction via Multicall3 (zero-value poisoning, Tsuchiya et al. 2025)
  S5 shared funder   the exchange funds a fresh wallet of Alice's and a fresh wallet of Carol's
  S6 shared sponsor  one paymaster sponsors UserOperations of Alice's and Bob's smart accounts
                     (the EntryPoint v0.7 code is swapped on the fork for a 30-byte contract that
                     emits the real UserOperationEvent, because the rule only reads that event)
  S7 7702 sweeper    Dave's wallet is delegated to a sweeper; Carol pays Dave, the ETH is swept
"""
import json
import subprocess
import time

import requests
from eth_hash.auto import keccak
from eth_keys import keys

RPC = "http://127.0.0.1:8545"
CAST = "/tmp/claude-0/foundry/cast"
USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"
ENTRYPOINT_V07 = "0x0000000071727de22e5e9d8baf0edac6f37da032"
USEROP = "49628fd1471006c1482da88028e9ce4dbb080b815c9b0344d39e5a8e6ec1419f"


def rpc(m, p):
    r = requests.post(RPC, json={"jsonrpc": "2.0", "id": 1, "method": m, "params": p}, timeout=60).json()
    if "error" in r:
        raise RuntimeError(r["error"])
    return r["result"]


def wallet(name):
    pk = keys.PrivateKey(keccak(f"evm-cluster-check:{name}".encode()))
    return pk.public_key.to_checksum_address().lower(), pk.to_hex()


def send(frm, to, value_eth=0.0, data="0x"):
    rpc("anvil_impersonateAccount", [frm])
    h = rpc("eth_sendTransaction", [{"from": frm, "to": to, "value": hex(int(value_eth * 1e18)), "data": data, "gas": hex(500000)}])
    rcpt = None
    for _ in range(100):  # anvil mines on submit, but the receipt can lag while fork state loads
        rcpt = rpc("eth_getTransactionReceipt", [h])
        if rcpt:
            break
        time.sleep(0.2)
    assert rcpt["status"] == "0x1", (frm, to, rcpt)
    return int(rcpt["blockNumber"], 16)


def word(x):
    return x[2:].rjust(64, "0") if isinstance(x, str) else hex(x)[2:].rjust(64, "0")


def main(exch, exch2):
    names = ["alice-1", "alice-2", "alice-3", "alice-deposit", "bob-1", "carol-1", "carol-2",
             "dave-1", "stranger-forwarder", "attacker", "bundler", "paymaster", "alice-sa", "bob-sa"]
    W = {n: wallet(n) for n in names}
    a = {n: W[n][0] for n in names}
    for n in names:
        rpc("anvil_setBalance", [a[n], hex(10 ** 19)])
    for e in (exch, exch2):
        rpc("anvil_setBalance", [e, hex(10 ** 21)])
    blocks = [int(rpc("eth_blockNumber", []), 16) + 1]
    # make "fresh" wallets fresh again: drop the setBalance top-up so their funding comes from the exchange
    for n in ("alice-3", "carol-2"):
        rpc("anvil_setBalance", [a[n], "0x0"])

    # S1 true positive: Alice -> her deposit -> exchange (fee-sized difference)
    send(a["alice-1"], a["alice-deposit"], 1.0)
    send(a["alice-deposit"], exch, 0.999)
    send(a["alice-2"], a["alice-deposit"], 0.5)
    send(a["alice-deposit"], exch, 0.4995)
    # S2 rogue forwarder
    send(a["bob-1"], a["stranger-forwarder"], 0.3)
    send(a["stranger-forwarder"], exch, 0.2995)
    send(a["carol-1"], a["stranger-forwarder"], 0.2)
    send(a["stranger-forwarder"], exch, 0.1995)
    # S3 a second exchange withdraws into Alice's deposit address, which forwards as usual
    send(exch2, a["alice-deposit"], 2.0)
    send(a["alice-deposit"], exch, 1.999)
    # S4 zero-value poisoning batch through Multicall3.aggregate3((address,bool,bytes)[])
    tf = lambda frm, to: "0x23b872dd" + word(frm) + word(to) + word(0)  # noqa: E731  transferFrom(from,to,0)
    calls = [(USDT, tf(a["alice-1"], a["attacker"])), (USDT, tf(a["bob-1"], a["attacker"]))]
    head = "0x82ad56cb" + word(0x20) + word(len(calls))
    tails, offs, cur = [], [], 0x20 * len(calls)
    for target, cd in calls:
        b = bytes.fromhex(cd[2:])
        t = word(target) + word(0) + word(0x60) + word(len(b)) + b.hex().ljust(((len(b) + 31) // 32) * 64, "0")
        offs.append(word(cur))
        cur += len(t) // 2
        tails.append(t)
    send(a["attacker"], MULTICALL3, 0, head + "".join(offs) + "".join(tails))
    # S5 the exchange funds two fresh wallets of different owners; each then makes its first tx
    send(exch, a["alice-3"], 0.05)
    send(exch, a["carol-2"], 0.05)
    send(a["alice-3"], a["alice-1"], 0.01)
    send(a["carol-2"], a["carol-1"], 0.01)
    # S6 shared paymaster: emitter at the EntryPoint address logs UserOperationEvent(hash, sender, paymaster)
    emitter = "0x604035602035600035" + "7f" + USEROP + "60006000a400"
    rpc("anvil_setCode", [ENTRYPOINT_V07, emitter])
    for i, sa in enumerate(("alice-sa", "bob-sa")):
        send(a["bundler"], ENTRYPOINT_V07, 0, "0x" + word(i + 1) + word(a[sa]) + word(a["paymaster"]))
    # S7 EIP-7702 sweeper: Dave delegates to a contract that forwards msg.value to the attacker
    sweeper = "0x" + "6000600060006000" + "34" + "73" + a["attacker"][2:] + "5af100"
    sweeper_at = "0x" + "77" * 20
    rpc("anvil_setCode", [sweeper_at, sweeper])
    subprocess.run([CAST, "send", "--rpc-url", RPC, "--private-key", W["dave-1"][1], "--auth", sweeper_at,
                    a["dave-1"]], check=True, capture_output=True)
    before = int(rpc("eth_getBalance", [a["dave-1"], "latest"]), 16)
    send(a["carol-1"], a["dave-1"], 0.1)
    after = int(rpc("eth_getBalance", [a["dave-1"], "latest"]), 16)
    blocks.append(int(rpc("eth_blockNumber", []), 16))

    owners = {a[n]: n.split("-")[0] for n in names if n not in ("alice-deposit",)}
    owners[a["alice-deposit"]] = "exchange-deposit"
    owners[exch], owners[exch2] = "exchange-1", "exchange-2"
    json.dump(owners, open("anvil/owners.json", "w"), indent=1)
    json.dump({"blocks": blocks, "exch": exch, "exch2": exch2, "sweeper": sweeper_at,
               "dave_balance_change_wei": after - before, "dave_received_wei": int(0.1e18)},
              open("anvil/blocks.json", "w"), indent=1)
    print("blocks", blocks, "dave balance change", after - before)


if __name__ == "__main__":
    import pandas as pd
    por = pd.read_parquet("data/raw/groundtruth/por.parquet")
    okx = por[por.exchange == "OKX"].address.iloc[0]
    kucoin = por[por.exchange == "KuCoin"].address.iloc[0]
    main(okx, kucoin)
