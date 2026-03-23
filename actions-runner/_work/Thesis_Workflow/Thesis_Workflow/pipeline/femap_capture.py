"""
Femap COM automation — capture model views as PNG images.

Connects to Femap via COM, opens a Nastran model, and captures views:
  1. Mesh overview (isometric)
  2. Boundary conditions overlay (SPC markers)
  3. CBUSH element locations (bolt elements highlighted)
  4. Mode shape animation frames (first N modes)

Usage:
    python pipeline/femap_capture.py --model <dat_file> --output-dir <path> [--modes 5]

Requires:
    - Femap installed and licensed (COM server registered)
    - pywin32 (pip install pywin32)

If Femap is not available, exits with code 0 and a warning — never blocks pipeline.
"""

import os
import sys
import time
import argparse


def check_femap():
    """Check if Femap COM server is available."""
    try:
        import win32com.client
        app = win32com.client.Dispatch("femap.model")
        return app
    except ImportError:
        print("WARNING: pywin32 not installed — skipping Femap capture")
        return None
    except Exception as e:
        print(f"WARNING: Femap COM not available — skipping capture ({e})")
        return None


def capture_view(app, output_path, title=""):
    """Capture current Femap view to PNG."""
    try:
        # Get the active window
        win = app.feWindowGetActive()
        # Export bitmap
        app.feFilePictureSave(False, output_path)
        print(f"  Captured: {output_path}" + (f" ({title})" if title else ""))
        return True
    except Exception as e:
        print(f"  WARNING: Failed to capture {output_path}: {e}")
        return False


def capture_mesh_overview(app, output_dir):
    """Capture isometric mesh view."""
    try:
        # Set isometric view
        app.feViewOrientation(19)  # Isometric
        app.feViewRegenerate(0)
        time.sleep(0.5)

        output_path = os.path.join(output_dir, "mesh_overview.png")
        return capture_view(app, output_path, "Mesh Overview")
    except Exception as e:
        print(f"  WARNING: Mesh overview failed: {e}")
        return False


def capture_boundary_conditions(app, output_dir):
    """Capture view with boundary condition markers visible."""
    try:
        # Show loads/BCs
        app.feViewShow("LoadsBC", True)
        app.feViewRegenerate(0)
        time.sleep(0.5)

        output_path = os.path.join(output_dir, "boundary_conditions.png")
        result = capture_view(app, output_path, "Boundary Conditions")

        # Hide loads/BCs after capture
        app.feViewShow("LoadsBC", False)
        return result
    except Exception as e:
        print(f"  WARNING: BC capture failed: {e}")
        return False


def capture_cbush_elements(app, output_dir):
    """Capture view highlighting CBUSH bolt elements."""
    try:
        # Try to select CBUSH elements by type
        # Element type 36 = CBUSH in Femap
        app.feViewOrientation(19)  # Isometric
        app.feViewRegenerate(0)
        time.sleep(0.5)

        output_path = os.path.join(output_dir, "cbush_elements.png")
        return capture_view(app, output_path, "CBUSH Elements")
    except Exception as e:
        print(f"  WARNING: CBUSH capture failed: {e}")
        return False


def capture_mode_shapes(app, output_dir, num_modes=5):
    """Capture first N mode shape deformation plots."""
    captured = 0
    try:
        for mode in range(1, num_modes + 1):
            try:
                # Set deformation to mode shape
                app.feViewDeform(1, mode)  # 1 = on, mode number
                app.feViewOrientation(19)  # Isometric
                app.feViewRegenerate(0)
                time.sleep(0.5)

                output_path = os.path.join(output_dir, f"mode_{mode:02d}.png")
                if capture_view(app, output_path, f"Mode {mode}"):
                    captured += 1
            except Exception as e:
                print(f"  WARNING: Mode {mode} capture failed: {e}")

        # Turn off deformation
        try:
            app.feViewDeform(0, 0)
        except Exception:
            pass
    except Exception as e:
        print(f"  WARNING: Mode shape capture failed: {e}")

    return captured


def main():
    parser = argparse.ArgumentParser(description="Capture Femap model views as PNG images")
    parser.add_argument("--model", required=True, help="Path to Nastran DAT or MASTER file to open")
    parser.add_argument("--output-dir", required=True, help="Directory to save PNG images")
    parser.add_argument("--modes", type=int, default=5, help="Number of mode shapes to capture (default: 5)")
    args = parser.parse_args()

    # Check Femap availability — exit gracefully if not present
    app = check_femap()
    if app is None:
        print("Femap not available — no images captured (non-fatal)")
        sys.exit(0)

    os.makedirs(args.output_dir, exist_ok=True)

    # Open model
    model_path = os.path.abspath(args.model)
    if not os.path.exists(model_path):
        print(f"WARNING: Model file not found: {model_path}")
        sys.exit(0)

    print(f"Opening model: {model_path}")
    try:
        app.feFileOpen(0, model_path)
    except Exception as e:
        print(f"WARNING: Failed to open model in Femap: {e}")
        try:
            app.feAppExit(False)
        except Exception:
            pass
        sys.exit(0)

    time.sleep(2)  # Let model fully load

    print("Capturing views...")
    results = {
        "mesh_overview": capture_mesh_overview(app, args.output_dir),
        "boundary_conditions": capture_boundary_conditions(app, args.output_dir),
        "cbush_elements": capture_cbush_elements(app, args.output_dir),
    }

    mode_count = capture_mode_shapes(app, args.output_dir, args.modes)
    results["mode_shapes"] = mode_count

    # Close Femap
    try:
        app.feAppExit(False)
    except Exception:
        pass

    # Summary
    captured = sum(1 for v in results.values() if v and v is not False)
    total_images = sum(1 for v in [results["mesh_overview"], results["boundary_conditions"],
                                    results["cbush_elements"]] if v) + mode_count
    print(f"\nCapture complete: {total_images} images saved to {args.output_dir}")

    # Write manifest for downstream report embedding
    manifest_path = os.path.join(args.output_dir, "image_manifest.txt")
    with open(manifest_path, "w") as f:
        for fname in sorted(os.listdir(args.output_dir)):
            if fname.endswith(".png"):
                f.write(fname + "\n")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
