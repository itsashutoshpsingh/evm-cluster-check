"""Small hand-built cases for every rule and metric. No network needed."""
import json

import pandas as pd
import pytest
import rlp
from eth_hash.auto import keccak
from eth_keys import keys

from src import groundtruth, score, taint
from src.cluster import components
from src.heuristics import cospend, dar, funder
from src.infra_labels import lookalike_edges, recover_authorities

A = lambda c: "0x" + c * 40 if len(c) == 1 else c  # noqa: E731


def tr(rows):
    cols = ["block", "src", "dst", "asset", "raw", "amount", "kind"]
    d = pd.DataFrame(rows, columns=cols)
    d["ts"] = d.block * 12
    d["tx_hash"] = ["0xt%d" % i for i in range(len(d))]
    d["log_index"] = range(len(d))
    return d


def test_extract_owners_ignores_comments_and_other_chains():
    js = """
    ethereum: { ownTokens: ['0x75231f58b43240c9718dd58b4967c5114342a86c'],
      owners: ['0x77134cbc06cb00b66f4c7e623d5fdbf6777635ec', // hot
               // '0x1111111111111111111111111111111111111111',
               '0x742d35Cc6634C0532925a3b844Bc454e4438f44e'] },
    bsc: { owners: ['0x2222222222222222222222222222222222222222'] }"""
    assert groundtruth.extract(js) == ["0x742d35cc6634c0532925a3b844bc454e4438f44e",
                                       "0x77134cbc06cb00b66f4c7e623d5fdbf6777635ec"]


def test_address_on_two_lists_is_dropped():
    df = pd.DataFrame({"address": ["0xa", "0xa", "0xb"], "exchange": ["X", "Y", "X"]})
    out, n = groundtruth.drop_overlaps(df)
    assert n == 1 and list(out.address) == ["0xb"]
    assert out.groupby("address").exchange.nunique().max() == 1


def test_dar_links_two_users_of_one_deposit_address():
    u1, u2, d, ex = A("1"), A("2"), A("d"), A("e")
    t = tr([
        (100, u1, d, "ETH", "1", 1.000, "eth"),
        (110, d, ex, "ETH", "1", 0.995, "eth"),     # fee-sized difference: deposit address
        (200, u2, d, "ETH", "2", 2.000, "eth"),
        (205, d, ex, "ETH", "2", 1.992, "eth"),
        (300, A("3"), A("4"), "ETH", "1", 1.0, "eth"),  # unrelated
    ])
    p = dar.paths(t, {ex})
    s, deps, _ = dar.clusters(p, "victor", exch={ex})
    assert deps == {d}
    assert s[u1] == s[u2] and d not in s.index


def test_dar_rejects_slow_or_lossy_forwards():
    u, d, ex = A("1"), A("d"), A("e")
    t = tr([(100, u, d, "ETH", "1", 1.0, "eth"), (100 + dar.TMAX + 1, d, ex, "ETH", "1", 0.999, "eth"),
            (100, u, A("c"), "ETH", "1", 1.0, "eth"), (101, A("c"), ex, "ETH", "1", 0.95, "eth")])
    assert dar.paths(t, {ex}).empty


def test_dar_token_forward_must_be_exact():
    u, d, ex, tok = A("1"), A("d"), A("e"), A("7")
    ok = tr([(1, u, d, tok, "500", 500.0, "erc20"), (2, d, ex, tok, "500", 500.0, "erc20")])
    off = tr([(1, u, d, tok, "500", 500.0, "erc20"), (2, d, ex, tok, "499", 499.0, "erc20")])
    assert len(dar.paths(ok, {ex})) == 1 and dar.paths(off, {ex}).empty


def test_victor_variant_excludes_exchange_senders_but_naive_does_not():
    ex1, ex2, d, u = A("e"), A("f"), A("d"), A("1")
    t = tr([(1, ex2, d, "ETH", "1", 1.0, "eth"), (2, d, ex1, "ETH", "1", 0.999, "eth"),
            (3, u, d, "ETH", "1", 1.0, "eth"), (4, d, ex1, "ETH", "1", 0.999, "eth")])
    p = dar.paths(t, {ex1})
    naive, _, _ = dar.clusters(p, "naive")
    vic, _, _ = dar.clusters(p, "victor", exch={ex1, ex2})
    assert naive[ex2] == naive[u]
    assert ex2 not in vic.index


