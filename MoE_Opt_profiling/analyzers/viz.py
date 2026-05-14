from __future__ import annotations

import os
import statistics
from typing import Any


def try_plot_operator_duration_scatter(
    xs: list[int],
    ys: list[float],
    highlight: list[bool],
    out_path: str,
    *,
    title: str,
    subtitle: str = "",
) -> bool:
    """Scatter: y = Task Duration (us), x = chronological index after sorting by start time."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    if not xs or not ys or len(xs) != len(ys) or len(highlight) != len(ys):
        return False

    fig, ax = plt.subplots(figsize=(10, 4.2))
    xn, yn = [], []
    xh, yh = [], []
    for i, y, h in zip(xs, ys, highlight):
        if h:
            xh.append(i)
            yh.append(y)
        else:
            xn.append(i)
            yn.append(y)
    if xn:
        ax.scatter(xn, yn, s=12, alpha=0.35, c="#2a6ebd", edgecolors="none", label="samples")
    if xh:
        ax.scatter(
            xh,
            yh,
            s=36,
            c="#e65100",
            marker="x",
            linewidths=1.2,
            label="largest durations (auto-trim policy)",
            zorder=5,
        )

    mean_y = float(statistics.mean(ys))
    ax.axhline(
        mean_y,
        color="#1b5e20",
        linestyle="--",
        linewidth=1.5,
        zorder=3,
        label=f"mean (all) = {mean_y:.2f} us",
    )
    xmax = max(xs) if xs else 0
    ax.annotate(
        f"mean={mean_y:.2f}",
        xy=(xmax, mean_y),
        xytext=(8, 0),
        textcoords="offset points",
        va="center",
        ha="left",
        fontsize=9,
        color="#1b5e20",
        fontweight="bold",
    )

    ax.set_xlabel("Index (chronological: Task Start Time asc.; missing time last)")
    ax.set_ylabel("Task Duration (us)")
    ax.set_title(title)
    if subtitle:
        ax.text(0.01, 0.98, subtitle, transform=ax.transAxes, fontsize=8, va="top", color="#444")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return True


def try_plot_compare_delta_bar(
    compare_rows: list[dict[str, Any]],
    out_path: str,
    *,
    top_n: int = 20,
    value_key: str = "delta_task_duration_us_sum",
) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False

    head = compare_rows[:top_n]
    labels = [str(r.get("group_key"))[:48] for r in head]
    values = [float(r.get(value_key) or 0.0) for r in head]
    colors = ["#2e7d32" if v <= 0 else "#c62828" for v in values]

    fig, ax = plt.subplots(figsize=(10, max(4, 0.35 * len(head))))
    ax.barh(range(len(labels)), values, color=colors)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(0.0, color="#666", linewidth=0.8)
    ax.set_xlabel("Δ sum(Task Duration) (us), candidate − baseline")
    ax.set_title("Largest absolute changes by OP Type")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return True
