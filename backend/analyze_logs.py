import argparse
import json
import os
from pathlib import Path
from collections import Counter


def parse_args():
    p = argparse.ArgumentParser(description="Analyse Speed Limit Detection Logs")
    p.add_argument("--csv", default="logs/detections.csv")
    p.add_argument("--json", default="logs/detections.json")
    p.add_argument("--output-dir", default="output")
    return p.parse_args()


def load_json_log(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        print(f"[!] JSON log not found: {path}")
        return []
    with open(p) as f:
        return json.load(f)


def print_summary(records: list[dict]) -> None:
    if not records:
        print("No records found in log file.")
        return

    total = len(records)
    violations = [r for r in records if r.get("is_violation")]
    speeds = [r["speed_limit_kmh"] for r in records if r.get("speed_limit_kmh")]
    v_speeds = [r["vehicle_speed_kmh"] for r in records
                if r.get("vehicle_speed_kmh") is not None]

    print("\n" + "=" * 55)
    print("  DETECTION SESSION ANALYSIS")
    print("=" * 55)
    print(f"  Total logged events   : {total}")
    print(f"  Violation events      : {len(violations)}")
    print(f"  Violation rate        : {len(violations)/total*100:.1f}%")

    if speeds:
        freq = Counter(speeds)
        print(f"\n  Speed Limits Detected:")
        for spd, cnt in sorted(freq.items()):
            bar = "█" * (cnt * 30 // max(freq.values()))
            print(f"    {int(spd):>4} km/h  {bar} ({cnt})")

    if v_speeds:
        avg = sum(v_speeds) / len(v_speeds)
        print(f"\n  Vehicle Speed (simulated):")
        print(f"    Average  : {avg:.1f} km/h")
        print(f"    Maximum  : {max(v_speeds):.1f} km/h")
        print(f"    Minimum  : {min(v_speeds):.1f} km/h")

    if violations:
        excess = [r.get("vehicle_speed_kmh", 0) - r.get("speed_limit_kmh", 0)
                  for r in violations]
        print(f"\n  Violation Details:")
        print(f"    Avg excess speed : {sum(excess)/len(excess):.1f} km/h")
        print(f"    Max excess speed : {max(excess):.1f} km/h")

    if records:
        print(f"\n  Session period:")
        print(f"    Start : {records[0].get('timestamp', 'N/A')}")
        print(f"    End   : {records[-1].get('timestamp', 'N/A')}")
    print("=" * 55 + "\n")


def plot_charts(records: list[dict], output_dir: str) -> None:
    """Generate and save analysis charts (requires matplotlib)."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("[!] matplotlib not installed — skipping charts")
        return

    if not records:
        return

    os.makedirs(output_dir, exist_ok=True)

    # ── Chart 1: Speed Limit Distribution ─────────────────────────────────────
    speeds = [r["speed_limit_kmh"] for r in records if r.get("speed_limit_kmh")]
    if speeds:
        fig, ax = plt.subplots(figsize=(8, 4))
        freq = Counter(speeds)
        ax.bar([str(k) for k in sorted(freq)], [freq[k] for k in sorted(freq)],
               color="#e74c3c", edgecolor="black", linewidth=0.5)
        ax.set_title("Speed Limit Detection Frequency", fontsize=14, fontweight="bold")
        ax.set_xlabel("Speed Limit (km/h)")
        ax.set_ylabel("Number of Detections")
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        chart_path = Path(output_dir) / "speed_distribution.png"
        plt.savefig(chart_path, dpi=150)
        plt.close()
        print(f"  Chart saved: {chart_path}")

    # ── Chart 2: Violations Over Time ─────────────────────────────────────────
    violations = [r for r in records if r.get("is_violation")]
    if violations:
        fig, ax = plt.subplots(figsize=(10, 4))
        frames = [r["frame_id"] for r in violations]
        v_spds = [r.get("vehicle_speed_kmh", 0) for r in violations]
        limits = [r.get("speed_limit_kmh", 0) for r in violations]

        ax.plot(frames, v_spds, "r-o", markersize=4, label="Vehicle Speed", alpha=0.7)
        ax.plot(frames, limits, "b--", linewidth=2, label="Speed Limit")
        ax.fill_between(frames, limits, v_spds,
                        where=[vs > sl for vs, sl in zip(v_spds, limits)],
                        alpha=0.2, color="red", label="Excess Speed")
        ax.set_title("Speed Violations Over Time", fontsize=14, fontweight="bold")
        ax.set_xlabel("Frame Number")
        ax.set_ylabel("Speed (km/h)")
        ax.legend()
        ax.grid(alpha=0.3)
        plt.tight_layout()
        chart_path2 = Path(output_dir) / "violations_timeline.png"
        plt.savefig(chart_path2, dpi=150)
        plt.close()
        print(f"  Chart saved: {chart_path2}")


def main():
    args = parse_args()
    records = load_json_log(args.json)
    print_summary(records)
    plot_charts(records, args.output_dir)


if __name__ == "__main__":
    main()
