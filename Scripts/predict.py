"""
Bolt looseness diagnostic prediction from a single PCH file.

Takes a Nastran PCH file, extracts features using the same pipeline as
training, runs all three classifiers (10-class, binary ensemble,
IsolationForest), and produces a diagnostic report with SHAP explanations.

Usage:
    python Scripts/predict.py --pch path/to/file.pch
    python Scripts/predict.py --pch file.pch --verbose
    python Scripts/predict.py --pch file.pch --model-dir D:\\thesis_database
"""
import argparse
import os
import sys
import sqlite3
import time
import datetime

os.environ["PYTHONUNBUFFERED"] = "1"

import joblib
import numpy as np

# Optional SHAP
try:
    import shap
    _HAS_SHAP = True
except ImportError:
    _HAS_SHAP = False


# ---------------------------------------------------------------------------
# Step 1: Parse PCH and import to temp in-memory DB
# ---------------------------------------------------------------------------
def _import_pch_to_memdb(pch_path, main_db_path=None):
    """Parse a PCH file and load into an in-memory SQLite DB.

    If main_db_path is provided, the baseline case is copied from the main
    database so delta features (spectral deltas, Miles delta-fn) can be
    computed — matching the training pipeline exactly.

    Returns (conn, case_id, baseline_cid) where conn is the in-memory
    SQLite connection and baseline_cid is the baseline case_id (or None).
    """
    # Import parser from batch_import module
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    db_scripts = os.path.join(os.path.dirname(scripts_dir), "heeds", "database")
    if db_scripts not in sys.path:
        sys.path.insert(0, db_scripts)
    import batch_import_to_database as bi

    # Parse PCH
    psd = bi.parse_pch_file(pch_path)

    # Create in-memory DB with same schema
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)

    # Insert study + case
    conn.execute("INSERT INTO studies (study_id, study_name) VALUES (1, 'predict')")
    conn.execute(
        "INSERT INTO cases (case_id, study_id, case_name, case_number, is_baseline, pch_file) "
        "VALUES (1, 1, 'predict', 1, 0, ?)", (pch_path,)
    )

    # Insert PSD data
    bi.insert_psd_data_batch(conn, 1, psd)
    bi.insert_peaks_batch(conn, 1, psd)
    bi.insert_force_psd_batch(conn, 1, psd)
    bi.insert_force_peaks_batch(conn, 1, psd)

    # Insert parameters from Bush.blk if it exists alongside the PCH
    bush_path = os.path.join(os.path.dirname(pch_path), "Bush.blk")
    if os.path.exists(bush_path):
        params = bi.parse_bush_file(bush_path)
        if params:
            bi.insert_parameters_batch(conn, 1, params)

    # Insert strain energy from f06 if it exists
    f06_path = pch_path.replace(".pch", ".f06")
    if os.path.exists(f06_path):
        ese = bi.parse_f06_strain_energy(f06_path)
        if ese:
            bi.insert_strain_energy_batch(conn, 1, ese)

    # Copy baseline case from main database (for delta features)
    baseline_cid = None
    if main_db_path and os.path.exists(main_db_path):
        baseline_cid = _copy_baseline_from_main_db(conn, main_db_path)

    conn.commit()
    return conn, 1, baseline_cid


