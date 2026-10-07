"""Control-variability grid analysis (Magni et al., J Diabetes Sci Technol 2008;2(4):630-635).

Each point is one subject-period (here: one simulated day) plotted at X = minimum BG (axis
reversed, 110 -> 50 mg/dL) and Y = maximum BG (110 -> 400 mg/dL). Nine rectangular zones:

==========  ===============  ==================
zone        X = min BG       Y = max BG
==========  ===============  ==================
A           110-90           110-180
Lower B     90-70            110-180
B           90-70            180-300
Upper B     110-90           180-300
Lower C     < 70             110-180
Upper C     110-90           > 300
Lower D     < 70             180-300
Upper D     90-70            > 300
E           < 70             > 300
==========  ===============  ==================

Magni gives the outer edges as strict (X < 70, Y > 300), so 70 belongs to the 90-70 column and
300 to the 180-300 row. The 90 and 180 edges are written as closed on both sides; we resolve
them the same way (a boundary value belongs to the safer cell): min BG = 90 is in the A column
and max BG = 180 in the bottom row, which also matches the inclusive 70-180 target range.
Values beyond the plotted axes (min > 110, max < 110, min < 50, max > 400) are classified by
the same rules and only clipped for drawing.
"""

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import numpy.typing as npt

ZONES = ("A", "Lower B", "B", "Upper B", "Lower C", "Upper C", "Lower D", "Upper D", "E")

# Grid rows indexed by max-BG band (<=180, (180,300], >300), columns by min-BG band
# (>=90, [70,90), <70).
_GRID = (
    ("A", "Lower B", "Lower C"),
    ("Upper B", "B", "Lower D"),
    ("Upper C", "Upper D", "E"),
)
_MIN_EDGES = (90.0, 70.0)
_MAX_EDGES = (180.0, 300.0)
X_TICKS = (110.0, 90.0, 70.0, 50.0)
Y_TICKS = (110.0, 180.0, 300.0, 400.0)


def classify(min_bg: float, max_bg: float) -> str:
    if min_bg > max_bg:
        raise ValueError(f"min BG {min_bg} exceeds max BG {max_bg}")
    col = 0 if min_bg >= _MIN_EDGES[0] else 1 if min_bg >= _MIN_EDGES[1] else 2
    row = 0 if max_bg <= _MAX_EDGES[0] else 1 if max_bg <= _MAX_EDGES[1] else 2
    return _GRID[row][col]


def daily_extremes(
    bg_mg_dl: npt.ArrayLike, samples_per_day: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Per-day (min, max) of a regularly sampled trace starting at midnight.

    A trailing partial day is dropped so every point covers the same observation period.
    """
    bg = np.asarray(bg_mg_dl, dtype=float)
    days = bg.size // samples_per_day
    if days == 0:
        raise ValueError("Trace shorter than one day")
    per_day = bg[: days * samples_per_day].reshape(days, samples_per_day)
    return per_day.min(axis=1), per_day.max(axis=1)


def summarize(mins: npt.ArrayLike, maxs: npt.ArrayLike) -> dict[str, float]:
    """Percent of points per zone plus Magni's macro-zones (A, A+B, C, D, E, D+E)."""
    lo = np.asarray(mins, dtype=float)
    hi = np.asarray(maxs, dtype=float)
    if lo.shape != hi.shape or lo.size == 0:
        raise ValueError("Need equally sized, non-empty min/max arrays")
    counts: dict[str, int] = dict.fromkeys(ZONES, 0)
    for a, b in zip(lo, hi, strict=True):
        counts[classify(float(a), float(b))] += 1
    pct = {z: 100.0 * c / lo.size for z, c in counts.items()}
    b_total = pct["Lower B"] + pct["B"] + pct["Upper B"]
    pct["A+B"] = pct["A"] + b_total
    pct["C"] = pct["Lower C"] + pct["Upper C"]
    pct["D"] = pct["Lower D"] + pct["Upper D"]
    pct["D+E"] = pct["D"] + pct["E"]
    return pct


def _x_pos(min_bg: npt.ArrayLike) -> npt.NDArray[np.float64]:
    # Reversed axis: 110 at 0, 50 at 3; one unit per zone column.
    return np.interp(np.asarray(min_bg, dtype=float), X_TICKS[::-1], (3.0, 2.0, 1.0, 0.0))


def _y_pos(max_bg: npt.ArrayLike) -> npt.NDArray[np.float64]:
    # Piecewise-linear so the three zone rows are square, as in Magni's Fig. 1.
    return np.interp(np.asarray(max_bg, dtype=float), Y_TICKS, (0.0, 1.0, 2.0, 3.0))


_ZONE_COLORS = {"A": "#2e7d32", "B": "#81c784", "C": "#fff176", "D": "#ffb74d", "E": "#e57373"}


def plot(
    panels: Mapping[str, tuple[npt.ArrayLike, npt.ArrayLike]], path: str | Path, title: str
) -> None:
    """One CVGA panel per entry ``label -> (daily mins, daily maxs)``; saved as PNG."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, axes = plt.subplots(1, len(panels), figsize=(5.2 * len(panels), 5.2), squeeze=False)
    for ax, (label, (mins, maxs)) in zip(axes[0], panels.items(), strict=True):
        for row in range(3):
            for col in range(3):
                zone = _GRID[row][col]
                ax.add_patch(
                    Rectangle(
                        (col, row), 1, 1, color=_ZONE_COLORS[zone.split()[-1]], alpha=0.35, lw=0
                    )
                )
                ax.text(col + 0.5, row + 0.5, zone, ha="center", va="center", fontsize=9)
        x = _x_pos(np.clip(np.asarray(mins, dtype=float), X_TICKS[-1], X_TICKS[0]))
        y = _y_pos(np.clip(np.asarray(maxs, dtype=float), Y_TICKS[0], Y_TICKS[-1]))
        ax.scatter(x, y, s=8, c="black", alpha=0.5)
        summary = summarize(mins, maxs)
        ax.set_title(f"{label}\nA+B {summary['A+B']:.0f}%  D+E {summary['D+E']:.0f}%")
        ax.set_xticks(range(4), [f"{v:.0f}" for v in X_TICKS])
        ax.set_yticks(range(4), [f"{v:.0f}" for v in Y_TICKS])
        ax.set_xlim(0, 3)
        ax.set_ylim(0, 3)
        ax.set_aspect("equal")
        ax.set_xlabel("Daily minimum BG (mg/dL)")
        ax.set_ylabel("Daily maximum BG (mg/dL)")
    fig.suptitle(title)
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
