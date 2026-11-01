param(
    [string]$Pak = (Join-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent) "re_chunk_000.pak"),
    [string]$PathList = "",
    [string]$Out = "$env:TEMP\ddc_extract",
    [string]$UnpackerPath = (Join-Path $env:LOCALAPPDATA "REE.Unpacker-x86")
)
$Paths = $PathList -split ";" | Where-Object { $_ }
$LogFile = "$env:TEMP\extract_log2.txt"
Set-Content $LogFile "inicio $(Get-Date -Format T)"
function Log($m) { Add-Content $LogFile $m }
try {
    $asm = [Reflection.Assembly]::LoadFrom((Join-Path $UnpackerPath "REE.Unpacker.exe"))
    [Reflection.Assembly]::LoadFrom((Join-Path $UnpackerPath "Zstandard.Net.dll")) | Out-Null
    $flags = [Reflection.BindingFlags]'Static,Public,NonPublic'
    function Invoke-Static($type, $name, [object[]]$args2) { $asm.GetType("REE.Unpacker.$type").GetMethod($name, $flags).Invoke($null, $args2) }

    $fs = [IO.File]::OpenRead($Pak)
    $br = New-Object IO.BinaryReader($fs)
    $magic = $br.ReadUInt32(); $major = $br.ReadByte(); $minor = $br.ReadByte(); $feature = $br.ReadUInt16(); $total = $br.ReadInt32(); [void]$br.ReadUInt32()
    if ($magic -ne 0x414B504B -or $major -ne 4) { throw "PAK inesperado: v$major.$minor" }
    Log "[1] lendo entradas $total"
    $entries = $br.ReadBytes($total * 48)
    Log "[2] tabela de mapas pos=$($fs.Position)"
    [void](Invoke-Static "PakChunks" "iReadMapTable" ([object[]]@($fs, [int]16)))
    Log "[2b] pos=$($fs.Position)"
    $key = $br.ReadBytes(128)
    [void](Invoke-Static "PakChunks" "iReadMapTable" ([object[]]@($fs, [int]8)))
    Log "[3] decifrando pos=$($fs.Position)"
    $entries = Invoke-Static "PakCipher" "iDecryptData" ([object[]]@(([byte[]]$entries), ([byte[]]$key)))
    Log "[4] indexando"

    Add-Type -TypeDefinition "public static class PakScan { public static int Find(byte[] e, int total, uint lower, uint upper) { for (int i = 0; i < total; i++) { int o = i * 48; uint l = System.BitConverter.ToUInt32(e, o); uint u = System.BitConverter.ToUInt32(e, o + 4); if (l == lower && u == upper) return o; } return -1; } }"
    New-Item -ItemType Directory -Force $Out | Out-Null
    foreach ($p in $Paths) {
        $lo = Invoke-Static "PakHash" "iGetStringHash" ([object[]]@($p.ToLower(), [uint32]4294967295))
        $up = Invoke-Static "PakHash" "iGetStringHash" ([object[]]@($p.ToUpper(), [uint32]4294967295))
        $o = [PakScan]::Find($entries, $total, [uint32]$lo, [uint32]$up)
        # a entrada guarda lower(4) e upper(4): lido como UInt64 = upper<<32 | lower
        if ($o -lt 0) { Log "NAO ACHADO: $p"; continue }
        $offset = [BitConverter]::ToInt64($entries, $o + 8); $comp = [BitConverter]::ToInt64($entries, $o + 16)
        $decomp = [BitConverter]::ToInt64($entries, $o + 24); $attr = [BitConverter]::ToInt64($entries, $o + 32)
        $ctype = $attr -band 15; $etype = ($attr -band 16711680) -shr 16
        Log ("{0}: off={1} comp={2} decomp={3} attr={4:X} ctype={5} etype={6}" -f $p, $offset, $comp, $decomp, $attr, $ctype, $etype)
        $fs.Position = $offset
        $data = $br.ReadBytes([int]$comp)
        if ($etype -ne 0 -and $etype -ne 5) { $data = Invoke-Static "ResourceCipher" "iDecryptResource" ([object[]]@(, ([byte[]]$data))) }
        if ($ctype -eq 1) { $data = Invoke-Static "DEFLATE" "iDecompress" ([object[]]@(, ([byte[]]$data))) }
        elseif ($ctype -eq 2) { $data = Invoke-Static "ZSTD" "iDecompress" ([object[]]@(, ([byte[]]$data))) }
        elseif ($ctype -ne 0) { Log "compressao desconhecida $ctype"; continue }
        $dest = Join-Path $Out ($p -replace "/", "\")
        New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
        [IO.File]::WriteAllBytes($dest, [byte[]]$data)
        Log "  gravado: $dest ($($data.Length) bytes)"
    }
    $fs.Close()
    Log "fim"
} catch {
    Log "ERRO: $($_.Exception.Message) $($_.Exception.InnerException.Message)"
    Write-Error "Falha na extração. Consulte $LogFile. $($_.Exception.Message)"
    exit 1
}

