"""
FEM Screenshot Automation — pyNastran + Matplotlib Backend.

Renders FEM mesh, mode shapes, boundary conditions, CBUSH bolt locations,
and PSD frequency response plots using pure Python (no Femap/Patran required).

CBEAM elements are rendered as thick solid bars for visual clarity.
CBUSH bolt springs are shown as distinct markers with spring symbols.

Usage:
    python pipeline/fem_screenshots.py --run-folder <path> [--dat <path>]

Requires:
    - pyNastran, matplotlib, numpy, Pillow
"""

import sys
import os
import argparse
import numpy as np
import glob as globmod

import matplotlib
matplotlib.use('Agg')  # Headless backend — no GUI needed
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, Polygon
from matplotlib.collections import PatchCollection
import matplotlib.colors as mcolors
import matplotlib.patheffects as pe


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DPI = 200
FIG_SIZE = (10, 14)           # Tall figure for vertical beam
FIG_SIZE_WIDE = (14, 8)       # Wide figure for charts
BEAM_HALF_WIDTH = 18          # Half-width of beam rectangle (visual units)
CBUSH_MARKER_SIZE = 14        # Bolt marker radius
COLORMAP = 'coolwarm'

CAPTURE_LIST = [
    ("mesh_overview",        "FEM mesh with element coloring"),
    ("boundary_conditions",  "SPC boundary conditions highlighted"),
    ("mode_shape_01",        "First mode shape"),
    ("mode_shape_02",        "Second mode shape"),
    ("mode_shape_03",        "Third mode shape"),
    ("cbush_locations",      "CBUSH bolt element locations"),
]

# Professional color palette
COLOR_BEAM      = '#2563EB'   # Blue for CBEAM
COLOR_BEAM_FILL = '#DBEAFE'   # Light blue beam fill
COLOR_CBUSH     = '#DC2626'   # Red for CBUSH bolts
COLOR_SPC       = '#16A34A'   # Green for SPC constraints
COLOR_NODE      = '#374151'   # Dark gray
COLOR_DEFORMED  = '#7C3AED'   # Purple for deformed shape
COLOR_UNDEF     = '#E5E7EB'   # Light gray for undeformed ghost
COLOR_BG        = '#FAFAFA'   # Subtle background


# ---------------------------------------------------------------------------
# Data loading (unchanged)
# ---------------------------------------------------------------------------
def load_bdf(dat_path):
    """Load BDF/DAT model and return geometry dict."""
    import logging
    logging.disable(logging.DEBUG)
    from pyNastran.bdf.bdf import BDF

    bdf = BDF(log=None)
    bdf.read_bdf(dat_path)

    nodes = {}
    for nid in bdf.nodes:
        nodes[nid] = bdf.nodes[nid].xyz.copy()

    cbeam_elems = []
    cbush_elems = []
    for eid in sorted(bdf.elements):
        e = bdf.elements[eid]
        if e.type == 'CBEAM':
            cbeam_elems.append((eid, e.node_ids))
        elif e.type == 'CBUSH':
            cbush_elems.append((eid, e.node_ids))

    spc_nodes = set()
    for spc_id in bdf.spcs:
        for spc in bdf.spcs[spc_id]:
            if hasattr(spc, 'node_ids'):
                for nid in spc.node_ids:
                    spc_nodes.add(nid)

    return {
        'nodes': nodes,
        'cbeam': cbeam_elems,
        'cbush': cbush_elems,
        'spc_nodes': spc_nodes,
        'bdf': bdf,
    }


def load_op2_modes(op2_path):
    """Load eigenvalues and eigenvectors from OP2."""
    import logging
    logging.disable(logging.DEBUG)
    from pyNastran.op2.op2 import OP2

    op2 = OP2(log=None)
    op2.read_op2(op2_path)

    result = {'modes': [], 'freqs': [], 'eigenvectors': None, 'node_ids': []}

    if op2.eigenvectors:
        key = list(op2.eigenvectors.keys())[0]
        eig = op2.eigenvectors[key]
        result['modes'] = list(eig.modes)
        result['freqs'] = list(eig.mode_cycles)
        result['eigenvectors'] = eig.data
        result['node_ids'] = eig.node_gridtype[:, 0].tolist()

    return result


