# Machine snapshot for autotest runs (research/01). Run via:
#   powershell -NoProfile -Command "Get-Content -Raw '<path>' | Invoke-Expression"
# Prints: time, free/total physical RAM, top 10 processes by working set, and the watched processes with CPU time.
$os = Get-CimInstance Win32_OperatingSystem
"time: " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
"RAM free/total: {0:N1} / {1:N1} GB" -f ($os.FreePhysicalMemory / 1MB), ($os.TotalVisibleMemorySize / 1MB)
"-- top 10 processes by working set (name pid MB) --"
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 | ForEach-Object { "{0} {1} {2:N0}" -f $_.ProcessName, $_.Id, ($_.WorkingSet64 / 1MB) }
"-- watched processes (name pid MB cpu_s) --"
$found = 0
foreach ($n in @('UnrealEditor', 'zenserver', 'ShaderCompileWorker', 'MsMpEng')) {
  $ps = @(Get-Process -Name $n -ErrorAction SilentlyContinue)
  foreach ($p in $ps) {
    $found++
    $cpu = 0; try { $cpu = $p.TotalProcessorTime.TotalSeconds } catch { $cpu = -1 }
    "{0} {1} {2:N0} {3:N1}" -f $p.ProcessName, $p.Id, ($p.WorkingSet64 / 1MB), $cpu
  }
  if ($ps.Count -eq 0) { "$n not running" }
}
