param(
    [int]$MaxItems = 0,
    [ValidateSet("gemini", "ollama")]
    [string]$Provider = "gemini",
    [string]$Model = "gemini-2.5-flash-lite"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

python -m harness.run --provider $Provider --model $Model --max-items $MaxItems
