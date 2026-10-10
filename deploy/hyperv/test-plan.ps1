# SPDX-License-Identifier: MIT
# OFFLINE ONLY: pure module import, explicit inventory fixtures. Never dot-source provisioner.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'Twinfra.psm1') -Force
$image=Get-Content (Join-Path $PSScriptRoot 'ubuntu-image.lock.json') -Raw | ConvertFrom-Json -AsHashtable
$script:passed=0
function Inventory {
    return @{Admin=$true;HyperV=$true;LogicalProcessors=16;FreeMemoryGB=24;FreeDiskGB=113;
        Switches=@();Nats=@();Addresses=@();Routes=@();Vms=@();ExistingPaths=@()}
}
function Owned($i) {
    $i.Switches=@(@{Name='twinfra-nat';SwitchType='Internal';Prefixes=@('10.50.0.1/24')})
    $i.Nats=@(@{Name='twinfra-nat';Prefix='10.50.0.0/24'})
    $i.Addresses=@(@{InterfaceAlias='vEthernet (twinfra-nat)';Address='10.50.0.1/24'})
    $i.Routes=@(@{InterfaceAlias='vEthernet (twinfra-nat)';Prefix='10.50.0.0/24';NextHop='0.0.0.0'},
        @{InterfaceAlias='vEthernet (twinfra-nat)';Prefix='10.50.0.1/32';NextHop='0.0.0.0'})
}
function Assert($condition,$message) { if(-not $condition){throw $message} }
function Check($name,[scriptblock]$body) { & $body; $script:passed++; Write-Output "PASS: $name" }
function Refused($i,$options=@{}) {
    $failed=$false
    try { New-TwinfraPlan -Inventory $i -Image $image @options | Out-Null } catch {$failed=$true}
    Assert $failed 'Unsafe plan was accepted'
}
Check 'default route and the five exclusions' {
    $i=Inventory
    $i.Routes=@('0.0.0.0/0','::/0','127.0.0.1/32','169.254.10.0/24','224.0.0.0/4','255.255.255.255/32' | ForEach-Object {@{Prefix=$_;InterfaceAlias='fixture';NextHop='0.0.0.0'}})
    $p=New-TwinfraPlan -Inventory $i -Image $image
    Assert (-not $p.NoChanges) 'New VM missing actions'
    Assert (-not (Test-ExcludedRoute '10.0.0.0/8')) 'Unapproved exclusion'
}
Check 'exact owned rerun makes zero changes' {
    $i=Inventory;Owned $i;$p=New-TwinfraPlan -Inventory $i -Image $image
    $i.Vms=@(@{Name=$p.Settings.Name;Stamp=$p.Stamp;FilesVerified=$true;Generation=2;Cpu=8;MemoryGB=20;DynamicMemory=$false;Nested=$true;Switch='twinfra-nat';Disk=$p.Settings.Disk;Seed=$p.Settings.Seed;DiskGB=100;Ips=@('10.50.0.10');ClusterCidrs=@('10.110.0.0/16','10.111.0.0/16')})
    $i.FreeMemoryGB=1;$i.FreeDiskGB=1
    $rerun=New-TwinfraPlan -Inventory $i -Image $image
    Assert ($rerun.NoChanges -and $rerun.Actions.Count -eq 0) 'Rerun mutated plan'
}
Check 'owned name with different prefix is refused' {
    $i=Inventory;Owned $i;$i.Nats[0].Prefix='10.51.0.0/24';Refused $i
    $i=Inventory;Owned $i;$i.Addresses+=@{InterfaceAlias='vEthernet (twinfra-nat)';Address='10.50.0.2/24'};Refused $i
}
Check 'second region shares owned network and next free address' {
    $i=Inventory;Owned $i
    $i.Vms=@(@{Name='twinfra-dev-cairo-1';Ips=@('10.50.0.10');ClusterCidrs=@('10.110.0.0/16','10.111.0.0/16')})
    $p=New-TwinfraPlan -Inventory $i -Image $image -Region cairo-2 -Cpu 4 -MemoryGB 12 -IpAddress 10.50.0.11 -PodCidr 10.120.0.0/16 -ServiceCidr 10.121.0.0/16
    Assert ($p.OwnedNetwork -and $p.Settings.Name -eq 'twinfra-dev-cairo-2') 'Second-region plan differs'
    Refused $i @{Region='cairo-2';IpAddress='10.50.0.10';PodCidr='10.120.0.0/16';ServiceCidr='10.121.0.0/16'}
}
Check 'protected networks and intersecting planned ranges refused' {
    foreach($range in @('10.20.0.0/16','192.168.1.0/24','10.50.0.0/16','10.111.0.0/17')) {Refused (Inventory) @{PodCidr=$range}}
}
Check 'duplicate planned entries refused' { Refused (Inventory) @{PodCidr='10.111.0.0/16'} }
Check 'specific route host prefix NAT and switch collisions refused' {
    $i=Inventory;$i.Routes=@(@{Prefix='10.110.0.0/24';InterfaceAlias='foreign';NextHop='192.168.1.1'});Refused $i
    $i=Inventory;$i.Addresses=@(@{Address='10.50.0.10/32';InterfaceAlias='foreign'});Refused $i
    $i=Inventory;$i.Nats=@(@{Name='foreign';Prefix='10.111.0.0/16'});Refused $i
    $i=Inventory;$i.Switches=@(@{Name='foreign';SwitchType='Internal';Prefixes=@('10.50.0.0/24')});Refused $i
}
Check 'admin Hyper-V RAM disk and address guards' {
    foreach($key in @('Admin','HyperV')) {$i=Inventory;$i[$key]=$false;Refused $i}
    $i=Inventory;$i.FreeMemoryGB=23;Refused $i
    $i=Inventory;$i.FreeDiskGB=109;Refused $i
    foreach($ip in @('10.50.0.0','10.50.0.1','10.50.0.255','10.51.0.10')) {Refused (Inventory) @{IpAddress=$ip}}
}
Check 'WO-29 defaults and resource boundary' {
    $i=Inventory;$i.FreeDiskGB=110
    $p=New-TwinfraPlan -Inventory $i -Image $image
    Assert ($p.Settings.MemoryGB -eq 20) 'Memory default must be 20'
    Assert ((Format-TwinfraPlan $p) -match 'Free RAM measured: 24 GiB') 'Measured free RAM missing'
    $i.FreeDiskGB=109;Refused $i
    $i=Inventory;$i.FreeMemoryGB=23;Refused $i
}
Check 'PowerShell 7.4 required in both entry and pure module' {
    foreach($file in @('New-TwinfraDev.ps1','Twinfra.psm1')) {
        Assert ((Get-Content (Join-Path $PSScriptRoot $file) -First 1) -eq '#Requires -Version 7.4') 'Missing PowerShell requirement'
    }
}
Check 'checksum mismatch refuses before provisioning' {
    $file=[IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllBytes($file,[byte[]](1,2,3))
        $lock=@{fileName='fixture.img';sizeBytes=3;sha256=(Get-FileHash $file).Hash.ToLowerInvariant()}
        Assert-TwinfraImage -File $file -Lock $lock -Checksums "$($lock.sha256) *fixture.img"
        $failed=$false
        try {Assert-TwinfraImage -File $file -Lock $lock -Checksums 'invalid'} catch {$failed=$true}
        Assert $failed 'Checksum failure accepted'
        try {Assert-TwinfraImage -File $file -Lock $lock -Checksums 'invalid'} catch {Assert ($_.Exception.Message -match ('delete '+[regex]::Escape($file)+' and rerun')) 'Missing manual cache recovery message'}
        Assert (Test-Path -LiteralPath $file) 'Bad cache automatically deleted'
    } finally {Remove-Item -LiteralPath $file}
}
Check 'entry script parses, plan branch precedes every mutation' {
    $entry=Join-Path $PSScriptRoot 'New-TwinfraDev.ps1'
    $tokens=$null;$errors=$null
    [Management.Automation.Language.Parser]::ParseFile($entry,[ref]$tokens,[ref]$errors) | Out-Null
    Assert ($errors.Count -eq 0) ($errors | Out-String)
    $raw=Get-Content $entry -Raw
    Assert ($raw.IndexOf('if ($Plan -or $p.NoChanges)') -lt $raw.IndexOf('New-Item -ItemType')) 'Writes before -Plan return'
    Assert ($raw -notmatch 'Start-VM|Remove-VM|Remove-VMSwitch|wsl.exe|Set-NetNat') 'Foreign/live operations in provisioner'
}
Write-Output "OFFLINE FIXTURE -Plan output ($passed checks passed; no host inventory reads):"
Format-TwinfraPlan (New-TwinfraPlan -Inventory (Inventory) -Image $image)
