param(
  [string]$Input = "dag_data.json",
  [string]$OutDir = "out/p1_batch"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

python3 phase1_scheduler.py --input $Input --algo baseline --out-prefix "$OutDir/baseline"

$seeds = @(1, 7, 42)
$budgets = @(100, 300, 800)
foreach ($s in $seeds) {
  foreach ($b in $budgets) {
    python3 phase1_scheduler.py `
      --input $Input `
      --algo ga `
      --seed $s `
      --budget-ms $b `
      --pop-size 30 `
      --generations 200 `
      --out-prefix "$OutDir/ga_s${s}_b${b}"
  }
}
Write-Host "done. summary: $OutDir/summary.csv"
