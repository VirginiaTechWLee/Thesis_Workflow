@echo off
REM Run the first Nastran command with the Fixed_base_beam.dat file
"C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe" Fixed_base_beam.dat scratch=no
IF ERRORLEVEL 1 (
    echo The first Nastran command failed. Exiting.
    exit /b 1
)
echo Waiting for 10 seconds before proceeding to the next command...
timeout /t 10 /nobreak >nul
REM Run the second Nastran command with the randombeamx.dat file
"C:\Program Files\Siemens\Simcenter3D\NXNASTRAN\bin\nastranw.exe" randombeamx.dat
IF ERRORLEVEL 1 (
    echo The second Nastran command failed. Exiting.
    exit /b 1
)
echo Both Nastran commands completed successfully.
REM Post-process PCH to CSV
echo Running post-processor...
"C:\ProgramData\anaconda3\python.exe" Pch_TO_CSV2.py
IF ERRORLEVEL 1 (
    echo Post-processing failed. Exiting.
    exit /b 1
)
echo Post-processing completed successfully.