def _copy_baseline_from_main_db(memdb_conn, main_db_path):
    """Copy baseline case data from the main database into the temp DB.

    This enables delta features (spectral deltas, Miles delta-fn) to be
    computed for the prediction case, matching the training pipeline.
    Returns the baseline case_id in the temp DB, or None if not found.
    """
    main_conn = sqlite3.connect(main_db_path)

    # Find the baseline case
    row = main_conn.execute(
        "SELECT case_id FROM cases WHERE is_baseline = 1 LIMIT 1"
    ).fetchone()
    if row is None:
        row = main_conn.execute(
            "SELECT case_id FROM cases WHERE case_number = 0 LIMIT 1"
        ).fetchone()
    if row is None:
        main_conn.close()
        return None

    src_cid = row[0]
    dst_cid = 2  # baseline gets case_id 2 in temp DB

    # Insert baseline case record
    memdb_conn.execute(
        "INSERT INTO cases (case_id, study_id, case_name, case_number, is_baseline) "
        "VALUES (?, 1, 'baseline', 0, 1)", (dst_cid,)
    )

    # Copy PSD data
    rows = main_conn.execute(
        "SELECT node_id, dof, frequency, psd_value, data_type "
        "FROM psd_data WHERE case_id = ?", (src_cid,)
    ).fetchall()
    memdb_conn.executemany(
        "INSERT INTO psd_data (case_id, node_id, dof, frequency, psd_value, data_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(dst_cid, *r) for r in rows]
    )

    # Copy peaks
    rows = main_conn.execute(
        "SELECT node_id, dof, data_type, area, peak1_freq, peak1_psd, "
        "peak2_freq, peak2_psd, peak3_freq, peak3_psd "
        "FROM peaks WHERE case_id = ?", (src_cid,)
    ).fetchall()
    memdb_conn.executemany(
        "INSERT INTO peaks (case_id, node_id, dof, data_type, area, "
        "peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(dst_cid, *r) for r in rows]
    )

    # Copy force PSD
    rows = main_conn.execute(
        "SELECT element_id, dof, frequency, psd_value, data_type "
        "FROM force_psd_data WHERE case_id = ?", (src_cid,)
    ).fetchall()
    memdb_conn.executemany(
        "INSERT INTO force_psd_data (case_id, element_id, dof, frequency, psd_value, data_type) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(dst_cid, *r) for r in rows]
    )

    # Copy force peaks
    rows = main_conn.execute(
        "SELECT element_id, dof, data_type, area, peak1_freq, peak1_psd, "
        "peak2_freq, peak2_psd, peak3_freq, peak3_psd "
        "FROM force_peaks WHERE case_id = ?", (src_cid,)
    ).fetchall()
    memdb_conn.executemany(
        "INSERT INTO force_peaks (case_id, element_id, dof, data_type, area, "
        "peak1_freq, peak1_psd, peak2_freq, peak2_psd, peak3_freq, peak3_psd) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(dst_cid, *r) for r in rows]
    )

    # Copy strain energy
    rows = main_conn.execute(
        "SELECT element_id, element_type, subcase_id, frequency, strain_energy, percent_total "
        "FROM strain_energy WHERE case_id = ?", (src_cid,)
    ).fetchall()
    memdb_conn.executemany(
        "INSERT INTO strain_energy (case_id, element_id, element_type, subcase_id, "
        "frequency, strain_energy, percent_total) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(dst_cid, *r) for r in rows]
    )

    # Copy parameters
    rows = main_conn.execute(
        "SELECT element_id, K4, K5, K6 FROM parameters WHERE case_id = ?", (src_cid,)
    ).fetchall()
    memdb_conn.executemany(
        "INSERT INTO parameters (case_id, element_id, K4, K5, K6) VALUES (?, ?, ?, ?, ?)",
        [(dst_cid, *r) for r in rows]
    )

    # Copy miles (if already computed in main DB)
    try:
        rows = main_conn.execute(
            "SELECT node_id, dof, data_type, mode_number, fn, Q, PSD_fn, grms, bandwidth "
            "FROM miles WHERE case_id = ?", (src_cid,)
        ).fetchall()
        memdb_conn.executemany(
            "INSERT INTO miles (case_id, node_id, dof, data_type, mode_number, "
            "fn, Q, PSD_fn, grms, bandwidth) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(dst_cid, *r) for r in rows]
        )
    except Exception:
        pass  # Miles table may not exist in main DB

    main_conn.close()
    return dst_cid