def test_funder_uses_last_eth_before_first_tx():
    f1, f2, x = A("f"), A("a"), A("9")
    txs = pd.DataFrame({"hash": ["0xt0", "0xt1", "0xt2"], "tx_index": [0, 0, 0], "from": [f1, f2, x],
                        "nonce": [5, 7, 0], "block": [10, 20, 30]})
    t = tr([(10, f1, x, "ETH", "1", 0.1, "eth"), (20, f2, x, "ETH", "1", 0.1, "eth")])
    f = funder.funding(txs, t)
    assert f.set_index("fresh").funder[x] == f2


def test_cospend_links_spoofed_victims_in_one_tx():
    v1, v2, atk, tok = A("1"), A("2"), A("a"), A("7")
    t = tr([(1, v1, atk, tok, "0", 0.0, "erc20"), (1, v2, atk, tok, "0", 0.0, "erc20")])
    t["tx_hash"] = "0xpoison"
    lk = cospend.links(t, eoas={v1, v2})
    s = cospend.clusters(lk)
    assert s[v1] == s[v2]
    assert cospend.clusters(lk, drop_txs={"0xpoison"}).empty


def test_lookalike_matches_prefix3_suffix4_only():
    v = A("1")
    real = "0xabc" + "0" * 33 + "1234"
    fake = "0xabc" + "f" * 33 + "1234"
    near = "0xab0" + "f" * 33 + "1234"  # prefix only 2: not a look-alike
    t = tr([(1, v, real, "ETH", "5", 5.0, "eth"), (2, fake, v, A("7"), "0", 0.0, "erc20"),
            (3, near, v, A("7"), "0", 0.0, "erc20")])
    hit, pairs = lookalike_edges(t)
    assert list(hit) == [False, True, False]
    assert len(pairs) == 1


def test_eip7702_authority_recovery():
    pk = keys.PrivateKey(b"\x01" * 32)
    delegate = "0x" + "ab" * 20
    msg = b"\x05" + rlp.encode([1, bytes.fromhex(delegate[2:]), 0])
    sig = pk.sign_msg_hash(keccak(msg))
    auth = [{"chainId": "0x1", "address": delegate, "nonce": "0x0",
             "yParity": hex(sig.v), "r": hex(sig.r), "s": hex(sig.s)}]
    out = recover_authorities(pd.DataFrame({"auth": [json.dumps(auth)]}))
    assert out.authority.iloc[0] == pk.public_key.to_checksum_address().lower()


def test_nhop_respects_time_order():
    s, a, b = A("5"), A("a"), A("b")
    t = tr([(10, a, b, "ETH", "1", 1.0, "eth"),   # a pays b before a is tainted: must not count
            (20, s, a, "ETH", "1", 1.0, "eth")])
    r = taint.nhop(t, [s]).set_index("address").hop
    assert r[a] == 1 and b not in r.index


def test_haircut_share():
    s, a, b = A("5"), A("a"), A("b")
    t = tr([(1, s, a, "ETH", "1", 1.0, "eth"), (2, b, a, "ETH", "3", 3.0, "eth")])
    assert taint.haircut(t, [s])[a] == pytest.approx(0.25)


def test_metrics_on_known_partition():
    labels = pd.DataFrame({"address": ["a1", "a2", "b1", "b2"], "exchange": ["A", "A", "B", "B"]})
    perfect = pd.Series({"a1": 0, "a2": 0, "b1": 1, "b2": 1})
    m = score.evaluate(perfect, labels)
    assert m["pair_precision"] == 1 and m["pair_recall"] == 1 and m["clusters_with_2plus_exchanges"] == 0
    assert m["aer"] == 0
    merged = pd.Series({"a1": 0, "a2": 0, "b1": 0, "b2": 0, "u": 0})
    m = score.evaluate(merged, labels)
    assert m["pair_precision"] == pytest.approx(2 / 6)
    assert m["cross_exchange_pairs_linked"] == 4 and m["clusters_with_2plus_exchanges"] == 1
    assert m["pw_precision"] == pytest.approx(1 / 4)  # seed sees 4 others, 1 is its own exchange


def test_components_drop():
    s = components(pd.DataFrame({"a": ["x", "y"], "b": ["d", "d"]}), drop={"d"})
    assert set(s.index) == {"x", "y"} and s["x"] == s["y"]
