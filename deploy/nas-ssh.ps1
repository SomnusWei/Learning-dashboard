$ErrorActionPreference = 'Stop'
$plink = "$env:USERPROFILE\bin\plink.exe"
$pscp  = "$env:USERPROFILE\bin\pscp.exe"
# 从环境变量读取 NAS 连接信息（不要硬编码到仓库）
# 使用前设置：$env:NAS_HOST / $env:NAS_USER / $env:NAS_PASS / $env:NAS_HOSTKEY
$nasHost = $env:NAS_HOST
$nasUser = $env:NAS_USER
$nasPass = $env:NAS_PASS
$hostkey = $env:NAS_HOSTKEY
if (-not $nasHost -or -not $nasUser -or -not $nasPass) {
    throw "请先设置环境变量 NAS_HOST / NAS_USER / NAS_PASS（以及可选的 NAS_HOSTKEY）"
}

function Invoke-NasCmd {
    param(
        [Parameter(Mandatory=$true, ValueFromPipeline=$true)][string]$Cmd,
        [int]$TimeoutMs = 120000
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $plink
    $psi.Arguments = "-ssh -P 22 -hostkey `"$hostkey`" -l $nasUser -pw $nasPass -batch $nasHost $Cmd"
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    # ReadToEnd blocks until process exits; for long-running commands use async read instead
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $errTask = $p.StandardError.ReadToEndAsync()
    if (-not $p.WaitForExit($TimeoutMs)) {
        try { $p.Kill() } catch {}
        Write-Host "TIMEOUT after ${TimeoutMs}ms"
    }
    $out = $outTask.Result
    $err = $errTask.Result
    if ($err -and $err -notmatch 'Could not chdir to home') { Write-Host "STDERR: $err" }
    Write-Output $out
}

function Send-NasFile {
    param([Parameter(Mandatory=$true)][string]$Local, [Parameter(Mandatory=$true)][string]$Remote)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $pscp
    $psi.Arguments = "-P 22 -hostkey `"$hostkey`" -pw $nasPass -batch `"$Local`" ${nasUser}@${nasHost}:`"$Remote`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    $out = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit(300000)
    if ($err) { Write-Host "STDERR: $err" }
    Write-Output $out
}

function Send-NasDir {
    param([Parameter(Mandatory=$true)][string]$Local, [Parameter(Mandatory=$true)][string]$Remote)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $pscp
    $psi.Arguments = "-P 22 -hostkey `"$hostkey`" -pw $nasPass -batch -r `"$Local`" ${nasUser}@${nasHost}:`"$Remote`""
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $psi
    [void]$p.Start()
    $out = $p.StandardOutput.ReadToEnd()
    $err = $p.StandardError.ReadToEnd()
    $p.WaitForExit(600000)
    if ($err) { Write-Host "STDERR: $err" }
    Write-Output $out
}
