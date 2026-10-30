param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\evidence\r10-live')
)
$ErrorActionPreference = 'Stop'
$expectedExe = 'F:\SteamLibrary\steamapps\common\Ready Or Not\ReadyOrNot\Binaries\Win64\ReadyOrNotSteam-Win64-Shipping.exe'
$live = @(Get-CimInstance Win32_Process -Filter "Name='ReadyOrNotSteam-Win64-Shipping.exe'" |
    Where-Object { $_.ThreadCount -gt 0 -and $_.ExecutablePath -eq $expectedExe })
if ($live.Count -ne 1) { throw "Expected one live game process at the verified path; found $($live.Count). No snapshot created." }
if (-not ('ReactiveSuspectsHangReadOnly' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
public static class ReactiveSuspectsHangReadOnly {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr handle);
    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    [DllImport("dbghelp.dll", SetLastError=true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool MiniDumpWriteDump(IntPtr process, uint pid,
        SafeFileHandle file, uint type, IntPtr exception, IntPtr streams, IntPtr callback);
}
'@
}
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$dumpPath = Join-Path $OutputDirectory ("hang-$($live[0].ProcessId)-" + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.dmp')
# QUERY_INFORMATION (0x400) | VM_READ (0x10), MiniDumpNormal (0).
$handle = [ReactiveSuspectsHangReadOnly]::OpenProcess(0x410, $false, [uint32]$live[0].ProcessId)
if ($handle -eq [IntPtr]::Zero) { throw "OpenProcess failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())" }
try {
    $file = [IO.File]::Open($dumpPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        $ok = [ReactiveSuspectsHangReadOnly]::MiniDumpWriteDump($handle, [uint32]$live[0].ProcessId,
            $file.SafeFileHandle, 0, [IntPtr]::Zero, [IntPtr]::Zero, [IntPtr]::Zero)
        if (-not $ok) { throw "MiniDumpWriteDump failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error()); incomplete output: $dumpPath" }
    } finally { $file.Dispose() }
} finally { [void][ReactiveSuspectsHangReadOnly]::CloseHandle($handle) }
Get-Item -LiteralPath $dumpPath | Select-Object FullName, Length, LastWriteTime