def _create_schema(conn):
    """Create the minimal DB schema needed for feature extraction."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS studies (
            study_id INTEGER PRIMARY KEY,
            study_name TEXT,
            force_label INTEGER DEFAULT NULL
        );
        CREATE TABLE IF NOT EXISTS cases (
            case_id INTEGER PRIMARY KEY,
            study_id INTEGER,
            case_name TEXT,
            case_number INTEGER,
            is_baseline INTEGER DEFAULT 0,
            status TEXT DEFAULT 'complete',
            pch_file TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS parameters (
            param_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            element_id INTEGER,
            K4 REAL, K5 REAL, K6 REAL
        );
        CREATE TABLE IF NOT EXISTS psd_data (
            psd_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            node_id INTEGER,
            dof TEXT,
            frequency REAL,
            psd_value REAL,
            data_type TEXT
        );
        CREATE TABLE IF NOT EXISTS peaks (
            peak_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            node_id INTEGER,
            dof TEXT,
            data_type TEXT,
            area REAL,
            peak1_freq REAL, peak1_psd REAL,
            peak2_freq REAL, peak2_psd REAL,
            peak3_freq REAL, peak3_psd REAL
        );
        CREATE TABLE IF NOT EXISTS force_psd_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            element_id INTEGER,
            dof TEXT,
            frequency REAL,
            psd_value REAL,
            data_type TEXT
        );
        CREATE TABLE IF NOT EXISTS force_peaks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            element_id INTEGER,
            dof TEXT,
            data_type TEXT,
            area REAL,
            peak1_freq REAL, peak1_psd REAL,
            peak2_freq REAL, peak2_psd REAL,
            peak3_freq REAL, peak3_psd REAL
        );
        CREATE TABLE IF NOT EXISTS strain_energy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            element_id INTEGER,
            element_type TEXT,
            subcase_id INTEGER,
            frequency REAL,
            strain_energy REAL,
            percent_total REAL
        );
        CREATE TABLE IF NOT EXISTS miles (
            miles_id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER,
            node_id INTEGER,
            dof TEXT,
            data_type TEXT,
            mode_number INTEGER,
            fn REAL,
            Q REAL,
            PSD_fn REAL,
            grms REAL,
            bandwidth REAL
        );
    """)


