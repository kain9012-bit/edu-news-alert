param(
    [int]$MaxItems = 0,
    [string]$Model = "exaone3.5:7.8b"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m harness.run --model $Model --max-items $MaxItems
