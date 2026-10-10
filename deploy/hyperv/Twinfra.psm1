#Requires -Version 7.4
# SPDX-License-Identifier: MIT
# Pure planning and an explicit mutation boundary. Importing this module reads no host state.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-IPv4Range([string]$Cidr) {
    $parts = $Cidr.Split('/')
    $ip = [System.Net.IPAddress]::Parse($parts[0])
    if ($ip.AddressFamily -ne 'InterNetwork') { throw "Not IPv4: $Cidr" }
    $prefix = if ($parts.Count -eq 2) { [int]$parts[1] } else { 32 }
    if ($prefix -lt 0 -or $prefix -gt 32) { throw "Invalid prefix: $Cidr" }
    $bytes = $ip.GetAddressBytes()
    [uint64]$number = [uint64]$bytes[0]*16777216 + [uint64]$bytes[1]*65536 + [uint64]$bytes[2]*256 + $bytes[3]
    [uint64]$size = [math]::Pow(2,32-$prefix)
    [uint64]$start = [math]::Floor($number/$size)*$size
    return @{ Start=$start; End=$start+$size-1; Prefix=$prefix; Address=$number }
}
function Test-Overlap([string]$Left, [string]$Right) {
    $a=Get-IPv4Range $Left; $b=Get-IPv4Range $Right
    return $a.Start -le $b.End -and $b.Start -le $a.End
}
function Test-ExcludedRoute([string]$Cidr) {
    if ($Cidr -eq '::/0') { return $true }
    $r=Get-IPv4Range $Cidr
    foreach ($special in @('0.0.0.0/0','127.0.0.0/8','169.254.0.0/16','224.0.0.0/4','255.255.255.255/32')) {
        if ($special -eq '0.0.0.0/0') { if ($Cidr -eq $special) { return $true }; continue }
        $s=Get-IPv4Range $special
        if ($r.Start -ge $s.Start -and $r.End -le $s.End) { return $true }
    }
    return $false
}
function New-TwinfraPlan {
    param([Parameter(Mandatory)][hashtable]$Inventory,
          [Parameter(Mandatory)][hashtable]$Image,
          [string]$Region='cairo-1',[int]$Cpu=8,[int]$MemoryGB=20,[int]$DiskGB=100,
          [string]$IpAddress='10.50.0.10',[string]$PodCidr='10.110.0.0/16',
          [string]$ServiceCidr='10.111.0.0/16',[string]$Root='E:\Twinfra',
          [string]$Environment='dev')
    if ($Environment -ne 'dev' -or $Region -notmatch '^cairo-[12]$') { throw 'Only the approved dev regions are provisionable' }
    if ($Cpu -lt 1 -or $MemoryGB -lt 4 -or $DiskGB -lt 32) { throw 'Invalid VM sizing' }
    if (-not $Inventory.Admin) { throw 'Administrator PowerShell is required; no changes made' }
    if (-not $Inventory.HyperV) { throw 'Hyper-V and its PowerShell management module must be enabled; no changes made' }
    if ($Cpu -gt $Inventory.LogicalProcessors) { throw 'Insufficient logical processors' }
    if ($Root -notmatch '^E:\\Twinfra(?:\\[A-Za-z0-9_-]+)*$') { throw 'VM storage must be an explicit directory on E:' }
    if ($Image.imageUrl -notmatch '^https://cloud-images\.ubuntu\.com/noble/[0-9]{8}/noble-server-cloudimg-amd64\.img$' -or
        $Image.sha256 -notmatch '^[a-f0-9]{64}$' -or $Image.sizeBytes -le 0) { throw 'Invalid Canonical image lock' }
    $name="twinfra-$Environment-$Region"
    $switch=@($Inventory.Switches | Where-Object Name -eq 'twinfra-nat')
    $nat=@($Inventory.Nats | Where-Object Name -eq 'twinfra-nat')
    $adapter=@($Inventory.Addresses | Where-Object InterfaceAlias -eq 'vEthernet (twinfra-nat)')
    $owned=$switch.Count -eq 1 -and $switch[0].SwitchType -eq 'Internal' -and
           $nat.Count -eq 1 -and $nat[0].Prefix -eq '10.50.0.0/24' -and
           $adapter.Count -eq 1 -and $adapter[0].Address -eq '10.50.0.1/24'
    if (($switch.Count+$nat.Count+$adapter.Count) -gt 0 -and -not $owned) {
        throw 'Owned name has foreign or incomplete configuration (switch/NAT/gateway); no changes made'
    }
    $vm=@($Inventory.Vms | Where-Object Name -eq $name)
    $dir="$Root\$name"
    $settings=[ordered]@{ Name=$name; Region=$Region; Cpu=$Cpu; MemoryGB=$MemoryGB; DiskGB=$DiskGB;
        IpAddress=$IpAddress; PodCidr=$PodCidr; ServiceCidr=$ServiceCidr; Environment=$Environment;
        Disk="$dir\$name.vhdx"; Seed="$dir\seed.iso"; ImageHash=$Image.sha256 }
    $stamp=$settings | ConvertTo-Json -Compress
    if ($vm.Count -gt 1) { throw 'Duplicate VM ownership' }
    if ($vm.Count -eq 1) {
        if (-not $owned -or $vm[0].Stamp -ne $stamp -or -not $vm[0].FilesVerified -or
            $vm[0].Generation -ne 2 -or $vm[0].Cpu -ne $Cpu -or $vm[0].MemoryGB -ne $MemoryGB -or
            $vm[0].DynamicMemory -or -not $vm[0].Nested -or $vm[0].Switch -ne 'twinfra-nat' -or
            $vm[0].Disk -ne $settings.Disk -or $vm[0].Seed -ne $settings.Seed -or $vm[0].DiskGB -ne $DiskGB) {
            throw 'Owned VM name/configuration/files differ; refusing adoption or modification'
        }
    } elseif ($Inventory.ExistingPaths -contains $dir) { throw 'Foreign or partial VM directory; refusing overwrite' }
    $planned=@('10.50.0.0/24',$PodCidr,$ServiceCidr)
    for ($i=0;$i -lt $planned.Count;$i++) {
        $range=Get-IPv4Range $planned[$i]
        if ($range.Address -ne $range.Start) { throw 'Planned CIDR must be canonical' }
        for ($j=$i+1;$j -lt $planned.Count;$j++) {
            if (Test-Overlap $planned[$i] $planned[$j]) { throw "Planned ranges overlap: $($planned[$i]) / $($planned[$j])" }
        }
    }
    $ip=Get-IPv4Range "$IpAddress/32"; $subnet=Get-IPv4Range '10.50.0.0/24'
    if ($ip.Start -le $subnet.Start+1 -or $ip.Start -ge $subnet.End) { throw 'VM IP must be a usable address on twinfra-nat, excluding .0/.1/.255' }
    # The VM address is intentionally contained in its switch; it must never intersect pod/service space.
    foreach ($range in @($PodCidr,$ServiceCidr)) { if (Test-Overlap "$IpAddress/32" $range) { throw 'VM IP overlaps cluster CIDRs' } }
    foreach ($protected in @('10.20.0.0/24','192.168.1.0/24','10.255.255.254/32')) {
        foreach ($range in $planned) { if (Test-Overlap $range $protected) { throw "Protected network overlap: $range / $protected" } }
    }
    $existing=@()
    foreach ($a in $Inventory.Addresses) {
        if ($owned -and $a.InterfaceAlias -eq 'vEthernet (twinfra-nat)') { continue }
        $existing+=@{Prefix=$a.Address; Source='host address'}
    }
    foreach ($r in $Inventory.Routes) {
        if (Test-ExcludedRoute $r.Prefix) { continue }
        if ($owned -and $r.InterfaceAlias -eq 'vEthernet (twinfra-nat)' -and $r.NextHop -eq '0.0.0.0' -and
            $r.Prefix -in @('10.50.0.0/24','10.50.0.1/32')) { continue }
        $existing+=@{Prefix=$r.Prefix; Source='specific route'}
    }
    foreach ($n in $Inventory.Nats) { if (-not ($owned -and $n.Name -eq 'twinfra-nat')) { $existing+=@{Prefix=$n.Prefix;Source='NAT'} } }
    foreach ($s in $Inventory.Switches) {
        if (-not ($owned -and $s.Name -eq 'twinfra-nat')) { foreach ($p in $s.Prefixes) { $existing+=@{Prefix=$p;Source='switch'} } }
    }
    foreach ($entry in $existing) {
        if (Test-ExcludedRoute $entry.Prefix) { continue }
        foreach ($range in ($planned+"$IpAddress/32")) {
            if (Test-Overlap $range $entry.Prefix) { throw "Foreign $($entry.Source) overlaps: $range / $($entry.Prefix)" }
        }
    }
    foreach ($other in $Inventory.Vms) {
        if ($other.Name -eq $name) { continue }
        if ($other.Ips -contains $IpAddress) { throw 'VM address already in use' }
        foreach ($p in $other.ClusterCidrs) {
            foreach ($range in @($PodCidr,$ServiceCidr)) { if (Test-Overlap $range $p) { throw 'Cluster CIDR already allocated to another VM' } }
        }
    }
    $noop=$vm.Count -eq 1
    # Reserve full dynamic-disk growth plus 10 GiB for the extracted Canonical VHD/cache/seed, never overcommit.
    if (-not $noop -and $Inventory.FreeMemoryGB -lt $MemoryGB+4) { throw "Insufficient free RAM: measured $($Inventory.FreeMemoryGB) GiB, require $($MemoryGB+4) GiB; close browsers/desktop apps and stop WSL or other guests yourself" }
    if (-not $noop -and $Inventory.FreeDiskGB -lt $DiskGB+10) { throw 'Insufficient E: disk (full VHDX growth plus 10 GiB conversion/cache reserve)' }
    return @{ Settings=$settings; Stamp=$stamp; Image=$Image; OwnedNetwork=$owned;
        FreeMemoryGB=$Inventory.FreeMemoryGB; FreeDiskGB=$Inventory.FreeDiskGB; NoChanges=$noop; Actions=@(if(-not $noop){'Verify Canonical download';'Create NoCloud ISO';'Create/verify owned NAT';'Convert/resize dynamic VHDX';'Create Generation 2 VM (left Off)'}) }
}
function Format-TwinfraPlan([hashtable]$Plan) {
    $s=$Plan.Settings; $i=$Plan.Image
    return @"
PLAN ONLY: no downloads, files, network or VM changes
VM: $($s.Name) | Generation 2 | $($s.Cpu) vCPU | $($s.MemoryGB) GiB static RAM | $($s.DiskGB) GiB dynamic VHDX
Free RAM measured: $($Plan.FreeMemoryGB) GiB | Required: $($s.MemoryGB+4) GiB; if short, close browsers/desktop apps and stop WSL or other guests yourself
Free E: disk measured: $($Plan.FreeDiskGB) GiB | Required: $($s.DiskGB+10) GiB
Nested virtualization: enabled; VM remains Off until owner starts it
Switch: twinfra-nat | 10.50.0.0/24 | gateway 10.50.0.1 | VM $($s.IpAddress)
Pods: $($s.PodCidr) | Services: $($s.ServiceCidr)
Image URL: $($i.imageUrl)
File: $($i.fileName) | Size: $($i.sizeBytes) bytes | SHA256: $($i.sha256)
Checksums: $($i.checksumsUrl)
Disk: $($s.Disk) | Seed: $($s.Seed)
Actions: $($Plan.Actions -join '; ')
Existing VM already verified: $($Plan.NoChanges)
"@
}
function Assert-TwinfraImage([string]$File,[hashtable]$Lock,[string]$Checksums) {
    $entry='(?m)^'+[regex]::Escape($Lock.sha256)+'\s+\*?'+[regex]::Escape($Lock.fileName)+'\r?$'
    if ($Checksums -notmatch $entry -or (Get-Item -LiteralPath $File).Length -ne $Lock.sizeBytes -or
        (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Lock.sha256) {
        throw "Canonical image size/checksum mismatch; delete $File and rerun; no automatic deletion or VM/network changes"
    }
}
Export-ModuleMember -Function Get-IPv4Range,Test-Overlap,Test-ExcludedRoute,New-TwinfraPlan,Format-TwinfraPlan,Assert-TwinfraImage
