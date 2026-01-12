# HEEDS Study Configuration - SOLUTION

## Status: ✅ WORKING - 576 designs completed successfully

---

## THE FIX (ONE LINE)

```powershell
Copy-Item "$repo\Misc\Bush.blk" "C:\Users\waynelee\Documents\Bush.blk" -Force
```

**Use `Misc/Bush.blk` instead of `baseline/Bush.blk`**

---

## Why This Worked

| Bush.blk Source | Format | Result |
|-----------------|--------|--------|
| `baseline/Bush.blk` | Tab-separated, NO comments | ❌ FAILED - charCol positions wrong |
| `Misc/Bush.blk` | Fixed-width WITH comment lines | ✅ WORKED - charCol positions match |

The `.heeds` file has hardcoded character positions:
- K4: `charCol="48"`
- K5: `charCol="56"`  
- K6: `charCol="64"`

These positions ONLY align correctly with the Femap-exported format in `Misc/Bush.blk`:

```
$ Femap Property 1 : Driving Cbush_1
PBUSH          1       K1000000.1000000.1000000.    1.+4    1.+4    1.+4
                                                    ^48     ^56     ^64
```

The `baseline/Bush.blk` has different spacing, so HEEDS wrote values in the wrong positions, causing truncation and Nastran errors.

---

## Complete Working Setup

### 1. Fix paths in .heeds file (one-time)
```powershell
$content = Get-Content "Square_Beam_scenario_short_revexample.heeds" -Raw
$content = $content -replace "m33002", "waynelee"
$content = $content -replace "D:\\HEEDS", "C:\\HEEDS"
$content = $content -replace "D:/HEEDS", "C:/HEEDS"
$content | Out-File "thesis_study_v2.heeds" -Encoding UTF8
```

### 2. Copy required files to Documents
```powershell
$docs = "C:\Users\waynelee\Documents"
Copy-Item "$repo\Misc\Bush.blk" "$docs\Bush.blk" -Force                    # THE KEY FIX
Copy-Item "$repo\templates\Fixed_base_beam.dat" "$docs\" -Force
Copy-Item "$repo\FBM_TO_DBALL.bat" "$docs\" -Force
Copy-Item "$repo\templates\RandomBeamX.dat" "$docs\" -Force
Copy-Item "$repo\templates\Recoveries.blk" "$docs\" -Force
Copy-Item "$repo\Scripts\Pch_TO_CSV2.py" "$docs\" -Force
Copy-Item "$repo\baseline\acceleration_results.csv" "$docs\acceleration_results_baseline.csv" -Force
Copy-Item "$repo\baseline\displacement_results.csv" "$docs\displacement_results_baseline.csv" -Force
```

### 3. Run the study
```powershell
& "C:\HEEDS\MDO\Ver2410\Win64\HEEDSMDO.exe" `
    -b `
    -script "$repo\run_study_v2.py" `
    -project "C:\Users\waynelee\Documents\thesis_study_v2.heeds"
```

### 4. Monitor progress
```powershell
(dir "C:\Users\waynelee\Documents\thesis_study_v2_Study_1\HEEDS_0\Design*" | Measure-Object).Count
```

---

## What Failed (for reference)

### Attempt 1: Comma-delimited Bush.blk
- Changed to `PBUSH,1,K,1.+6,1.+6,1.+6,1.+12,1.+12,1.+12`
- Changed .heeds to `mode="delimited"`
- **Result:** HEEDS wrote level INDICES (1-9) instead of VALUES (1.+4 to 1.+14)

### Attempt 2: baseline/Bush.blk (tab-separated, no comments)
- Used `PBUSH   1       K       1.+6    1.+6    1.+6    1.+12   1.+12   1.+12`
- **Result:** Values written at wrong character positions, truncated
- **Error:** `FATAL ERROR - FORMAT ERROR ON BULK DATA ENTRY PBUSH`

### Attempt 3: Misc/Bush.blk (Femap format with comments) ✅
- Used original Femap export format
- **Result:** SUCCESS - all 576 designs completed

---

## Files Reference

| File | Location | Purpose |
|------|----------|---------|
| `Bush.blk` | `Misc/Bush.blk` | **MUST use this one** - Femap format with comments |
| `run_study_v2.py` | repo root | Python script to run HEEDS via batch mode |
| `thesis_study_v2.heeds` | Documents | .heeds file with corrected paths |
| `FBM_TO_DBALL.bat` | repo root | Runs Nastran (ensure correct path inside) |

---

## Discrete Variable Levels

The study uses 11 stiffness levels defined in `Set_2`:
```
Level 1:  1.+4   (10,000)      - loosest
Level 2:  1.+5   (100,000)
Level 3:  1.+6   (1,000,000)
Level 4:  1.+7   
Level 5:  1.+8   
Level 6:  1.+9   
Level 7:  1.+10  
Level 8:  1.+11  
Level 9:  1.+12  
Level 10: 1.+13  
Level 11: 1.+14  (100 trillion) - tightest/baseline
```

---

## Version Info
- HEEDS MDO: 2410.0 build 241030
- License: siemensaoe.software.vt.edu (expires 02-feb-2026)
- Nastran: Siemens Simcenter NX Nastran
- Date Verified: January 9, 2026
