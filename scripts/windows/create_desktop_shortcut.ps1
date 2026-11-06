$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('Desktop')
if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop)) {
    throw 'Windows Desktop folder is unavailable.'
}
$target = Join-Path $PSScriptRoot '..\..\START_SL_CARBORUNDUM_PLANNING_CENTER.bat'
$target = [IO.Path]::GetFullPath($target)
if (-not (Test-Path -LiteralPath $target)) { throw "Launcher not found: $target" }
$shortcutPath = Join-Path $desktop 'SL Carborundum Planning Center.lnk'
$ws = New-Object -ComObject WScript.Shell
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = Split-Path -Parent $target
$shortcut.Description = 'SL Carborundum Planning Center — starts the installed interface'
$icon = Join-Path $shortcut.WorkingDirectory 'assets\sl_carborundum.ico'
$shortcut.IconLocation = "$icon,0"
$shortcut.Save()
Write-Output $shortcutPath
