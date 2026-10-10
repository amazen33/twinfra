#Requires -Version 7.4
# SPDX-License-Identifier: MIT
# Owner-only entry point. Codex/CI import Twinfra.psm1 against fixtures, never this file.
[CmdletBinding()]
param([switch]$Plan,[string]$Region='cairo-1',[int]$Cpu=8,[int]$MemoryGB=20,[int]$DiskGB=100,
      [string]$IpAddress='10.50.0.10',[string]$PodCidr='10.110.0.0/16',
      [string]$ServiceCidr='10.111.0.0/16',[string]$Root='E:\Twinfra',
      [string]$SshPublicKeyFile,[string]$SeedDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'Twinfra.psm1') -Force
$admin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Run an Administrator PowerShell session. No changes made.' }
if (-not (Get-Module -ListAvailable Hyper-V) -or (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All).State -ne 'Enabled') {
    throw 'Enable Hyper-V and its PowerShell management tools, then reboot. No changes made.'
}
Import-Module Hyper-V
$addresses=@(Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object {
    @{InterfaceAlias=$_.InterfaceAlias;Address="$($_.IPAddress)/$($_.PrefixLength)"}
})
$switches=@(Get-VMSwitch | ForEach-Object {
    $switch=$_
    @{Name=$switch.Name;SwitchType=[string]$switch.SwitchType;
      Prefixes=@($addresses | Where-Object InterfaceAlias -eq "vEthernet ($($switch.Name))" | ForEach-Object Address)}
})
$vms=@(Get-VM | ForEach-Object {
    $vm=$_; $adapters=@(Get-VMNetworkAdapter -VM $vm); $stamp=''; $cidrs=@()
    try { $note=$vm.Notes | ConvertFrom-Json -AsHashtable; $stamp=$note.Stamp
          $settings=$stamp | ConvertFrom-Json -AsHashtable; $cidrs=@($settings.PodCidr,$settings.ServiceCidr) } catch { $note=$null }
    $disks=@(Get-VMHardDiskDrive -VM $vm); $dvds=@(Get-VMDvdDrive -VM $vm)
    $disk=if($disks.Count -eq 1){$disks[0].Path}else{''}
    $seed=if($dvds.Count -eq 1){$dvds[0].Path}else{''}
    $verified=$false
    if ($note -and $disk -and $seed -and (Test-Path -LiteralPath $seed) -and (Test-Path -LiteralPath $disk)) {
        $verified=(Get-FileHash -LiteralPath $seed).Hash -eq $note.SeedSHA256
        $vhd=Get-VHD -Path $disk
        $verified=$verified -and $vhd.VhdFormat -eq 'VHDX' -and $vhd.VhdType -eq 'Dynamic'
    }
    @{Name=$vm.Name;Stamp=$stamp;FilesVerified=$verified;Generation=$vm.Generation;
      Cpu=(Get-VMProcessor -VM $vm).Count;MemoryGB=$vm.MemoryStartup/1GB;
      DynamicMemory=(Get-VMMemory -VM $vm).DynamicMemoryEnabled;Nested=(Get-VMProcessor -VM $vm).ExposeVirtualizationExtensions;
      Switch=if($adapters.Count -eq 1){$adapters[0].SwitchName}else{''};Disk=$disk;Seed=$seed;
      DiskGB=if($disk -and (Test-Path -LiteralPath $disk)){(Get-VHD -Path $disk).Size/1GB}else{0};
      Ips=@($adapters | ForEach-Object IPAddresses)+@(if($note){$settings.IpAddress});ClusterCidrs=$cidrs}
})
$os=Get-CimInstance Win32_OperatingSystem
$inventory=@{Admin=$admin;HyperV=$true;LogicalProcessors=(Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors;
    FreeMemoryGB=$os.FreePhysicalMemory*1KB/1GB;FreeDiskGB=(Get-PSDrive E).Free/1GB;
    Addresses=$addresses;Switches=$switches;Vms=$vms;
    Nats=@(Get-NetNat | ForEach-Object {@{Name=$_.Name;Prefix=$_.InternalIPInterfaceAddressPrefix}});
    Routes=@(Get-NetRoute -AddressFamily IPv4 | ForEach-Object {@{Prefix=$_.DestinationPrefix;InterfaceAlias=$_.InterfaceAlias;NextHop=$_.NextHop}});
    ExistingPaths=@(if(Test-Path -LiteralPath $Root){Get-ChildItem -LiteralPath $Root -Directory | ForEach-Object FullName})}
$image=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'ubuntu-image.lock.json') -Raw | ConvertFrom-Json -AsHashtable
$p=New-TwinfraPlan -Inventory $inventory -Image $image -Region $Region -Cpu $Cpu -MemoryGB $MemoryGB -DiskGB $DiskGB -IpAddress $IpAddress -PodCidr $PodCidr -ServiceCidr $ServiceCidr -Root $Root
Format-TwinfraPlan $p
if ($Plan -or $p.NoChanges) { return }
# All host collision/resource/ownership checks precede the first write/download.
if (-not $SshPublicKeyFile -or -not (Test-Path -LiteralPath $SshPublicKeyFile)) { throw 'Supply an operator SSH PUBLIC key file (never a private key)' }
$key=(Get-Content -LiteralPath $SshPublicKeyFile -Raw).Trim()
if ($key -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256) [A-Za-z0-9+/=]+(?: [^\r\n]+)?$') { throw 'Invalid SSH public key' }
if (-not $SeedDirectory) { $SeedDirectory=Join-Path (Split-Path $PSScriptRoot -Parent) "environments\dev\$Region\seed" }
foreach ($file in @('user-data','meta-data','network-config')) {
    if (-not (Test-Path -LiteralPath (Join-Path $SeedDirectory $file))) { throw "Missing generated NoCloud $file; run tools/platform_dev.py render first" }
}
$seedText=Get-Content -LiteralPath (Join-Path $SeedDirectory 'user-data') -Raw
if ($seedText -notmatch [regex]::Escape("NODE_IP=$IpAddress") -or $seedText -notmatch [regex]::Escape("CLUSTER_NAME=twinfra-dev-$Region") -or $seedText -notmatch [regex]::Escape("POD_CIDR=$PodCidr") -or $seedText -notmatch [regex]::Escape("SERVICE_CIDR=$ServiceCidr") -or
    (Get-Content -LiteralPath (Join-Path $SeedDirectory 'network-config') -Raw) -notmatch [regex]::Escape("$IpAddress/24")) {
    throw 'Parameters do not match the generated seed; generate a matching region overlay before any writes'
}
$storageAncestor=if(Test-Path -LiteralPath $Root){$Root}else{Split-Path $Root -Parent}
if ((Get-Item -LiteralPath $storageAncestor).Attributes -band ([IO.FileAttributes]::Compressed -bor [IO.FileAttributes]::Encrypted -bor [IO.FileAttributes]::ReparsePoint)) {
    throw 'VHDX parent must be uncompressed, unencrypted and not a reparse point'
}
$python=Get-Command python -ErrorAction Stop
$cache=Join-Path $Root 'image-cache'; New-Item -ItemType Directory -Path $cache -Force | Out-Null
$download=Join-Path $cache $image.fileName
if (-not (Test-Path -LiteralPath $download)) { Invoke-WebRequest -Uri $image.imageUrl -OutFile $download }
$sums=Invoke-WebRequest -Uri $image.checksumsUrl
$sumsText=if($sums.Content -is [byte[]]){[Text.Encoding]::UTF8.GetString($sums.Content)}else{[string]$sums.Content}
Assert-TwinfraImage -File $download -Lock $image -Checksums $sumsText
# Convert the verified generic image without booting it or mounting host disks.
# Python is already a repository CLI prerequisite; no third-party converter is installed.
$dir=Split-Path $p.Settings.Disk -Parent
New-Item -ItemType Directory -Path $dir | Out-Null
$source=Join-Path $dir 'canonical-base.vhd'
& $python.Source (Join-Path $PSScriptRoot 'qcow2_to_vhd.py') $download $source
if ($LASTEXITCODE) { throw 'Verified QCOW2 conversion failed; no network or VM changes made' }
Convert-VHD -Path $source -DestinationPath $p.Settings.Disk -VHDType Dynamic
# Only this verified script-created intermediate is removed after successful conversion.
Remove-Item -LiteralPath $source
Resize-VHD -Path $p.Settings.Disk -SizeBytes ($DiskGB*1GB)
# Windows IMAPI2 produces CIDATA without an external ISO tool/package.
$stage=Join-Path $dir 'seed'; New-Item -ItemType Directory -Path $stage | Out-Null
foreach ($file in @('user-data','meta-data','network-config')) {
    $raw=Get-Content -LiteralPath (Join-Path $SeedDirectory $file) -Raw
    if ($file -eq 'user-data') { $raw=$raw.Replace('@@SSH_PUBLIC_KEY@@',$key) }
    [IO.File]::WriteAllText((Join-Path $stage $file),$raw,[Text.UTF8Encoding]::new($false))
}
$fsi=New-Object -ComObject IMAPI2FS.MsftFileSystemImage
$fsi.FileSystemsToCreate=3; $fsi.VolumeName='CIDATA'; $fsi.Root.AddTree($stage,$false)
$iso=$fsi.CreateResultImage()
Add-Type -TypeDefinition @'
using System; using System.IO; using System.Runtime.InteropServices; using System.Runtime.InteropServices.ComTypes;
public static class TwinfraIso { public static void Save(object stream, string file) {
 var s=(IStream)stream; var b=new byte[65536]; var n=Marshal.AllocHGlobal(4);
 try { using(var f=new FileStream(file,FileMode.CreateNew)) { for(;;) { s.Read(b,b.Length,n); int c=Marshal.ReadInt32(n); if(c==0)break; f.Write(b,0,c); } } }
 finally { Marshal.FreeHGlobal(n); }
} }
'@
[TwinfraIso]::Save($iso.ImageStream,$p.Settings.Seed)
if (-not $p.OwnedNetwork) {
    New-VMSwitch -Name twinfra-nat -SwitchType Internal | Out-Null
    New-NetIPAddress -InterfaceAlias 'vEthernet (twinfra-nat)' -IPAddress 10.50.0.1 -PrefixLength 24 | Out-Null
    New-NetNat -Name twinfra-nat -InternalIPInterfaceAddressPrefix 10.50.0.0/24 | Out-Null
}
$vm=New-VM -Name $p.Settings.Name -Generation 2 -MemoryStartupBytes ($MemoryGB*1GB) -VHDPath $p.Settings.Disk -Path $dir -SwitchName twinfra-nat
Set-VMProcessor -VM $vm -Count $Cpu -ExposeVirtualizationExtensions $true
Set-VMMemory -VM $vm -DynamicMemoryEnabled $false
Add-VMDvdDrive -VM $vm -Path $p.Settings.Seed
Set-VMFirmware -VM $vm -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority -FirstBootDevice (Get-VMHardDiskDrive -VM $vm)
$note=@{Stamp=$p.Stamp;SeedSHA256=(Get-FileHash -LiteralPath $p.Settings.Seed).Hash} | ConvertTo-Json -Compress
Set-VM -VM $vm -Notes $note -AutomaticStartAction Nothing -AutomaticStopAction ShutDown
Write-Output "Created $($vm.Name), left Off. Owner reviews seed and starts it explicitly. No other VM, switch or WSL distro touched."
