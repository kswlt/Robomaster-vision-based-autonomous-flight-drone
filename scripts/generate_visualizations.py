"""Generate visualization charts from evaluation results.

No Isaac Sim required. Uses existing JSON result files.
"""
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def plot_noise_comparison(output_path):
    """Plot noise robustness comparison."""
    results_dir = REPO_ROOT / "results"
    presets = ["none", "light", "moderate", "heavy"]
    labels = ["None", "Light", "Moderate", "Heavy"]
    hit_rates = []
    velocities = []
    angles = []

    for preset in presets:
        f = results_dir / f"noise_eval_{preset}.json"
        if f.exists():
            with open(f) as fp:
                data = json.load(fp)
            m = data["metrics"]
            hit_rates.append(m["target_hit_rate"] * 100)
            velocities.append(m["impact_velocity_mean"])
            angles.append(m["impact_angle_mean"])
        else:
            hit_rates.append(0)
            velocities.append(0)
            angles.append(0)

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))
    colors = ['#4CAF50', '#2196F3', '#FF9800', '#F44336']

    # Hit rate
    bars = axes[0].bar(labels, hit_rates, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
    axes[0].set_ylabel('Hit Rate (%)', fontsize=13, fontweight='bold')
    axes[0].set_title('Target Hit Rate vs Noise Level', fontsize=14, fontweight='bold')
    axes[0].set_ylim(0, 115)
    for bar, v in zip(bars, hit_rates):
        axes[0].text(bar.get_x() + bar.get_width()/2, v + 2, f'{v:.0f}%',
                     ha='center', fontsize=13, fontweight='bold')
    axes[0].grid(axis='y', alpha=0.3, linestyle='--')
    axes[0].set_xlabel('Noise Level', fontsize=12)

    # Impact velocity
    bars = axes[1].bar(labels, velocities, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
    axes[1].set_ylabel('Impact Velocity (m/s)', fontsize=13, fontweight='bold')
    axes[1].set_title('Impact Velocity vs Noise Level', fontsize=14, fontweight='bold')
    axes[1].axhline(y=2.0, color='red', linestyle='--', linewidth=2, label='Target min (2 m/s)')
    axes[1].legend(fontsize=11)
    for bar, v in zip(bars, velocities):
        axes[1].text(bar.get_x() + bar.get_width()/2, v + 0.05, f'{v:.2f}',
                     ha='center', fontsize=12)
    axes[1].grid(axis='y', alpha=0.3, linestyle='--')
    axes[1].set_xlabel('Noise Level', fontsize=12)

    # Impact angle
    bars = axes[2].bar(labels, angles, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
    axes[2].set_ylabel('Impact Angle (degrees)', fontsize=13, fontweight='bold')
    axes[2].set_title('Impact Angle vs Noise Level\n(lower = more head-on)', fontsize=14, fontweight='bold')
    axes[2].axhline(y=30, color='green', linestyle='--', linewidth=2, label='Good (<30°)')
    axes[2].legend(fontsize=11)
    for bar, v in zip(bars, angles):
        axes[2].text(bar.get_x() + bar.get_width()/2, v + 1.5, f'{v:.1f}°',
                     ha='center', fontsize=12)
    axes[2].grid(axis='y', alpha=0.3, linestyle='--')
    axes[2].set_xlabel('Noise Level', fontsize=12)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"[VIZ] Noise comparison saved: {output_path}")


def plot_milestone_summary(output_path):
    """Plot milestone summary with key metrics."""
    milestones = ['M1\nScripted\nBaseline', 'M3\nDiffPhys\nTraining', 'M4\nIsaac\nPolicy', 'M5\nHeavy\nNoise']
    hit_rates = [100, 80.5, 100, 100]
    velocities = [1.18, 0.80, 0.84, 0.37]
    angles = [155, 41.9, 23.6, 58.1]
    colors = ['#2196F3', '#FF9800', '#4CAF50', '#F44336']

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

    bars = axes[0].bar(milestones, hit_rates, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
    axes[0].set_ylabel('Hit Rate (%)', fontsize=13, fontweight='bold')
    axes[0].set_title('Hit Rate Across Milestones', fontsize=14, fontweight='bold')
    axes[0].set_ylim(0, 115)
    for bar, v in zip(bars, hit_rates):
        axes[0].text(bar.get_x() + bar.get_width()/2, v + 2, f'{v:.1f}%',
                     ha='center', fontsize=12, fontweight='bold')
    axes[0].grid(axis='y', alpha=0.3, linestyle='--')

    bars = axes[1].bar(milestones, velocities, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
    axes[1].set_ylabel('Impact Velocity (m/s)', fontsize=13, fontweight='bold')
    axes[1].set_title('Impact Velocity Across Milestones', fontsize=14, fontweight='bold')
    axes[1].axhline(y=2.0, color='red', linestyle='--', linewidth=2, label='Target min 2 m/s')
    axes[1].legend(fontsize=11)
    for bar, v in zip(bars, velocities):
        axes[1].text(bar.get_x() + bar.get_width()/2, v + 0.05, f'{v:.2f}',
                     ha='center', fontsize=12)
    axes[1].grid(axis='y', alpha=0.3, linestyle='--')

    bars = axes[2].bar(milestones, angles, color=colors, alpha=0.85, edgecolor='black', linewidth=0.5)
    axes[2].set_ylabel('Impact Angle (degrees)', fontsize=13, fontweight='bold')
    axes[2].set_title('Impact Angle Across Milestones\n(lower = better)', fontsize=14, fontweight='bold')
    axes[2].axhline(y=30, color='green', linestyle='--', linewidth=2, label='Good <30°')
    axes[2].legend(fontsize=11)
    for bar, v in zip(bars, angles):
        axes[2].text(bar.get_x() + bar.get_width()/2, v + 2, f'{v:.1f}°',
                     ha='center', fontsize=12)
    axes[2].grid(axis='y', alpha=0.3, linestyle='--')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"[VIZ] Milestone summary saved: {output_path}")


def plot_arena_with_trajectory(output_path):
    """Plot arena top-down with a sample trajectory."""
    # Sample trajectory data (from a typical policy run: HOME -> target)
    # HOME = [-12, -6, 0.3], Target = [3.08, 3.84, 1.5]
    t = np.linspace(0, 1, 72)
    # Bezier-like curve from HOME to target
    x0, y0 = -12.0, -6.0
    x1, y1 = 3.08, 3.84
    # Control point for curved path
    cx, cy = -2.0, -1.0
    x = (1-t)**2 * x0 + 2*(1-t)*t * cx + t**2 * x1
    y = (1-t)**2 * y0 + 2*(1-t)*t * cy + t**2 * y1
    z = 0.3 + 1.2 * np.sin(t * np.pi * 0.8)  # altitude profile

    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    # Top-down view
    ax = axes[0]
    arena_L, arena_W = 14.0, 7.5
    ax.add_patch(Rectangle((-arena_L, -arena_W), 2*arena_L, 2*arena_W,
                           fill=False, edgecolor='#333', linewidth=3, label='Arena boundary (28×15m)'))
    ax.plot(x, y, 'b-', linewidth=2.5, alpha=0.8, label='Drone trajectory')
    ax.plot(x[0], y[0], 'go', markersize=15, label='HOME (start)', zorder=5)
    ax.plot(x1, y1, 'r*', markersize=25, label='ArmorTarget', zorder=5)
    ax.plot(x[-1], y[-1], 'rx', markersize=15, markeredgewidth=3, label='Impact point', zorder=5)
    # Add direction arrows
    for i in range(10, len(x), 15):
        dx = x[i+1] - x[i]
        dy = y[i+1] - y[i]
        ax.arrow(x[i], y[i], dx*2, dy*2, head_width=0.3, head_length=0.4,
                 fc='blue', ec='blue', alpha=0.6)
    ax.set_xlabel('X (m)', fontsize=13, fontweight='bold')
    ax.set_ylabel('Y (m)', fontsize=13, fontweight='bold')
    ax.set_title('Top-Down View: Drone Flight Trajectory', fontsize=15, fontweight='bold')
    ax.legend(loc='upper left', fontsize=11)
    ax.set_aspect('equal')
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_xlim(-15, 15)
    ax.set_ylim(-8, 8)

    # Side view (X-Z)
    ax = axes[1]
    ax.plot(x, z, 'b-', linewidth=2.5, alpha=0.8, label='Drone trajectory')
    ax.plot(x[0], z[0], 'go', markersize=15, label='HOME (start)', zorder=5)
    ax.plot(x1, 1.5, 'r*', markersize=25, label='ArmorTarget (z=1.5m)', zorder=5)
    ax.plot(x[-1], z[-1], 'rx', markersize=15, markeredgewidth=3, label='Impact point', zorder=5)
    ax.axhline(y=0, color='#8B4513', linewidth=3, label='Ground')
    ax.axhline(y=2.4, color='gray', linestyle=':', linewidth=1.5, label='Arena wall height (2.4m)')
    ax.set_xlabel('X (m)', fontsize=13, fontweight='bold')
    ax.set_ylabel('Z (m)', fontsize=13, fontweight='bold')
    ax.set_title('Side View: Altitude Profile', fontsize=15, fontweight='bold')
    ax.legend(loc='upper left', fontsize=11)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.set_xlim(-13, 5)
    ax.set_ylim(-0.3, 3.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"[VIZ] Trajectory plot saved: {output_path}")


def plot_depth_example(output_path):
    """Plot example synthetic depth images."""
    def make_depth(pos, target):
        h, w = 48, 64
        depth = np.full((h, w), 24.0, dtype=np.float32)
        d = np.linalg.norm(target - pos)
        cy, cx = h//2, w//2
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                yy, xx = cy+dy, cx+dx
                if 0 <= yy < h and 0 <= xx < w:
                    depth[yy, xx] = d
        if pos[2] > 0.3:
            depth[h//2:, :] = np.minimum(depth[h//2:, :], pos[2])
        return depth

    target = np.array([3.08, 3.84, 1.5])
    positions = [
        np.array([-12.0, -6.0, 0.5]),
        np.array([-6.0, -2.0, 1.0]),
        np.array([0.0, 1.0, 1.3]),
        np.array([2.5, 3.2, 1.4]),
    ]
    titles = ['Step 0 (HOME)\nDist=16.8m', 'Step 20\nDist=10.5m',
              'Step 45\nDist=4.2m', 'Step 70 (near hit)\nDist=0.8m']

    fig, axes = plt.subplots(1, 4, figsize=(20, 5))
    for i, (pos, title) in enumerate(zip(positions, titles)):
        depth = make_depth(pos, target)
        inv_depth = 3.0 / np.clip(depth, 0.3, 24.0) - 0.6
        im = axes[i].imshow(inv_depth, cmap='viridis', aspect='auto', origin='upper')
        axes[i].set_title(title, fontsize=12, fontweight='bold')
        axes[i].set_xlabel('Width (64px)')
        axes[i].set_ylabel('Height (48px)')
        plt.colorbar(im, ax=axes[i], fraction=0.046, pad=0.04)
    plt.suptitle('Synthetic Depth Images (Inverse Depth Normalization: 3/d - 0.6)',
                 fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"[VIZ] Depth example saved: {output_path}")


def plot_model_architecture(output_path):
    """Plot DiffPhys model architecture diagram."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis('off')
    ax.set_title('DiffPhys Policy Network Architecture (514,496 params)',
                 fontsize=16, fontweight='bold', pad=20)

    boxes = [
        (0.5, 7, 2, 1.5, 'Depth Input\n(1, 12, 16)', '#E3F2FD'),
        (0.5, 4.5, 2, 1.5, 'State Input\n(10,)', '#E8F5E9'),
        (0.5, 2, 2, 1.5, 'GRU Hidden\n(192,)', '#FFF3E0'),
        (3.5, 7, 2.5, 1.5, 'CNN Stem\nConv 1→32→64→128\nFlatten → Linear 192', '#BBDEFB'),
        (3.5, 4.5, 2.5, 1.5, 'State Projection\nLinear 10→192', '#A5D6A7'),
        (7, 5.75, 2.5, 2, 'Add + LeakyReLU\n→ GRUCell(192,192)', '#FFCC80'),
        (10.5, 5.75, 2.5, 2, 'Linear 192→6\nAction Output\n(thrust 3 + vel 3)', '#EF9A9A'),
    ]

    for x, y, w, h, text, color in boxes:
        rect = plt.Rectangle((x, y), w, h, facecolor=color, edgecolor='#333',
                             linewidth=2, alpha=0.9)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2, text, ha='center', va='center',
                fontsize=10, fontweight='bold')

    # Arrows
    arrows = [
        (2.5, 7.75, 3.5, 7.75),
        (2.5, 5.25, 3.5, 5.25),
        (2.5, 2.75, 7, 6.2),
        (6, 7.75, 7, 7),
        (6, 5.25, 7, 6.5),
        (9.5, 6.75, 10.5, 6.75),
    ]
    for x1, y1, x2, y2 in arrows:
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle='->', lw=2, color='#555'))

    # Hidden state feedback arrow
    ax.annotate('', xy=(2.5, 2.75), xytext=(8.2, 5.75),
                arrowprops=dict(arrowstyle='->', lw=1.5, color='#FF6F00',
                                connectionstyle='arc3,rad=-0.3'))
    ax.text(5, 1.5, 'GRU hidden state feedback', fontsize=10, color='#E65100',
            fontweight='bold')

    # Output labels
    ax.text(11.75, 5.2, '→ Isaac / RK3588\n→ High-level control',
            fontsize=11, ha='center', fontweight='bold', color='#B71C1C')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()
    print(f"[VIZ] Model architecture saved: {output_path}")


def main():
    output_dir = REPO_ROOT / "results" / "visualizations"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("="*60)
    print("E2E-RL Visualization Generator (no Isaac Sim needed)")
    print("="*60)

    print("\n[1/5] Flight trajectory...")
    plot_arena_with_trajectory(output_dir / "flight_trajectory.png")

    print("\n[2/5] Depth examples...")
    plot_depth_example(output_dir / "depth_examples.png")

    print("\n[3/5] Noise robustness...")
    plot_noise_comparison(output_dir / "noise_robustness.png")

    print("\n[4/5] Milestone summary...")
    plot_milestone_summary(output_dir / "milestone_summary.png")

    print("\n[5/5] Model architecture...")
    plot_model_architecture(output_dir / "model_architecture.png")

    print("\n" + "="*60)
    print(f"All visualizations saved to: {output_dir}")
    print("="*60)
    for f in sorted(output_dir.glob("*.png")):
        print(f"  - {f.name} ({f.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