# ---------------------------------------------------------------------------
# Step 2: Extract features (same pipeline as training)
# ---------------------------------------------------------------------------
def _extract_features(memdb_conn, case_id, baseline_cid, training_feature_names,
                      verbose=False):
    """Extract features for one case using the same logic as extract_features.py.

    The in-memory DB is dumped to a temp file so that functions requiring a
    db_path (e.g. extract_spectral_and_delta_features with its reconnect
    logic) work correctly.

    If baseline_cid is provided (baseline was copied from main DB), delta
    features are computed — matching the training pipeline exactly.

    Returns a 1D numpy array matching training_feature_names order.
    """
    import tempfile
    import shutil
    import pandas as pd

    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import extract_features as ef

    # Dump in-memory DB to a temp file so path-based functions work
    tmp_dir = tempfile.mkdtemp(prefix="predict_")
    tmp_db = os.path.join(tmp_dir, "predict_temp.db")
    try:
        disk_conn = sqlite3.connect(tmp_db)
        memdb_conn.backup(disk_conn)
        disk_conn.close()

        # Compute Miles equation on the temp DB (for both predict + baseline)
        db_scripts = os.path.join(os.path.dirname(scripts_dir), "heeds", "database")
        if db_scripts not in sys.path:
            sys.path.insert(0, db_scripts)
        try:
            import compute_miles as cm
            cm.populate_miles_table(tmp_db)
        except Exception as exc:
            if verbose:
                print(f"  Miles computation skipped: {exc}")

        # Open connection to temp DB
        conn = sqlite3.connect(tmp_db)

        # Get ALL cases (predict + baseline if present)
        cases = pd.read_sql_query(
            "SELECT case_id, case_number, is_baseline FROM cases ORDER BY case_id",
            conn,
        )

        # Use baseline for structure discovery (preferred) or predict case
        ref_cid = baseline_cid if baseline_cid else case_id
        nodes = ef.discover_nodes(conn, ref_cid)
        primary_dof, primary_dtype = ef.detect_primary_channel(conn, ref_cid)
        common_freq = ef._common_freq_grid(conn, ref_cid, n_points=256)
        if verbose:
            print(f"  Nodes discovered: {nodes}")
            print(f"  Primary channel: {primary_dof} / {primary_dtype}")
            print(f"  Freq grid: {len(common_freq)} points "
                  f"({common_freq[0]:.1f}-{common_freq[-1]:.1f} Hz)")
            if baseline_cid:
                print(f"  Baseline case_id: {baseline_cid} (delta features enabled)")
        conn.close()

        # --- Extract each feature group ---
        # Peak features (takes conn)
        conn = sqlite3.connect(tmp_db)
        peak_feats = ef.extract_peak_features(conn, cases)
        conn.close()

        # Spectral + delta features (takes db_path)
        spectral_feats, delta_feats = ef.extract_spectral_and_delta_features(
            tmp_db, cases, common_freq, nodes, primary_dof, primary_dtype,
        )

        # Miles features (with baseline for delta-fn)
        conn = sqlite3.connect(tmp_db)
        miles_feats = ef.extract_miles_features(
            conn, cases, baseline_cid=baseline_cid)
        conn.close()

        # Strain energy features (with baseline for delta)
        conn = sqlite3.connect(tmp_db)
        se_feats = ef.extract_strain_energy_features(
            conn, cases, baseline_cid=baseline_cid)
        conn.close()

        # Force PSD features (with baseline for delta)
        conn = sqlite3.connect(tmp_db)
        fp_feats = ef.extract_force_psd_features(
            conn, cases, baseline_cid=baseline_cid)
        conn.close()

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # Merge all feature groups (both predict + baseline cases)
    merged = cases[["case_id"]].copy()
    for df in [peak_feats, spectral_feats, delta_feats,
               miles_feats, se_feats, fp_feats]:
        if df is not None and len(df) > 0:
            merged = merged.merge(df, on="case_id", how="left")
    merged = merged.fillna(0.0)

    # Keep only the predict case (drop baseline row if present)
    merged = merged[merged["case_id"] == case_id].reset_index(drop=True)

    # Extract feature values in training order
    feature_vector = np.zeros(len(training_feature_names), dtype=np.float64)
    merged_cols = set(merged.columns)

    matched = 0
    for i, fname in enumerate(training_feature_names):
        if fname in merged_cols:
            feature_vector[i] = float(merged[fname].iloc[0])
            matched += 1

    if verbose:
        print(f"  Features matched: {matched}/{len(training_feature_names)}")
        if matched < len(training_feature_names):
            missing = [f for f in training_feature_names if f not in merged_cols]
            print(f"  Missing features (set to 0): {len(missing)}")
            if len(missing) <= 10:
                for m in missing:
                    print(f"    - {m}")

    if matched < len(training_feature_names) * 0.5:
        print(f"WARNING: Only {matched}/{len(training_feature_names)} features matched.")
        print(f"  Was the model trained on a different dataset?")

    # Apply noise floor (same tags as training in extract_features.py)
    noise_floor = 1e-5
    amplitude_tags = ('_area', '_pk1a', '_pk2a', '_pk3a', '_PSDfn', '_grms',
                      '_rms', '_band', '_d_area', '_peak')
    for i, fname in enumerate(training_feature_names):
        if any(tag in fname for tag in amplitude_tags):
            if abs(feature_vector[i]) < noise_floor:
                feature_vector[i] = 0.0

    # Log-transform amplitude features (same tags as training)
    log_tags = ('_rms', '_band', '_d_rms', '_d_band',
                '_PSDfn', '_grms', '_bw',
                '_area', '_peak', '_pk1a', '_pk2a', '_pk3a')
    for i, fname in enumerate(training_feature_names):
        if any(tag in fname for tag in log_tags):
            feature_vector[i] = np.sign(feature_vector[i]) * np.log10(
                np.abs(feature_vector[i]) + 1)

    return feature_vector.reshape(1, -1)


# ---------------------------------------------------------------------------
# Step 6-8: Run classifiers
# ---------------------------------------------------------------------------
def _run_10class(X_pca, model_bundle, label_encoder=None):
    """Run the 10-class bolt localization classifier."""
    model = model_bundle["model"]
    model_name = model_bundle.get("model_name", "unknown")

    if model_name == "XGBoost" and label_encoder is not None:
        proba = model.predict_proba(X_pca)[0]
        pred_enc = model.predict(X_pca)[0]
        pred = label_encoder.inverse_transform([pred_enc])[0]
        # Map probabilities to original classes
        classes = label_encoder.classes_
        class_proba = {int(classes[i]): float(proba[i]) for i in range(len(classes))}
    else:
        proba = model.predict_proba(X_pca)[0]
        pred = model.predict(X_pca)[0]
        classes = model.classes_
        class_proba = {int(classes[i]): float(proba[i]) for i in range(len(classes))}

    confidence = max(class_proba.values())
    return int(pred), confidence, class_proba


