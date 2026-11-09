#!/bin/sh
# Builds the replay reader into ../lecteur (.NET 10 SDK required)
cd "$(dirname "$0")" && dotnet publish LecteurCoffres/LecteurCoffres.csproj -c Release -p:DebugType=none -p:UseAppHost=false -o ../lecteur
