@echo off

REM Run the first Nastran command with the Fixed_base_beam.dat file
"D:\Program Files\Siemens\Simcenter3D_2206\NXNASTRAN\bin\nastranw.exe" Fixed_base_beam.dat scratch=no

REM Check if the first command was successful
IF ERRORLEVEL 1 (
    echo The first Nastran command failed. Exiting.
    exit /b 1
)

REM Add a 10-second delay before the next command
echo Waiting for 10 seconds before proceeding to the next command...
timeout /t 10

REM Run the second Nastran command with the randombeamx.dat file
"D:\Program Files\Siemens\Simcenter3D_2206\NXNASTRAN\bin\nastranw.exe" randombeamx.dat

REM Optionally, check if the second command was successful
IF ERRORLEVEL 1 (
    echo The second Nastran command failed. Exiting.
    exit /b 1
)

echo Both Nastran commands completed successfully.
