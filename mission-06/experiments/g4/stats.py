"""Statistics for Gate 4 (EXPERIMENT_PRE_REGISTRATION.md section G4): Wilson 95 % interval for a rate; for paired
binary outcomes on the same games, the difference with a bootstrap 95 % interval (10,000 resamples of games, seed 70)
and the exact two-sided McNemar p-value; for paired step counts, the mean difference with a bootstrap interval."""

import math
import random

Z = 1.959963984540054


def wilson(k, n):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (c - h, c + h)


def mcnemar_exact(a, b):
    """a, b: paired 0/1 lists. Two-sided exact binomial test on the discordant pairs."""
    n10 = sum(1 for x, y in zip(a, b) if x and not y)
    n01 = sum(1 for x, y in zip(a, b) if y and not x)
    n = n10 + n01
    if n == 0:
        return 1.0, n10, n01
    k = min(n10, n01)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p), n10, n01


def paired_diff(a, b, reps=10000, seed=70):
    """mean(a) - mean(b) over paired items, with a percentile bootstrap 95 % interval."""
    n = len(a)
    rng = random.Random(seed)
    d = [x - y for x, y in zip(a, b)]
    est = sum(d) / n
    boots = []
    for _ in range(reps):
        s = 0
        for _ in range(n):
            s += d[rng.randrange(n)]
        boots.append(s / n)
    boots.sort()
    return est, (boots[int(0.025 * reps)], boots[int(0.975 * reps) - 1])