def load_op2_psd(op2_path):
    """Load PSD displacement data from randombeamx OP2."""
    import logging
    logging.disable(logging.DEBUG)
    from pyNastran.op2.op2 import OP2

    op2 = OP2(log=None)
    try:
        op2.read_op2(op2_path)
    except Exception:
        return None

    try:
        psd_disp = op2.psd.displacements
        if psd_disp:
            key = list(psd_disp.keys())[0]
            psd_obj = psd_disp[key]
            return {
                'data': psd_obj.data,
                'node_ids': psd_obj.node_gridtype[:, 0].tolist(),
                'freqs': psd_obj.dts if hasattr(psd_obj, 'dts') else None,
            }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 2D Drawing helpers for vertical beam
# ---------------------------------------------------------------------------
def get_beam_segments(nodes, cbeam_elems):
    """Get ordered beam segment coordinates. Returns list of (z1, z2, y1, y2, nid1, nid2)."""
    segments = []
    for eid, nids in cbeam_elems:
        n1 = nodes[nids[0]]
        n2 = nodes[nids[1]]
        segments.append((n1[2], n2[2], n1[1], n2[1], nids[0], nids[1]))
    segments.sort(key=lambda s: min(s[0], s[1]))
    return segments


def draw_thick_beam(ax, z1, z2, y_center=0, half_w=BEAM_HALF_WIDTH,
                    facecolor=COLOR_BEAM_FILL, edgecolor=COLOR_BEAM, lw=2, alpha=1.0):
    """Draw a beam segment as a thick rectangle."""
    zmin, zmax = min(z1, z2), max(z1, z2)
    rect = Rectangle((y_center - half_w, zmin), half_w * 2, zmax - zmin,
                      facecolor=facecolor, edgecolor=edgecolor,
                      linewidth=lw, alpha=alpha, zorder=2)
    ax.add_patch(rect)
    return rect


def draw_thick_beam_deformed(ax, y1, z1, y2, z2, half_w=BEAM_HALF_WIDTH,
                              facecolor=COLOR_BEAM_FILL, edgecolor=COLOR_BEAM,
                              lw=2, alpha=1.0):
    """Draw a deformed beam segment as a quadrilateral."""
    # Four corners of the deformed beam cross-section
    corners = np.array([
        [y1 - half_w, z1],
        [y1 + half_w, z1],
        [y2 + half_w, z2],
        [y2 - half_w, z2],
    ])
    poly = Polygon(corners, closed=True, facecolor=facecolor,
                   edgecolor=edgecolor, linewidth=lw, alpha=alpha, zorder=2)
    ax.add_patch(poly)
    return poly


def draw_spring_symbol(ax, y, z, size=12, color=COLOR_CBUSH):
    """Draw a small spring/zigzag symbol for CBUSH."""
    # Diamond marker with inner cross
    ax.plot(y, z, 'D', color=color, markersize=size, markeredgecolor='black',
            markeredgewidth=1.0, zorder=5)
    # Small inner dot
    ax.plot(y, z, '.', color='white', markersize=size * 0.35, zorder=6)


def draw_spc_symbol(ax, y, z, size=30, color=COLOR_SPC):
    """Draw ground/fixed support symbol (triangle + hatching)."""
    # Triangle pointing down
    tri_h = size
    tri_w = size * 1.2
    triangle = Polygon([
        [y, z],
        [y - tri_w/2, z - tri_h],
        [y + tri_w/2, z - tri_h],
    ], closed=True, facecolor=color, edgecolor='black', linewidth=1.5,
       alpha=0.7, zorder=5)
    ax.add_patch(triangle)

    # Hatching lines below triangle
    for i in range(4):
        offset = -tri_h - 5 - i * 6
        ax.plot([y - tri_w/2 + i*4, y - tri_w/2 + i*4 - 8],
                [z + offset, z + offset - 8],
                color='black', linewidth=1, alpha=0.5, zorder=4)


