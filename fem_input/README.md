# fem_input/ — FEM Drop Zone

## Quick Start

To run the Nastran Utility Workflow on a new FEM, drop these files here:

| File | Required | Purpose |
|------|----------|---------|
| `<model>.dat` | **Yes** | Nastran structural deck (SOL 103 / SOL SEMODES) |
| `Bush.blk` | **Yes** | CBUSH bolt properties (PBUSH cards) |
| `RandomBeamX.dat` | For `full`/`sol111` runs | SOL 111 random response deck |
| `config.yaml` | **Yes** | Pipeline configuration (update to match your model) |

Then trigger the workflow via GitHub Actions UI, `gh workflow run`, or git push.

---

## DAT File Requirements

Your `.dat` file must satisfy these checks (enforced by the DBALL readiness validator):

1. **Solution type:** `SOL SEMODES` or `SOL 103` — modal analysis
2. **INIT MASTER:** Must include `$INIT MASTER(S)` so the DBALL is preserved between runs
3. **Boundary conditions:** At least one `SPC` or `SPC1` card — no free-free models
4. **INCLUDE 'Bush.blk':** The DAT must reference `Bush.blk` via an INCLUDE statement — this is how HEEDS swaps bolt stiffness values during parametric sweeps
5. **DISPLACEMENT output:** `DISPLACEMENT(PLOT) = ALL` in the case control section

### DAT File Structure (example header)
```
$INIT MASTER(S)
NASTRAN SYSTEM(442)=-1,SYSTEM(319)=1
ID BASIC,FEMAP
SOL SEMODES
CEND
MEFFMASS(ALL) = YES
  TITLE = FIXED BASE MODES
  ECHO = NONE
  DISPLACEMENT(PLOT) = ALL
  SPCFORCE(PLOT) = ALL
  METHOD = 1
  SPC = 1
BEGIN BULK
...
SPC1           1  123456       1
INCLUDE 'Bush.blk'
...
CBUSH          1       1       1     111
CBUSH          2       2       2     222
...
ENDDATA
```

### CBUSH Element Convention
Each bolt is modeled as a single CBUSH spring element connecting two nodes:
- **Upper node** = structural attachment point
- **Lower node** = measurement/sensor point

The element ID, property ID, and bolt number must match 1:1:1:
```
CBUSH  <bolt_id>  <bolt_id>  <upper_node>  <lower_node>
```

Example: Bolt 3 = `CBUSH 3  3  3  333` (element 3, property 3, connects node 3 to node 333)

---

## Bush.blk Format

One `PBUSH` card per bolt in Nastran fixed-width format (8-character fields):

```
PBUSH   <id>    K       <K1>    <K2>    <K3>    <K4>    <K5>    <K6>
```

- **K1, K2, K3** = translational stiffness (typically constant, e.g., `1.+6`)
- **K4, K5, K6** = rotational stiffness — these are the design variables that get swept
- **Baseline (healthy):** all rotational stiffness at `1.+12` (1e12 N·m/rad)
- **Bolt 1** is the driving bolt with fixed rotational stiffness (`K4=1.+8, K5=1.+12, K6=1.+12`)

### Example Bush.blk (10 bolts, all healthy baseline)
```
PBUSH   1       K       1.+6    1.+6    1.+6    1.+8    1.+12   1.+12
PBUSH   2       K       1.+6    1.+6    1.+6    1.+12   1.+12   1.+12
PBUSH   3       K       1.+6    1.+6    1.+6    1.+12   1.+12   1.+12
...
PBUSH   10      K       1.+6    1.+6    1.+6    1.+12   1.+12   1.+12
```

**Important:** HEEDS modifies K4/K5/K6 values by overwriting specific character positions (charCol offsets). The fixed-width format must be preserved exactly — do not use comma-separated or free-field format.

---

## RandomBeamX.dat Requirements

Only needed for `full` or `sol111` analysis types. This deck:

1. **References the DBALL** from SOL 103 via `ASSIGN MASTER` / `DBLOCATE` / `RESTART`
2. Uses `SOL 111` for frequency response / random analysis
3. Must contain `DLOAD` or `RANDPS` cards for random excitation
4. Must reference `fixed_base_beam.master` (the MASTER file from SOL 103)

### Example header
```
ASSIGN MASTERCP='fixed_base_beam.master'
DBLOCATE LOGICAL=MASTERCP
ASSIGN MODES='fixed_base_beam.master'
RESTART,LOGI=MODES NOKEEP
SOL 111
CEND
  DISPLACEMENT(PHASE,PSDF) = 1
  ACCELERATION(PHASE,PSDF) = 1
  SDAMPING = 2001
  FREQ = 3001
BEGIN BULK
...
RANDPS  ...
DLOAD   ...
```

**Note:** The MASTER filename in `ASSIGN MASTERCP` must match the actual `.MASTER` file that SOL 103 produces. For the current pipeline, this is always `fixed_base_beam.master`.

---

## config.yaml — What to Update

When bringing a new FEM, update these sections in `config.yaml`:

```yaml
study:
  name: <your_study_name>        # used for folder naming
  sweep_bolts: [3]               # which bolt(s) to sweep
  expected_designs: 5            # how many HEEDS designs

files:
  structural_model: <your_model>.dat   # must match DAT filename
  # Leave other file fields as-is unless renamed

bolts:
  total: <N>                     # number of CBUSH bolts
  driving_bolt: 1                # which bolt is fixed reference
  variable_bolts: [2, 3, ..., N] # which bolts can be swept

output_nodes: [...]              # node IDs to extract PSD from

analysis:
  type: full                     # sol103 | sol111 | full
```

---

## What the Pipeline Does with These Files

1. **Validates** — checks SOL type, boundary conditions, DBALL readiness
2. **Copies** everything to a timestamped folder: `FEM_Utility/<study>_<YYYYMMDD_HHMMSS>/`
3. **Runs Nastran** — SOL 103 (with `scratch=no`) → 10s wait → SOL 111
4. **Collects** all Nastran outputs (F06, OP2, DBALL, PCH, etc.) in one flat folder
5. **Generates** `simulation_report.md` — LLM reads the F06 and explains results in plain English

Old runs are automatically cleaned up (keeps last 5 by default, configurable via `analysis.keep_last_runs`).
