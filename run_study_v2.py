import sys
import time

LOG_FILE = r"C:\Users\waynelee\Desktop\actions-runner\_work\Thesis_Workflow\Thesis_Workflow\run_study_log.txt"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(str(msg) + "\n")
    print(msg)

log("=" * 60)
log("HEEDS Study Runner")
log("=" * 60)

import HEEDS

app = HEEDS.app()
project_path = app.data("-project")

log(f"Project: {project_path}")

# Open project
log("Opening project...")
HEEDS.open(project_path)

proj = HEEDS.currentProject()
study = HEEDS.currentStudy()

log(f"Project loaded: {proj}")
log(f"Study loaded: {study}")

# Run the study
log("Starting study.run()...")
try:
    study.run()
    log("study.run() called successfully!")
except Exception as e:
    log(f"ERROR calling study.run(): {e}")
    sys.exit(1)

# Wait for completion
log("Calling study.wait() to wait for completion...")
try:
    study.wait()
    log("study.wait() completed!")
except Exception as e:
    log(f"ERROR in study.wait(): {e}")

log("=" * 60)
log("Study run complete!")
log("=" * 60)
