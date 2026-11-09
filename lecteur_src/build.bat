@echo off
rem Compile le lecteur de replays dans ..\lecteur (SDK .NET 10 requis : winget install Microsoft.DotNet.SDK.10)
rem Builds the replay reader into ..\lecteur (.NET 10 SDK required: winget install Microsoft.DotNet.SDK.10)
cd /d "%~dp0"
dotnet publish LecteurCoffres\LecteurCoffres.csproj -c Release -p:DebugType=none -p:UseAppHost=false -o ..\lecteur
if errorlevel 1 (echo. & echo Echec de la compilation / Build failed & pause & exit /b 1)
echo. & echo OK : ..\lecteur