def _run_binary_ensemble(X_pca, binary_bundle):
    """Run the binary per-bolt ensemble."""
    models = binary_bundle["models"]
    threshold = binary_bundle.get("healthy_threshold", 0.5)
    bolt_ids = binary_bundle.get("bolt_ids", sorted(models.keys()))

    scores = {}
    for bolt_id in bolt_ids:
        model = models[bolt_id]
        proba = model.predict_proba(X_pca)[0]
        # proba = [P(not loose), P(loose)]
        scores[bolt_id] = float(proba[1]) if len(proba) > 1 else float(proba[0])

    best_bolt = max(scores, key=scores.get)
    best_confidence = scores[best_bolt]

    if best_confidence < threshold:
        prediction = 0  # healthy
        confidence = 1 - best_confidence
    else:
        prediction = best_bolt
        confidence = best_confidence

    return prediction, confidence, scores, threshold


def _run_isolation_forest(X_pca, iso_bundle):
    """Run IsolationForest anomaly detection."""
    model = iso_bundle["model"]
    score = float(model.decision_function(X_pca)[0])
    prediction = model.predict(X_pca)[0]  # +1 = inlier, -1 = outlier
    is_anomalous = prediction == -1
    return is_anomalous, score


# ---------------------------------------------------------------------------
# Step 9: SHAP explanation
# ---------------------------------------------------------------------------
def _compute_shap(X_pca, model_bundle, feature_names_pca, label_encoder=None,
                  top_n=5, verbose=False):
    """Compute SHAP values and return top features driving the prediction."""
    if not _HAS_SHAP:
        return None, "SHAP not available (pip install shap)"

    model = model_bundle["model"]
    model_name = model_bundle.get("model_name", "unknown")

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_pca)
    except Exception as exc:
        return None, f"SHAP failed: {exc}"

    # For multi-class, shap_values is a list of arrays (one per class)
    # Find the predicted class and get its SHAP values
    if model_name == "XGBoost" and label_encoder is not None:
        pred_enc = int(model.predict(X_pca)[0])
        if isinstance(shap_values, list):
            sv = shap_values[pred_enc][0]
        else:
            # Some XGBoost versions return 3D array
            if shap_values.ndim == 3:
                sv = shap_values[0, :, pred_enc]
            else:
                sv = shap_values[0]
    else:
        pred = int(model.predict(X_pca)[0])
        if isinstance(shap_values, list):
            # Find index of predicted class
            classes = list(model.classes_)
            pred_idx = classes.index(pred) if pred in classes else 0
            sv = shap_values[pred_idx][0]
        else:
            sv = shap_values[0]

    # Top features by absolute SHAP value
    top_idx = np.argsort(np.abs(sv))[::-1][:top_n]
    results = []
    for rank, idx in enumerate(top_idx, 1):
        results.append({
            "rank": rank,
            "feature": feature_names_pca[idx] if idx < len(feature_names_pca) else f"PC{idx}",
            "shap_value": float(sv[idx]),
            "direction": "increases" if sv[idx] > 0 else "decreases",
        })

    return results, None


