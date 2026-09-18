import json
from pathlib import Path

import numpy as np


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

CHECKPOINT_PATH = ROOT / "models" / "sharp_bdq_v2" / "checkpoint.npz"
GOLDEN_PATH = ROOT / "models" / "kaggle_final" / "golden_vector.json"


# ============================================================
# CONSTANTS
# ============================================================

N_FEATURES = 305
N_BRANCHES = 28
N_LEVELS = 3


# ============================================================
# HELPERS
# ============================================================

def load_checkpoint(path):
    """Load the trained SHARP BDQ checkpoint."""
    data = np.load(path)

    required = ["mean", "sd", "w", "b", "v", "vb", "a", "ab"]

    for name in required:
        if name not in data:
            raise RuntimeError(
                f"Checkpoint is missing required array: {name}"
            )

    return {name: data[name] for name in required}


def forward(params, x):
    """
    Exact SHARP BDQ v2 forward pass.

    Architecture:
        Input: 305
        Hidden: 128 ReLU
        Value stream: 1
        Advantage stream: 28 × 3

    Formula recovered from the project's
    validate_sharp_model_end_to_end_v1.py.
    """

    h = np.maximum(
        0,
        x @ params["w"] + params["b"]
    )

    advantage = (
        h @ params["a"] + params["ab"]
    ).reshape(
        -1,
        N_BRANCHES,
        N_LEVELS
    )

    value = (
        h @ params["v"] + params["vb"]
    ).reshape(
        -1,
        1,
        1
    )

    q = value + advantage - advantage.mean(
        2,
        keepdims=True
    )

    return q


# ============================================================
# MAIN TEST
# ============================================================

