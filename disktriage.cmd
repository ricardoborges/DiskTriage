@echo off
rem Atalho: roda o disktriage a partir desta pasta, sem precisar instalar.
pushd "%~dp0"
python -m pydisktriage %*
popd
