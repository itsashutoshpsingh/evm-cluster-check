"""Connected components over link edges: every rule outputs (a, b) pairs, this turns them into clusters."""
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components


def components(pairs, drop=()):
    """pairs: DataFrame with columns a, b. Returns Series address -> cluster id (only linked addresses).

    `drop` addresses are removed after linking (Victor removes deposit addresses from user clusters).
    """
    if len(pairs) == 0:
        return pd.Series(dtype="int64", name="cluster")
    codes, uniq = pd.factorize(pd.concat([pairs.a, pairs.b], ignore_index=True))
    n = len(uniq)
    a, b = codes[: len(pairs)], codes[len(pairs):]
    m = coo_matrix((np.ones(len(a), dtype=np.int8), (a, b)), shape=(n, n))
    _, lab = connected_components(m, directed=False)
    s = pd.Series(lab, index=uniq, name="cluster")
    if len(drop):
        s = s[~s.index.isin(set(drop))]
    return s


def cap(s, max_size):
    """Drop clusters larger than max_size (Victor ignored entities with >1,000 addresses)."""
    size = s.map(s.value_counts())
    return s[size <= max_size]
