param(
  [string]$Input = "dag_data.json",
  [string]$OutDir = "out2/p2_batch"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$seeds = @(1, 7, 42)
$budgets = @(100, 300, 800)
foreach ($s in $seeds) {
  foreach ($b in $budgets) {
    python3 phase2_scheduler.py `
      --input $Input `
      --algo compare `
      --seed $s `
      --budget-ms $b `
      --out-prefix "$OutDir/cmp_s${s}_b${b}"
  }
}
Write-Host "done. summary: $OutDir/summary.csv"
