"""JUDGE SIDE: legal non-deterministic execution for Gate 4 (EXPERIMENT_PRE_REGISTRATION.md section G4).
Each manipulation command independently has no effect with probability P and gets the environment's own reply to a
command without effect, "Nothing happens." It still counts as a step. Movement, examine and look are never perturbed.
The generator is seeded per game and consumed only by manipulation commands, so the k-th manipulation attempt in a game
fails or not identically in every arm."""

import random

VERBS = ("take", "move", "put", "open", "close", "clean", "heat", "cool", "use")
P = 0.2


class Perturb:
    def __init__(self, seed):
        self.rng = random.Random(seed)

    def fails(self, cmd):
        return cmd.split(" ")[0] in VERBS and self.rng.random() < P
