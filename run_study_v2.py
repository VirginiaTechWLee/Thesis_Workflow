import sys
import time
import os

LOG_FILE = r"C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow\run_study_log.txt"

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line)

log("=" * 60)
log("HEEDS Study Runner v3 (diagnostic)")
log("=" * 60)

import HEEDS

app = HEEDS.app()
project_path = app.data("-project")

log(f"Project: {project_path}")
log(f"HEEDS module location: {HEEDS.__file__}" if hasattr(HEEDS, '__file__') else "HEEDS module: built-in")

# Open project
log("Opening project...")
HEEDS.open(project_path)

proj = HEEDS.currentProject()
study = HEEDS.currentStudy()

log(f"Project loaded: {proj}")
log(f"Study loaded: {study}")

# Introspect the study object
log("--- Study object introspection ---")
study_methods = [m for m in dir(study) if not m.startswith('_')]
log(f"Study methods/attrs: {study_methods}")

# Try to get study info
for attr in ['name', 'status', 'id', 'folder', 'directory', 'path', 'agents', 'numAgents']:
    try:
        val = getattr(study, attr)
        if callable(val):
            result = val()
            log(f"  study.{attr}() = {result}")
        else:
            log(f"  study.{attr} = {val}")
    except Exception as e:
        log(f"  study.{attr}: {type(e).__name__}: {e}")

# Introspect project object
log("--- Project object introspection ---")
proj_methods = [m for m in dir(proj) if not m.startswith('_')]
log(f"Project methods/attrs: {proj_methods}")

for attr in ['name', 'path', 'folder', 'directory', 'studies', 'validate']:
    try:
        val = getattr(proj, attr)
        if callable(val):
            result = val()
            log(f"  proj.{attr}() = {result}")
        else:
            log(f"  proj.{attr} = {val}")
    except Exception as e:
        log(f"  proj.{attr}: {type(e).__name__}: {e}")

# Check if the project folder (working directory) has the expected files
work_dir = os.path.dirname(project_path)
log(f"Working directory: {work_dir}")
log(f"Files in working dir: {os.listdir(work_dir)[:20]}")

# Try to validate/check the study before running
log("--- Attempting study.run() ---")
t0 = time.time()
try:
    result = study.run()
    t1 = time.time()
    log(f"study.run() returned: {result} (took {t1-t0:.2f}s)")
except Exception as e:
    t1 = time.time()
    log(f"ERROR in study.run(): {type(e).__name__}: {e} (took {t1-t0:.2f}s)")
    sys.exit(1)

# Check study status after run
for attr in ['status', 'folder', 'directory']:
    try:
        val = getattr(study, attr)
        if callable(val):
            result = val()
            log(f"  POST-RUN study.{attr}() = {result}")
        else:
            log(f"  POST-RUN study.{attr} = {val}")
    except Exception as e:
        pass

# Check if study folder was created
study_name = os.path.splitext(os.path.basename(project_path))[0]
expected_folder = os.path.join(work_dir, f"{study_name}_Study_1")
log(f"Expected study folder: {expected_folder}")
log(f"Study folder exists: {os.path.exists(expected_folder)}")
if os.path.exists(expected_folder):
    log(f"Study folder contents: {os.listdir(expected_folder)[:20]}")

# Wait for completion
log("--- Calling study.wait() ---")
t0 = time.time()
try:
    result = study.wait()
    t1 = time.time()
    log(f"study.wait() returned: {result} (took {t1-t0:.2f}s)")
except Exception as e:
    t1 = time.time()
    log(f"ERROR in study.wait(): {type(e).__name__}: {e} (took {t1-t0:.2f}s)")

# Final check
log(f"Study folder exists (final): {os.path.exists(expected_folder)}")
if os.path.exists(expected_folder):
    log(f"Study folder contents: {os.listdir(expected_folder)}")

# Check HEEDS messages/errors
for attr in ['messages', 'errors', 'warnings', 'log', 'getMessages', 'getErrors']:
    try:
        val = getattr(study, attr)
        if callable(val):
            result = val()
            log(f"study.{attr}() = {result}")
        else:
            log(f"study.{attr} = {val}")
    except:
        pass

log("=" * 60)
log("Script complete")
log("=" * 60)
