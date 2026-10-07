# Operator-only retrieval: no private value is written to the console or a file.
# Run in a local PowerShell terminal; this intentionally replaces the clipboard.
$ErrorActionPreference = 'Stop'
$recordText = & wsl.exe -d Ubuntu -u root -- /usr/local/bin/k3s kubectl --kubeconfig=/etc/vcloud-wsl/kubeconfig.yaml --context=vcloud-wsl-local --request-timeout=15s -n platform-services get secret vcloud-wsl-keycloak-admin '-o=json' 2>$null
if ($LASTEXITCODE -ne 0 -or -not $recordText) { throw 'Keycloak admin Secret is unavailable; private details withheld' }
try {
    $record = ($recordText -join "`n") | ConvertFrom-Json
    if ($record.metadata.labels.'vcloud.io/component' -ne 'keycloak-admin-bootstrap') { throw 'Refusing an unowned credential reference' }
    $username = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($record.data.'admin-user'))
    if ($username -ne 'vcloud-admin') { throw 'Unexpected administrator reference' }
    $privateBytes = [Convert]::FromBase64String($record.data.'admin-password')
    $privateText = [Text.Encoding]::UTF8.GetString($privateBytes)
    if ($privateText.Length -lt 32) { throw 'Invalid credential reference' }
    Set-Clipboard -Value $privateText
    Write-Host 'Keycloak admin password copied. Username: vcloud-admin. Paste into the local login page; clear the clipboard afterwards.'
} finally {
    if ($privateBytes) { [Array]::Clear($privateBytes, 0, $privateBytes.Length) }
    $privateText = $null
    $record = $null
    $recordText = $null
}
