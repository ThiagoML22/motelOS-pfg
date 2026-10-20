# Aplica las migraciones sobre un PostgreSQL 16 descartable y corre las verificaciones SQL del canal.
# Uso (desde src/): powershell -File db/verificar_local.ps1
$ErrorActionPreference = 'Stop'
$db = $PSScriptRoot
$nombre = 'motelos_verif_sql'

function Invoke-Psql([string]$base, [string[]]$argumentos) {
    docker exec $nombre psql -U postgres -d $base -v ON_ERROR_STOP=1 -q @argumentos
    if ($LASTEXITCODE -ne 0) { throw "psql fallo en $base con: $($argumentos -join ' ')" }
}

docker rm -f $nombre 2>$null | Out-Null
docker run -d --name $nombre -e POSTGRES_PASSWORD=postgres -v "${db}:/db:ro" postgres:16 | Out-Null
try {
    for ($i = 0; $i -lt 30; $i++) {
        docker exec $nombre pg_isready -U postgres -q
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    Start-Sleep -Seconds 2
    $migraciones = Get-ChildItem (Join-Path $db 'migraciones') -Filter *.sql | Sort-Object Name

    Invoke-Psql 'postgres' @('-c', 'CREATE DATABASE motel_schema;')
    foreach ($m in $migraciones) {
        Write-Host "Aplicando $($m.Name)"
        Invoke-Psql 'motel_schema' @('-f', "/db/migraciones/$($m.Name)")
    }
    foreach ($v in 'verify_inmutabilidad.sql', 'verify_roles.sql', 'verify_caja.sql') {
        Write-Host "Verificando $v"
        Invoke-Psql 'motel_schema' @('-f', "/db/$v")
    }

    Write-Host 'Verificando la migracion desde una base v1.2 con datos'
    Invoke-Psql 'postgres' @('-c', 'CREATE DATABASE motel_migracion;')
    Invoke-Psql 'motel_migracion' @('-f', '/db/migraciones/001_esquema_v1.sql')
    Invoke-Psql 'motel_migracion' @('-v', 'fase=antes', '-f', '/db/verify_migracion_datos_v1.sql')
    foreach ($m in $migraciones | Where-Object { $_.Name -ne '001_esquema_v1.sql' }) {
        Invoke-Psql 'motel_migracion' @('-f', "/db/migraciones/$($m.Name)")
    }
    Invoke-Psql 'motel_migracion' @('-v', 'fase=despues', '-f', '/db/verify_migracion_datos_v1.sql')
    Write-Host 'Todas las verificaciones SQL pasaron.'
}
finally {
    docker rm -f $nombre | Out-Null
}