def _map_pca_to_original(pca_component_idx, pca_model, original_feature_names, top_n=3):
    """Map a PCA component back to the most influential original features."""
    if pca_component_idx >= pca_model.n_components_:
        return []
    loadings = pca_model.components_[pca_component_idx]
    top_orig_idx = np.argsort(np.abs(loadings))[::-1][:top_n]
    results = []
    for idx in top_orig_idx:
        if idx < len(original_feature_names):
            results.append({
                "feature": str(original_feature_names[idx]),
                "loading": float(loadings[idx]),
            })
    return results


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def _format_report(pch_path, iso_result, tenclass_result, binary_result,
                   shap_result, pca_model, original_feature_names,
                   model_bundle, verbose=False):
    """Format the full diagnostic report."""
    is_anomalous, anomaly_score = iso_result
    pred_10c, conf_10c, class_proba = tenclass_result
    pred_bin, conf_bin, bin_scores, bin_threshold = binary_result

    lines = []
    sep = "=" * 56

    lines.append(sep)
    lines.append("BOLT LOOSENESS DIAGNOSTIC REPORT")
    lines.append(f"PCH file:  {os.path.basename(pch_path)}")
    lines.append(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(sep)

    # Anomaly detection
    lines.append("")
    lines.append("ANOMALY DETECTION (IsolationForest)")
    status = "ANOMALOUS" if is_anomalous else "NORMAL"
    lines.append(f"  Status:    {status}  (score: {anomaly_score:.3f})")
    lines.append(f"  Threshold: 0.000 (negative = anomalous)")

    # 10-class classifier
    lines.append("")
    lines.append("BOLT LOCATION -- 10-CLASS CLASSIFIER")
    if pred_10c == 0:
        lines.append(f"  Predicted: HEALTHY (no bolt loosened)")
    else:
        lines.append(f"  Predicted: CBUSH Element {pred_10c}")
    lines.append(f"  Confidence: {conf_10c:.1%}")

    # Binary ensemble
    lines.append("")
    lines.append("BOLT LOCATION -- BINARY ENSEMBLE")
    if pred_bin == 0:
        lines.append(f"  Predicted: HEALTHY (no bolt above threshold)")
    else:
        lines.append(f"  Predicted: CBUSH Element {pred_bin}")
    lines.append(f"  Confidence: {conf_bin:.1%}")
    lines.append(f"  Per-bolt scores:")
    for bolt_id in sorted(bin_scores.keys()):
        marker = " <--" if bolt_id == pred_bin and pred_bin != 0 else ""
        lines.append(f"    Element {bolt_id:>2d}: {bin_scores[bolt_id]:.1%}{marker}")

    # Agreement
    lines.append("")
    lines.append("CLASSIFIER AGREEMENT")
    if pred_10c == pred_bin:
        lines.append(f"  Status: AGREE (both predict element {pred_10c})")
    else:
        lines.append(f"  Status: DISAGREE")
        lines.append(f"    10-class: element {pred_10c} ({conf_10c:.1%})")
        lines.append(f"    Binary:   element {pred_bin} ({conf_bin:.1%})")
        lines.append(f"  Low confidence -- recommend manual inspection")

    # SHAP
    shap_features, shap_error = shap_result
    lines.append("")
    lines.append("SUPPORTING EVIDENCE (SHAP)")
    if shap_error:
        lines.append(f"  {shap_error}")
    elif shap_features:
        lines.append(f"  Top features driving 10-class prediction:")
        lines.append("")
        for sf in shap_features:
            arrow = "+" if sf["shap_value"] > 0 else "-"
            lines.append(f"  {sf['rank']}. {sf['feature']}")
            lines.append(f"     SHAP: {arrow}{abs(sf['shap_value']):.4f} "
                         f"({sf['direction']} fault probability)")
            # Map PCA component to original features
            pc_idx = int(sf["feature"].replace("PC", "")) if sf["feature"].startswith("PC") else -1
            if pc_idx >= 0 and pca_model is not None:
                originals = _map_pca_to_original(pc_idx, pca_model, original_feature_names)
                if originals:
                    top_orig = originals[0]
                    lines.append(f"     Top original feature: {top_orig['feature']} "
                                 f"(loading: {top_orig['loading']:.4f})")
    else:
        lines.append("  No SHAP data available")

    # Interpretation
    lines.append("")
    lines.append("INTERPRETATION")
    if is_anomalous and pred_10c != 0 and pred_10c == pred_bin:
        lines.append(f"  Both classifiers agree: CBUSH element {pred_10c} is the most")
        lines.append(f"  likely source of structural anomaly. IsolationForest confirms")
        lines.append(f"  the response deviates from healthy baseline (score {anomaly_score:.3f}).")
        lines.append(f"  Recommend inspection of bolt connection at element {pred_10c}.")
    elif not is_anomalous:
        lines.append(f"  IsolationForest indicates normal structural response.")
        lines.append(f"  No bolt looseness detected.")
    else:
        lines.append(f"  Mixed signals -- anomaly detected but classifiers")
        lines.append(f"  {'disagree' if pred_10c != pred_bin else 'show low confidence'}.")
        lines.append(f"  Recommend detailed inspection.")

    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


def _get_main_db_path(model_dir):
    """Resolve the main database path from the model directory.

    The main DB lives in the same directory as the model .pkl files
    (e.g. D:\\thesis_database\\thesis_results.db).
    """
    # Try config.yaml first
    try:
        import yaml
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "fem_input", "config.yaml"
        )
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        db_path = cfg.get("database", {}).get("default_path", "")
        if db_path and os.path.exists(db_path):
            return db_path
    except Exception:
        pass

    # Fall back to model_dir/thesis_results.db
    candidate = os.path.join(model_dir, "thesis_results.db")
    if os.path.exists(candidate):
        return candidate

    return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def predict(pch_path, model_dir, verbose=False):
    """Full prediction pipeline: PCH -> features -> classifiers -> report."""

    if not os.path.exists(pch_path):
        print(f"ERROR: PCH file not found: {pch_path}")
        sys.exit(1)

    print(f"Loading PCH: {pch_path}")

    # --- Step 1: Parse and import to temp DB ---
    t0 = time.time()
    # Derive main DB path from config for baseline lookup
    main_db_path = _get_main_db_path(model_dir)
    conn, case_id, baseline_cid = _import_pch_to_memdb(pch_path, main_db_path)
    if verbose:
        n_psd = conn.execute("SELECT COUNT(*) FROM psd_data").fetchone()[0]
        n_force = conn.execute("SELECT COUNT(*) FROM force_psd_data").fetchone()[0]
        n_se = conn.execute("SELECT COUNT(*) FROM strain_energy").fetchone()[0]
        n_cases = conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        print(f"  Temp DB: {n_psd:,} PSD rows, {n_force:,} force rows, {n_se:,} SE rows")
        print(f"  Cases in temp DB: {n_cases} (baseline={'yes' if baseline_cid else 'no'})")
    print(f"  PCH parsed ({time.time()-t0:.1f}s)")

    # --- Load model artifacts ---
    required = ["bolt_classifier.pkl", "pca_transform.pkl",
                "feature_names.pkl"]
    for f in required:
        path = os.path.join(model_dir, f)
        if not os.path.exists(path):
            print(f"ERROR: Required model file not found: {path}")
            sys.exit(1)

    # Need training_matrix.npz for the REAL scaler (extract_features scaler)
    npz_path = os.path.join(model_dir, "training_matrix.npz")
    if not os.path.exists(npz_path):
        print(f"ERROR: training_matrix.npz not found in {model_dir}")
        sys.exit(1)

    model_bundle = joblib.load(os.path.join(model_dir, "bolt_classifier.pkl"))
    pca = joblib.load(os.path.join(model_dir, "pca_transform.pkl"))
    feature_names = joblib.load(os.path.join(model_dir, "feature_names.pkl"))

    # Load the REAL scaler from extract_features (not train_classifier's identity scaler)
    from sklearn.preprocessing import StandardScaler
    npz_data = np.load(npz_path, allow_pickle=True)
    ef_scaler = StandardScaler()
    ef_scaler.mean_ = npz_data["scaler_mean"]
    ef_scaler.scale_ = npz_data["scaler_scale"]
    ef_scaler.var_ = ef_scaler.scale_ ** 2
    ef_scaler.n_features_in_ = len(feature_names)
    ef_scaler.n_samples_seen_ = 1  # placeholder

    # train_classifier also applies a scaler (on already-scaled data)
    tc_scaler_path = os.path.join(model_dir, "standard_scaler.pkl")
    tc_scaler = joblib.load(tc_scaler_path) if os.path.exists(tc_scaler_path) else None

    # Optional
    le_path = os.path.join(model_dir, "label_encoder.pkl")
    label_encoder = joblib.load(le_path) if os.path.exists(le_path) else None

    binary_path = os.path.join(model_dir, "binary_classifiers.pkl")
    binary_bundle = joblib.load(binary_path) if os.path.exists(binary_path) else None

    iso_path = os.path.join(model_dir, "isolation_forest.pkl")
    iso_bundle = joblib.load(iso_path) if os.path.exists(iso_path) else None

    print(f"  Models loaded from {model_dir}")
    if verbose:
        print(f"    10-class: {model_bundle.get('model_name', '?')}")
        print(f"    Binary:   {'loaded' if binary_bundle else 'not found'}")
        print(f"    IsoForest: {'loaded' if iso_bundle else 'not found'}")
        print(f"    Features: {len(feature_names)}")
        print(f"    PCA:      {pca.n_components_} components "
              f"({pca.explained_variance_ratio_.sum():.1%} variance)")
        print(f"    EF scaler: mean range [{ef_scaler.mean_.min():.2f}, "
              f"{ef_scaler.mean_.max():.2f}]")

    # --- Step 2: Extract features ---
    t1 = time.time()
    X_raw = _extract_features(conn, case_id, baseline_cid, feature_names,
                              verbose=verbose)
    conn.close()
    print(f"  Features extracted ({time.time()-t1:.1f}s)")

    # --- Step 3: Scale (transform ONLY, never fit) ---
    # Two scalers in series:
    # 1. extract_features scaler: raw features → zero-mean, unit-variance
    # 2. train_classifier scaler: identity (trained on already-scaled data)
    X_scaled = ef_scaler.transform(X_raw)
    if tc_scaler is not None:
        X_scaled = tc_scaler.transform(X_scaled)

    # --- Step 4: PCA (transform ONLY, never fit) ---
    X_pca = pca.transform(X_scaled)
    if verbose:
        print(f"  PCA: {X_raw.shape[1]} -> {X_pca.shape[1]} components")

    # --- Step 6: 10-class classifier ---
    pred_10c, conf_10c, class_proba = _run_10class(X_pca, model_bundle, label_encoder)
    print(f"  10-class prediction: element {pred_10c} ({conf_10c:.1%})")

    # --- Step 7: Binary ensemble ---
    if binary_bundle:
        pred_bin, conf_bin, bin_scores, bin_threshold = _run_binary_ensemble(
            X_pca, binary_bundle)
        print(f"  Binary prediction:   element {pred_bin} ({conf_bin:.1%})")
    else:
        pred_bin, conf_bin, bin_scores, bin_threshold = 0, 0.0, {}, 0.5
        print(f"  Binary ensemble: not available")

    # --- Step 8: IsolationForest ---
    if iso_bundle:
        is_anomalous, anomaly_score = _run_isolation_forest(X_pca, iso_bundle)
        status = "ANOMALOUS" if is_anomalous else "NORMAL"
        print(f"  Anomaly detection:   {status} (score: {anomaly_score:.3f})")
    else:
        is_anomalous, anomaly_score = False, 0.0
        print(f"  IsolationForest: not available")

    # --- Step 9: SHAP ---
    pca_feature_names = [f"PC{i}" for i in range(X_pca.shape[1])]
    shap_result = _compute_shap(X_pca, model_bundle, pca_feature_names,
                                label_encoder, top_n=5, verbose=verbose)

    # --- Format and print report ---
    report = _format_report(
        pch_path,
        (is_anomalous, anomaly_score),
        (pred_10c, conf_10c, class_proba),
        (pred_bin, conf_bin, bin_scores, bin_threshold),
        shap_result,
        pca, feature_names,
        model_bundle, verbose=verbose,
    )
    print("\n" + report)

    return {
        "prediction_10class": pred_10c,
        "confidence_10class": conf_10c,
        "prediction_binary": pred_bin,
        "confidence_binary": conf_bin,
        "is_anomalous": is_anomalous,
        "anomaly_score": anomaly_score,
        "agreement": pred_10c == pred_bin,
        "report": report,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _default_model_dir():
    """Try to read model dir from config.yaml, fall back to D:\\thesis_database."""
    try:
        import yaml
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "fem_input", "config.yaml"
        )
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}
        db_path = cfg.get("database", {}).get("default_path", "")
        if db_path:
            return os.path.dirname(db_path)
    except Exception:
        pass
    return r"D:\thesis_database"


def main():
    parser = argparse.ArgumentParser(
        description="Bolt looseness diagnostic prediction from a PCH file"
    )
    parser.add_argument(
        "--pch", required=True,
        help="Path to Nastran PCH file"
    )
    parser.add_argument(
        "--model-dir", default=None,
        help="Directory containing trained model .pkl files "
             "(default: from config.yaml database.default_path)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print detailed diagnostics"
    )
    args = parser.parse_args()

    model_dir = args.model_dir or _default_model_dir()
    result = predict(args.pch, model_dir, verbose=args.verbose)


if __name__ == "__main__":
    main()
