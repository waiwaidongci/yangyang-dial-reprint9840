"""Generate the historical register, evaluation batches and next-shift pieces."""

from random import Random

from .settings import COLUMNS

PLATES = ("DP-17", "DP-24", "DP-36", "DP-41", "DP-52", "DP-63")
INKS = ("INK-BLK", "INK-IVY", "INK-BLU", "INK-RED")
PLATE_RISK = (0.05, 0.09, 0.15, 0.32, 0.52, 0.65)
INK_ADJUSTMENT = (-0.03, 0.00, 0.03, 0.12)


def demo_rows() -> list[dict]:
    rng = Random(251126)
    rows = []
    for split, prefix, batch_total, batch_size in (
        ("train", "H", 18, 6),
        ("holdout", "V", 5, 8),
        ("pending", "P", 4, 6),
    ):
        for batch in range(1, batch_total + 1):
            batch_id = f"DP-{prefix}{batch:02d}"
            batch_adjustment = rng.choice((-0.06, 0, 0.04))
            for piece in range(1, batch_size + 1):
                plate_index = (batch + (piece - 1) // 2) % len(PLATES)
                ink_index = (2 * batch + piece) % len(INKS)
                plate = PLATES[plate_index]
                ink = INKS[ink_index]
                risk = PLATE_RISK[plate_index] + INK_ADJUSTMENT[ink_index] + batch_adjustment
                if split == "train" and batch == 18 and piece == 6:
                    plate, risk = "DP-R08", 0.85
                if split == "holdout" and batch == 5 and piece <= 3:
                    plate = "DP-N72"
                if split == "holdout" and batch == 4 and piece == 2:
                    ink = "INK-GRY"
                if split == "pending" and batch == 1 and piece <= 2:
                    plate = "DP-N72"
                if split == "pending" and batch == 2 and piece <= 3:
                    ink = "INK-GRY"
                target = None if split == "pending" else int(rng.random() < risk)
                values = (f"{batch_id}-{piece:02d}", batch_id, split, plate, ink, target)
                rows.append(dict(zip(COLUMNS, values)))
    return rows
