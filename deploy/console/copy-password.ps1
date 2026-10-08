# Operator-only: no private value is printed or written to a host file.
# This explicitly replaces the clipboard; clear it after first login.
$ErrorActionPreference = 'Stop'
$recordText = & wsl.exe -d Ubuntu -u root -- /usr/local/bin/k3s kubectl --kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml --context=vcloud-wsl-local --request-timeout=15s -n platform-services get secret vcloud-wsl-console-admin '-o=json' 2>$null
if ($LASTEXITCODE -ne 0 -or -not $recordText) { throw 'Console credential reference unavailable; private details withheld' }
try {
    $record = ($recordText -join "`n") | ConvertFrom-Json
    if ($record.metadata.labels.'vcloud.io/component' -ne 'vcloud-console-identity') { throw 'Refusing unowned credential reference' }
    $user = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($record.data.'admin-user'))
    $realm = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($record.data.realm))
    if ($user -ne 'vcloud-admin' -or $realm -ne 'vcloud') { throw 'Unexpected realm account' }
    $privateBytes = [Convert]::FromBase64String($record.data.'admin-password')
    $privateText = [Text.Encoding]::UTF8.GetString($privateBytes)
    if ($privateText.Length -lt 32) { throw 'Invalid credential reference' }
    Set-Clipboard -Value $privateText
    Write-Host 'Temporary portal password copied. Realm: vcloud. Username: vcloud-admin. Change password and enroll MFA at first login; clear the clipboard afterwards.'
} finally {
    if ($privateBytes) { [Array]::Clear($privateBytes, 0, $privateBytes.Length) }
    $privateText = $null; $record = $null; $recordText = $null
}