def setup_2d_axes(fig, title, subtitle=None):
    """Create clean 2D axes for beam elevation view."""
    ax = fig.add_subplot(111)
    ax.set_facecolor(COLOR_BG)
    ax.set_xlabel('Lateral Position (Y)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Station Height (Z)', fontsize=11, fontweight='bold')

    full_title = title
    if subtitle:
        full_title += f'\n{subtitle}'
    ax.set_title(full_title, fontsize=14, fontweight='bold', pad=15)

    ax.grid(True, alpha=0.2, linestyle='--')
    ax.set_aspect('equal')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    return ax


# ---------------------------------------------------------------------------
# Image capture functions
# ---------------------------------------------------------------------------
def capture_mesh_overview(geom, run_folder):
    """Render 2D elevation view of FEM mesh with thick beam and bolt markers."""
    fig = plt.figure(figsize=FIG_SIZE, facecolor='white')
    ax = setup_2d_axes(fig, 'FEM Mesh Overview',
                       f'{len(geom["cbeam"])} CBEAM + {len(geom["cbush"])} CBUSH elements  |  {len(geom["nodes"])} nodes')

    nodes = geom['nodes']
    segments = get_beam_segments(nodes, geom['cbeam'])

    # Draw beam segments as thick bars
    for z1, z2, y1, y2, nid1, nid2 in segments:
        draw_thick_beam(ax, z1, z2, y_center=(y1 + y2) / 2)

    # Draw CBUSH bolt markers
    for eid, nids in geom['cbush']:
        mid = (nodes[nids[0]] + nodes[nids[1]]) / 2
        draw_spring_symbol(ax, mid[1], mid[2], size=CBUSH_MARKER_SIZE)

    # Draw nodes
    for nid in sorted(nodes):
        n = nodes[nid]
        ax.plot(n[1], n[2], 'o', color=COLOR_NODE, markersize=4,
                markeredgecolor='black', markeredgewidth=0.3, zorder=4, alpha=0.6)

    # Node labels for beam nodes (every other to avoid crowding)
    beam_nids = sorted([nid for nid in nodes if nid >= 100])
    for i, nid in enumerate(beam_nids):
        if i % 2 == 0:  # Label every other node
            n = nodes[nid]
            ax.annotate(f'{nid}', (n[1] + BEAM_HALF_WIDTH + 8, n[2]),
                        fontsize=6, color='gray', va='center')

    # Legend entries (invisible artists)
    ax.plot([], [], 's', color=COLOR_BEAM_FILL, markeredgecolor=COLOR_BEAM,
            markersize=12, label='CBEAM (beam)')
    ax.plot([], [], 'D', color=COLOR_CBUSH, markeredgecolor='black',
            markersize=8, label='CBUSH (bolt spring)')
    ax.legend(loc='upper right', fontsize=10, framealpha=0.9)

    # Axis limits
    all_z = [nodes[nid][2] for nid in nodes]
    ax.set_xlim(-150, 150)
    ax.set_ylim(min(all_z) - 80, max(all_z) + 80)

    out = os.path.join(run_folder, 'mesh_overview.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out


def capture_boundary_conditions(geom, run_folder):
    """Render mesh with SPC boundary conditions highlighted."""
    fig = plt.figure(figsize=FIG_SIZE, facecolor='white')

    spc_desc = ', '.join(str(n) for n in sorted(geom['spc_nodes']))
    ax = setup_2d_axes(fig, 'Boundary Conditions',
                       f'SPC (123456 fixed): Node(s) {spc_desc}')

    nodes = geom['nodes']
    segments = get_beam_segments(nodes, geom['cbeam'])

    # Draw beam (faded)
    for z1, z2, y1, y2, nid1, nid2 in segments:
        draw_thick_beam(ax, z1, z2, y_center=(y1 + y2) / 2, alpha=0.5)

    # Draw CBUSH markers (small, faded)
    for eid, nids in geom['cbush']:
        mid = (nodes[nids[0]] + nodes[nids[1]]) / 2
        draw_spring_symbol(ax, mid[1], mid[2], size=8, color='#FCA5A5')

    # Highlight SPC nodes with ground symbol
    for nid in geom['spc_nodes']:
        n = nodes[nid]
        draw_spc_symbol(ax, n[1], n[2], size=35, color=COLOR_SPC)

    # Draw DOF arrows at SPC node
    for nid in geom['spc_nodes']:
        n = nodes[nid]
        arrow_len = 50
        # Translation constraints
        for dy, dz, label in [(arrow_len, 0, 'Ty'), (0, arrow_len, 'Tz'),
                               (-arrow_len, 0, 'Ty'), (0, -arrow_len, 'Tz')]:
            ax.annotate('', xy=(n[1] + dy*0.7, n[2] + dz*0.7),
                        xytext=(n[1], n[2]),
                        arrowprops=dict(arrowstyle='-|>', color=COLOR_SPC,
                                        lw=1.5, mutation_scale=10),
                        zorder=7)
        # Label
        ax.text(n[1] + 70, n[2], 'FIXED\n(123456)',
                fontsize=9, fontweight='bold', color=COLOR_SPC,
                ha='left', va='center',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                          edgecolor=COLOR_SPC, alpha=0.9))

    # Free tip label
    tip_z = max(nodes[nid][2] for nid in nodes)
    ax.text(70, tip_z, 'FREE TIP',
            fontsize=9, fontweight='bold', color='#6B7280',
            ha='left', va='center',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                      edgecolor='#D1D5DB', alpha=0.9))

    # Legend
    ax.plot([], [], '^', color=COLOR_SPC, markersize=10, label='SPC (fixed)')
    ax.plot([], [], 's', color=COLOR_BEAM_FILL, markeredgecolor=COLOR_BEAM,
            markersize=10, label='CBEAM', alpha=0.5)
    ax.legend(loc='upper right', fontsize=10, framealpha=0.9)

    all_z = [nodes[nid][2] for nid in nodes]
    ax.set_xlim(-150, 200)
    ax.set_ylim(min(all_z) - 100, max(all_z) + 80)

    out = os.path.join(run_folder, 'boundary_conditions.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out


def capture_mode_shape(geom, mode_data, mode_num, freq_hz, run_folder):
    """Render deformed mode shape with thick beam and displacement colormap."""
    fig = plt.figure(figsize=(12, 14), facecolor='white')
    ax = setup_2d_axes(fig, f'Mode {mode_num} — {freq_hz:.2f} Hz',
                       'Deformed shape (scaled) with displacement magnitude colormap')

    nodes = geom['nodes']
    mode_idx = mode_num - 1

    eigvec = mode_data['eigenvectors'][mode_idx]  # (nnodes, 6)
    eig_nids = mode_data['node_ids']

    # Build displacement dict
    disp = {}
    disp_mag = {}
    for i, nid in enumerate(eig_nids):
        d = eigvec[i, :3]
        disp[nid] = d
        disp_mag[nid] = np.linalg.norm(d)

    # Auto-scale: max displacement = 20% of model height
    all_z = [nodes[nid][2] for nid in nodes]
    model_height = max(all_z) - min(all_z)
    max_disp = max(disp_mag.values()) if disp_mag else 1.0
    scale = (model_height * 0.20) / max_disp if max_disp > 0 else 1.0

    # Deformed positions (use Y for lateral, Z for vertical)
    def_nodes = {}
    for nid in nodes:
        if nid in disp:
            def_nodes[nid] = nodes[nid] + disp[nid] * scale
        else:
            def_nodes[nid] = nodes[nid].copy()

    # Colormap setup
    all_mags = np.array([disp_mag.get(nid, 0) for nid in sorted(nodes)])
    vmax = all_mags.max() if all_mags.max() > 0 else 1.0
    norm = mcolors.Normalize(vmin=0, vmax=vmax)
    cmap = plt.colormaps[COLORMAP]

    # Draw undeformed ghost beam
    segments = get_beam_segments(nodes, geom['cbeam'])
    for z1, z2, y1, y2, nid1, nid2 in segments:
        draw_thick_beam(ax, z1, z2, y_center=(y1 + y2) / 2,
                        facecolor=COLOR_UNDEF, edgecolor='#D1D5DB',
                        lw=1, alpha=0.4)

    # Draw deformed beam segments with color
    for eid, nids in geom['cbeam']:
        n1_def = def_nodes[nids[0]]
        n2_def = def_nodes[nids[1]]
        avg_mag = (disp_mag.get(nids[0], 0) + disp_mag.get(nids[1], 0)) / 2
        color = cmap(norm(avg_mag))
        draw_thick_beam_deformed(ax, n1_def[1], n1_def[2], n2_def[1], n2_def[2],
                                  half_w=BEAM_HALF_WIDTH,
                                  facecolor=color, edgecolor=color, lw=1.5, alpha=0.85)
        # Darker edge outline
        draw_thick_beam_deformed(ax, n1_def[1], n1_def[2], n2_def[1], n2_def[2],
                                  half_w=BEAM_HALF_WIDTH,
                                  facecolor='none', edgecolor='black', lw=0.5, alpha=0.3)

    # Draw CBUSH markers on deformed position
    for eid, nids in geom['cbush']:
        n1_def = def_nodes.get(nids[0], nodes[nids[0]])
        n2_def = def_nodes.get(nids[1], nodes[nids[1]])
        mid = (n1_def + n2_def) / 2
        avg_mag = (disp_mag.get(nids[0], 0) + disp_mag.get(nids[1], 0)) / 2
        c = cmap(norm(avg_mag))
        ax.plot(mid[1], mid[2], 'D', color=c, markersize=10,
                markeredgecolor='black', markeredgewidth=0.8, zorder=5)

    # Deformed centerline (dashed)
    beam_node_order = []
    for eid, nids in sorted(geom['cbeam'], key=lambda x: min(nodes[x[1][0]][2], nodes[x[1][1]][2])):
        for nid in nids:
            if nid not in [n for n, _ in beam_node_order]:
                beam_node_order.append((nid, def_nodes.get(nid, nodes[nid])))
    beam_node_order.sort(key=lambda x: x[1][2])
    if beam_node_order:
        ys = [n[1] for _, n in beam_node_order]
        zs = [n[2] for _, n in beam_node_order]
        ax.plot(ys, zs, '--', color='black', linewidth=1, alpha=0.4, zorder=3,
                label='Deformed centerline')

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, shrink=0.5, pad=0.02, aspect=30,
                        label='Displacement Magnitude')
    cbar.ax.tick_params(labelsize=9)

    # Legend
    ax.fill_between([], [], [], color=COLOR_UNDEF, alpha=0.4, label='Undeformed')
    ax.fill_between([], [], [], color=cmap(0.7), alpha=0.85, label='Deformed')
    ax.legend(loc='upper right', fontsize=10, framealpha=0.9)

    # Axis limits with room for deformation
    max_y_disp = max(abs(def_nodes[nid][1]) for nid in def_nodes) + BEAM_HALF_WIDTH + 30
    ax.set_xlim(-max(max_y_disp, 100), max(max_y_disp, 100))
    ax.set_ylim(min(all_z) - 80, max(all_z) + 80)

    out = os.path.join(run_folder, f'mode_shape_{mode_num:02d}.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out


def capture_cbush_locations(geom, run_folder):
    """Render mesh highlighting CBUSH bolt locations with labels."""
    fig = plt.figure(figsize=FIG_SIZE, facecolor='white')
    ax = setup_2d_axes(fig, 'CBUSH Bolt Locations',
                       f'{len(geom["cbush"])} spring elements connecting beam to ground')

    nodes = geom['nodes']
    segments = get_beam_segments(nodes, geom['cbeam'])

    # Draw beam (faded)
    for z1, z2, y1, y2, nid1, nid2 in segments:
        draw_thick_beam(ax, z1, z2, y_center=(y1 + y2) / 2,
                        facecolor='#EFF6FF', edgecolor='#93C5FD', lw=1.5, alpha=0.7)

    # Draw ground side (thin bar to the left)
    ground_nids = sorted([nid for nid in nodes if nid <= 10], key=lambda n: nodes[n][2])
    if ground_nids:
        gz_min = nodes[ground_nids[0]][2]
        gz_max = nodes[ground_nids[-1]][2]
        # Ground bar
        ground_x = -60
        rect = Rectangle((ground_x - 8, gz_min - 10), 16, gz_max - gz_min + 20,
                          facecolor='#D1D5DB', edgecolor='#6B7280', linewidth=1.5,
                          alpha=0.6, zorder=1, hatch='///')
        ax.add_patch(rect)
        ax.text(ground_x, gz_max + 30, 'GROUND', fontsize=8, fontweight='bold',
                color='#6B7280', ha='center', va='bottom')

    # Draw CBUSH bolts with connecting lines to ground
    for eid, nids in geom['cbush']:
        n_ground = nodes[nids[0]]  # Ground node
        n_beam = nodes[nids[1]]    # Beam node
        mid_z = (n_ground[2] + n_beam[2]) / 2

        # Spring line from ground bar to beam
        ax.plot([ground_x + 8, -BEAM_HALF_WIDTH], [mid_z, mid_z],
                color=COLOR_CBUSH, linewidth=1.5, linestyle='-', alpha=0.6, zorder=3)

        # Zigzag spring symbol
        spring_y = np.linspace(ground_x + 8, -BEAM_HALF_WIDTH, 12)
        spring_z = mid_z + np.array([0, 4, -4, 4, -4, 4, -4, 4, -4, 4, -4, 0]) * 2.5
        ax.plot(spring_y, spring_z, color=COLOR_CBUSH, linewidth=1.2, alpha=0.8, zorder=3)

        # Large bolt marker on beam face
        ax.plot(-BEAM_HALF_WIDTH, mid_z, 'D', color=COLOR_CBUSH, markersize=CBUSH_MARKER_SIZE,
                markeredgecolor='black', markeredgewidth=1.0, zorder=5)

        # Label
        ax.text(BEAM_HALF_WIDTH + 10, mid_z, f'Bolt {eid}\n(z={mid_z:.0f})',
                fontsize=7, color=COLOR_CBUSH, fontweight='bold',
                ha='left', va='center',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                          edgecolor=COLOR_CBUSH, alpha=0.8, linewidth=0.5))

    # Legend
    ax.plot([], [], 'D', color=COLOR_CBUSH, markeredgecolor='black',
            markersize=10, label=f'CBUSH bolt ({len(geom["cbush"])} total)')
    ax.plot([], [], 's', color='#EFF6FF', markeredgecolor='#93C5FD',
            markersize=12, label='CBEAM (beam)')
    ax.fill_between([], [], color='#D1D5DB', alpha=0.6, label='Ground structure',
                    hatch='///')
    ax.legend(loc='upper right', fontsize=10, framealpha=0.9)

    all_z = [nodes[nid][2] for nid in nodes]
    ax.set_xlim(-120, 180)
    ax.set_ylim(min(all_z) - 80, max(all_z) + 80)

    out = os.path.join(run_folder, 'cbush_locations.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out


def capture_psd_plot(psd_data, run_folder):
    """Generate PSD frequency response plot from OP2 data."""
    if psd_data is None:
        return None

    fig, ax = plt.subplots(figsize=FIG_SIZE_WIDE, facecolor='white')
    ax.set_facecolor(COLOR_BG)
    ax.set_title('PSD Displacement Response — SOL 111 Random Analysis',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Frequency (Hz)', fontsize=11, fontweight='bold')
    ax.set_ylabel('PSD Displacement (unit²/Hz)', fontsize=11, fontweight='bold')

    data = psd_data['data']
    node_ids = psd_data['node_ids']
    freqs = psd_data['freqs']

    if freqs is None or data is None:
        plt.close(fig)
        return None

    freqs = np.array(freqs)

    # Find top 5 responding nodes
    total_psd = np.sum(np.abs(data[:, :, :3]), axis=(0, 2))
    top_nodes_idx = np.argsort(total_psd)[-5:]

    colors = ['#2563EB', '#DC2626', '#16A34A', '#F59E0B', '#7C3AED']
    dof_labels = ['Tx', 'Ty', 'Tz']

    for i, nidx in enumerate(reversed(top_nodes_idx)):
        nid = node_ids[nidx]
        dof_max = np.argmax(np.sum(np.abs(data[:, nidx, :3]), axis=0))
        psd_vals = np.abs(data[:, nidx, dof_max])
        if psd_vals.max() > 0:
            ax.semilogy(freqs, psd_vals, label=f'Node {nid} ({dof_labels[dof_max]})',
                        color=colors[i % len(colors)], linewidth=2, alpha=0.85)

    ax.grid(True, alpha=0.3, which='both', linestyle='--')
    ax.legend(fontsize=10, loc='upper right', framealpha=0.9)
    ax.set_xlim(freqs.min(), freqs.max())
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    out = os.path.join(run_folder, 'psd_response.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out


def capture_frequency_bar_chart(mode_data, run_folder):
    """Bar chart of natural frequencies."""
    if not mode_data['freqs']:
        return None

    fig, ax = plt.subplots(figsize=FIG_SIZE_WIDE, facecolor='white')
    ax.set_facecolor(COLOR_BG)
    modes = mode_data['modes']
    freqs = mode_data['freqs']

    bars = ax.bar(modes, freqs, color=COLOR_BEAM, edgecolor='black',
                  linewidth=0.5, alpha=0.85, width=0.7)

    for bar, freq in zip(bars, freqs):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(freqs)*0.02,
                f'{freq:.1f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    ax.set_xlabel('Mode Number', fontsize=12, fontweight='bold')
    ax.set_ylabel('Natural Frequency (Hz)', fontsize=12, fontweight='bold')
    ax.set_title('Natural Frequencies — SOL 103 Modal Analysis',
                 fontsize=14, fontweight='bold')
    ax.set_xticks(modes)
    ax.grid(True, axis='y', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    out = os.path.join(run_folder, 'frequency_bar_chart.png')
    fig.savefig(out, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# File finders
# ---------------------------------------------------------------------------
def find_files(run_folder, ext):
    """Find files by extension (case-insensitive)."""
    matches = globmod.glob(os.path.join(run_folder, f'*.{ext}')) + \
              globmod.glob(os.path.join(run_folder, f'*.{ext.upper()}'))
    seen = set()
    unique = []
    for path in sorted(matches):
        norm = os.path.normcase(os.path.normpath(path))
        if norm not in seen:
            seen.add(norm)
            unique.append(path)
    return unique


def find_dat_for_model(run_folder, dat_override=None):
    """Find the primary DAT file."""
    if dat_override and os.path.isfile(dat_override):
        return dat_override
    dat_files = find_files(run_folder, 'dat')
    for f in dat_files:
        if 'fixed_base_beam' in os.path.basename(f).lower():
            return f
    for f in dat_files:
        if 'random' not in os.path.basename(f).lower():
            return f
    return dat_files[0] if dat_files else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Capture FEM screenshots")
    parser.add_argument('--run-folder', required=True, help='Path to run folder')
    parser.add_argument('--dat', default=None, help='Optional DAT file path')
    args = parser.parse_args()

    run_folder = args.run_folder
    if not os.path.isdir(run_folder):
        print(f"ERROR: Run folder not found: {run_folder}")
        sys.exit(1)

    print("=" * 60)
    print("  FEM SCREENSHOT CAPTURE — pyNastran + Matplotlib")
    print("=" * 60)
    print(f"Run folder: {run_folder}")

    dat_path = find_dat_for_model(run_folder, args.dat)
    op2_files = find_files(run_folder, 'op2')

    if not dat_path:
        print("ERROR: No DAT file found")
        sys.exit(1)

    print(f"DAT file:  {os.path.basename(dat_path)}")
    print(f"OP2 files: {[os.path.basename(f) for f in op2_files]}")

    print("\nLoading FEM model...")
    geom = load_bdf(dat_path)
    print(f"  Nodes: {len(geom['nodes'])}, CBEAM: {len(geom['cbeam'])}, CBUSH: {len(geom['cbush'])}, SPC: {sorted(geom['spc_nodes'])}")

    mode_data = None
    for op2_path in op2_files:
        if 'fixed_base_beam' in os.path.basename(op2_path).lower():
            print(f"Loading modes from {os.path.basename(op2_path)}...")
            mode_data = load_op2_modes(op2_path)
            if mode_data['modes']:
                print(f"  {len(mode_data['modes'])} modes ({mode_data['freqs'][0]:.1f} – {mode_data['freqs'][-1]:.1f} Hz)")
            break

    psd_data = None
    for op2_path in op2_files:
        if 'randombeam' in os.path.basename(op2_path).lower():
            print(f"Loading PSD from {os.path.basename(op2_path)}...")
            psd_data = load_op2_psd(op2_path)
            if psd_data:
                print(f"  PSD shape: {psd_data['data'].shape}")
            break

    captured = []
    print("\n--- Capturing images ---")

    print("  [1/7] Mesh overview...")
    path = capture_mesh_overview(geom, run_folder)
    if path: captured.append(path); print(f"        -> {os.path.basename(path)}")

    print("  [2/7] Boundary conditions...")
    path = capture_boundary_conditions(geom, run_folder)
    if path: captured.append(path); print(f"        -> {os.path.basename(path)}")

    if mode_data and mode_data['modes']:
        for mn in [1, 2, 3]:
            if mn <= len(mode_data['modes']):
                freq = mode_data['freqs'][mn - 1]
                print(f"  [{mn + 2}/7] Mode shape {mn} ({freq:.2f} Hz)...")
                path = capture_mode_shape(geom, mode_data, mn, freq, run_folder)
                if path: captured.append(path); print(f"        -> {os.path.basename(path)}")
    else:
        print("  [3-5/7] SKIP — no modal data")

    print("  [6/7] CBUSH bolt locations...")
    path = capture_cbush_locations(geom, run_folder)
    if path: captured.append(path); print(f"        -> {os.path.basename(path)}")

    if mode_data and mode_data['freqs']:
        print("  [7/7] Frequency bar chart...")
        path = capture_frequency_bar_chart(mode_data, run_folder)
        if path: captured.append(path); print(f"        -> {os.path.basename(path)}")

    if psd_data:
        print("  [bonus] PSD response plot...")
        path = capture_psd_plot(psd_data, run_folder)
        if path: captured.append(path); print(f"        -> {os.path.basename(path)}")

    write_output(run_folder, captured)
    print(f"\nCaptured {len(captured)} images")
    print("=" * 60)
    return captured


def write_output(run_folder, captured):
    """Write captured image paths to manifest and GITHUB_OUTPUT."""
    manifest_path = os.path.join(run_folder, "captured_images.txt")
    with open(manifest_path, 'w') as f:
        for path in captured:
            f.write(f"{path}\n")

    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"IMAGE_COUNT={len(captured)}\n")
            f.write(f"IMAGES_MANIFEST={manifest_path}\n")
            f.write(f"HAS_IMAGES={'true' if captured else 'false'}\n")


if __name__ == '__main__':
    main()