def main():

    print("=" * 60)
    print("SHARP BDQ v2 — GOLDEN VECTOR TEST")
    print("=" * 60)


    # ========================================================
    # 1. LOAD CHECKPOINT
    # ========================================================

    print("\n1. Loading checkpoint:")
    print(CHECKPOINT_PATH)

    if not CHECKPOINT_PATH.exists():
        raise FileNotFoundError(
            f"Checkpoint not found:\n{CHECKPOINT_PATH}"
        )

    params = load_checkpoint(CHECKPOINT_PATH)

    print("\nCheckpoint contents:")

    for name, value in params.items():
        print(f"  {name:>5} : {value.shape}")


    # ========================================================
    # 2. CHECK MODEL SHAPES
    # ========================================================

    print("\n2. Checking model shapes...")

    assert params["mean"].shape == (N_FEATURES,)
    assert params["sd"].shape == (N_FEATURES,)

    assert params["w"].shape == (N_FEATURES, 128)
    assert params["b"].shape == (128,)

    assert params["v"].shape == (128, 1)
    assert params["vb"].shape == (1,)

    assert params["a"].shape == (128, N_BRANCHES * N_LEVELS)
    assert params["ab"].shape == (N_BRANCHES * N_LEVELS,)

    print("  ✅ All checkpoint shapes correct")
    print("  ✅ 305 input features")
    print("  ✅ 128 hidden units")
    print("  ✅ 28 branches × 3 levels")


    # ========================================================
    # 3. LOAD GOLDEN VECTOR
    # ========================================================

    print("\n3. Loading golden vector:")
    print(GOLDEN_PATH)

    if not GOLDEN_PATH.exists():
        raise FileNotFoundError(
            f"Golden vector not found:\n{GOLDEN_PATH}"
        )

    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        golden = json.load(f)

    state = np.asarray(
        golden["state"],
        dtype=np.float32
    )

    expected_q = np.asarray(
        golden["expected_q"],
        dtype=np.float32
    )

    expected_action = np.asarray(
        golden["expected_greedy_action"],
        dtype=np.int64
    )

    print(f"  State shape: {state.shape}")
    print(f"  Expected Q shape: {expected_q.shape}")

    assert state.shape == (N_FEATURES,)
    assert expected_q.shape == (N_BRANCHES, N_LEVELS)
    assert expected_action.shape == (N_BRANCHES,)

    print("  ✅ Golden vector structure valid")


    # ========================================================
    # 4. USE GOLDEN STATE DIRECTLY
    # ========================================================

    print("\n4. Loading golden state...")

    # IMPORTANT:
    #
    # golden_vector.json already contains the NORMALIZED
    # model input.
    #
    # Therefore:
    #
    #     DO NOT do:
    #     (state - mean) / sd
    #
    # here.
    #
    # For live/raw states later, normalization will be:
    #
    #     x = (raw_state - mean) / sd
    #
    # But the golden vector is already x.

    x = state.astype(np.float32)

    print("  ✅ Golden state used directly")
    print("  ✅ No second normalization applied")


    # ========================================================
    # 5. RUN BDQ INFERENCE
    # ========================================================

    print("\n5. Running BDQ inference...")

    q = forward(
        params,
        x.reshape(1, N_FEATURES)
    )[0]

    print(f"  Q-value shape: {q.shape}")

    assert q.shape == (
        N_BRANCHES,
        N_LEVELS
    )

    print("  ✅ Q-value shape correct")


    # ========================================================
    # 6. COMPARE Q VALUES WITH GOLDEN VECTOR
    # ========================================================

    print("\n6. Golden Q comparison:")

    difference = np.abs(
        q - expected_q
    )

    max_difference = float(
        difference.max()
    )

    mean_difference = float(
        difference.mean()
    )

    print(
        f"  Maximum difference: "
        f"{max_difference:.12e}"
    )

    print(
        f"  Mean difference: "
        f"{mean_difference:.12e}"
    )

    if max_difference < 1e-8:
        print("  ✅ Q-VALUES MATCH GOLDEN VECTOR")
    else:
        print("  ❌ Q-VALUES DO NOT MATCH")

        # Show the largest mismatches to help debugging
        flat_indices = np.argsort(
            difference.ravel()
        )[::-1]

        print("\n  Largest Q-value differences:")

        for flat_index in flat_indices[:5]:

            branch, level = np.unravel_index(
                flat_index,
                difference.shape
            )

            print(
                f"    slot {branch:02d}, "
                f"level {level}: "
                f"got={q[branch, level]:.8f}, "
                f"expected={expected_q[branch, level]:.8f}, "
                f"diff={difference[branch, level]:.8f}"
            )

        raise AssertionError(
            "BDQ Q-values do not match the golden vector."
        )


    # ========================================================
    # 7. CHECK LEGAL ACTIONS
    # ========================================================

    print("\n7. Checking legal actions...")

    device_present = np.asarray(
        golden["device_present"],
        dtype=bool
    )

    legal_levels = np.asarray(
        golden["legal_levels"],
        dtype=bool
    )

    assert device_present.shape == (
        N_BRANCHES,
    )

    assert legal_levels.shape == (
        N_BRANCHES,
        N_LEVELS
    )

    allowed = (
        device_present[:, None]
        & legal_levels
    )

    masked_q = np.where(
        allowed,
        q,
        -np.inf
    )

    greedy_action = np.argmax(
        masked_q,
        axis=1
    )

    print("\n  Greedy actions:")

    for slot in range(N_BRANCHES):

        print(
            f"    slot {slot:02d} "
            f"got={greedy_action[slot]} "
            f"expected={expected_action[slot]}"
        )

    if np.array_equal(
        greedy_action,
        expected_action
    ):
        print("\n  ✅ GREEDY ACTIONS MATCH")
    else:
        print("\n  ❌ GREEDY ACTIONS DO NOT MATCH")

        print("\n  Got:")
        print(greedy_action.tolist())

        print("\n  Expected:")
        print(expected_action.tolist())

        raise AssertionError(
            "Greedy actions do not match golden vector."
        )


    # ========================================================
    # 8. FINAL RESULT
    # ========================================================

    print("\n" + "=" * 60)
    print("✅ SHARP BDQ v2 GOLDEN TEST PASSED")
    print("=" * 60)

    print("\nVerified:")
    print("  ✅ Checkpoint loads")
    print("  ✅ Model dimensions are correct")
    print("  ✅ 305-feature input")
    print("  ✅ Exact BDQ forward pass")
    print("  ✅ Golden Q-values match")
    print("  ✅ Legal-action masking matches")
    print("  ✅ Greedy actions match")

    print("\nExpected golden actions:")
    print(expected_action.tolist())

    print("\nNext step:")
    print("  → Connect the verified RL inference to the SHARP")
    print("    state/intent pipeline.")
    print("=" * 60)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()