<#
.SYNOPSIS
  增量构建并推送 SmartGallery 汉化镜像到 Harbor。

.DESCRIPTION
  默认走增量构建：以上一版镜像为基底，只拷贝改动的代码/词典/模板，跳过 apt 与 pip，
  通常 20~60 秒完成；上游动了 requirements.txt 时会自动补装依赖，也只有那一次慢。

  需要完整重建（上游改了 Dockerfile 的 apt 部分、或想清理层层叠加的历史）时加 -Full。

.PARAMETER Version
  目标标签，默认读取 Makefile 里的 SMARTGALLERY_VERSION 并加 -i18n 后缀，如 2.24.4-i18n。

.PARAMETER Base
  增量基底镜像，默认自动取本机最新的一版 smartgallery:*（排除本次要构建的标签）。

.PARAMETER Registry
  目标仓库前缀，默认 ai.icewin.cn:8081 上的 icegroup/smart-comfyui-gallery。

.PARAMETER Full
  走上游 Dockerfile 完整构建（apt + pip 全量），耗时约 10~20 分钟。

.PARAMETER NoPush
  只构建不推送。

.PARAMETER SkipVerify
  跳过镜像内自检（不推荐，自检只要几秒）。

.EXAMPLE
  .\build-push-harbor.ps1
  .\build-push-harbor.ps1 -Version 2.24.5-i18n
  .\build-push-harbor.ps1 -Full
#>
param(
    [string]$Version,
    [string]$Base,
    [string]$Registry = "ai.icewin.cn:8081/icegroup/smart-comfyui-gallery",
    [switch]$Full,
    [switch]$NoPush,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$StateFile = Join-Path $PSScriptRoot ".docker-build-state.json"

function Step($msg) { Write-Host ""; Write-Host "=== $msg ===" -ForegroundColor Cyan }

# ---------- 1. 决定版本号 ----------
if (-not $Version) {
    $mk = Get-Content -LiteralPath (Join-Path $Repo "Makefile") -Encoding utf8
    $m = [regex]::Match(($mk -join "`n"), 'SMARTGALLERY_VERSION\s*=\s*([\d.]+)')
    if (-not $m.Success) { throw "从 Makefile 里读不到 SMARTGALLERY_VERSION，请用 -Version 指定" }
    $Version = "$($m.Groups[1].Value)-i18n"
}
$Image = "smartgallery:$Version"
Write-Host "目标镜像: $Image"
Write-Host "目标仓库: ${Registry}:${Version} + :latest"

# ---------- 2. 决定基底镜像 ----------
if (-not $Full -and -not $Base) {
    $cands = docker images --filter "reference=smartgallery" --format "{{.Repository}}:{{.Tag}}|{{.CreatedAt}}" 2>$null |
        ForEach-Object {
            # 注意：-split 用正则，"|" 必须写成 '\|'，否则会被当成"或"逐字符切分
            $p = $_ -split '\|'
            if ($p.Count -lt 2 -or $p[1].Length -lt 19) { return }
            # CreatedAt 形如 "2026-11-11 23:20:27 +0800 CST"，只取前 19 位再解析
            [pscustomobject]@{ Tag = $p[0]; Created = [datetime]::ParseExact($p[1].Substring(0, 19), 'yyyy-MM-dd HH:mm:ss', $null) }
        } |
        Where-Object { $_.Tag -ne $Image } |
        Sort-Object Created -Descending
    if (-not $cands) {
        Write-Host "本机只找到要构建的这个标签，没有其它基底镜像。" -ForegroundColor Yellow
        Write-Host "  - 要重建同一版本：显式指定 -Base smartgallery:2.24.4-i18n" -ForegroundColor Yellow
        Write-Host "  - 要从头完整构建：加 -Full（约 20 分钟）" -ForegroundColor Yellow
        throw "无法确定增量基底镜像"
    }
    else {
        $Base = $cands[0].Tag
        Write-Host "增量基底: $Base（$($cands[0].Created.ToString('yyyy-MM-dd HH:mm'))）"
    }
}

# ---------- 3. 上游 Dockerfile / requirements 变化检测 ----------
$shaDockerfile = (Get-FileHash -LiteralPath (Join-Path $Repo "Dockerfile") -Algorithm SHA256).Hash
$shaReq = (Get-FileHash -LiteralPath (Join-Path $Repo "requirements.txt") -Algorithm SHA256).Hash
if (-not $Full) {
    if (Test-Path -LiteralPath $StateFile) {
        $st = Get-Content -LiteralPath $StateFile -Raw -Encoding utf8 | ConvertFrom-Json
        if ($st.dockerfile_sha256 -and $st.dockerfile_sha256 -ne $shaDockerfile) {
            Write-Host "上游 Dockerfile 变了（apt 层可能新增依赖），自动改为完整构建" -ForegroundColor Yellow
            $Full = $true
        }
    }
    else {
        Write-Host "没有历史构建记录，本次按增量处理；若发现运行期缺系统库，请加 -Full 重建" -ForegroundColor Yellow
    }
}

# ---------- 4. 构建 ----------
$sw = [Diagnostics.Stopwatch]::StartNew()
if ($Full) {
    Step "完整构建（上游 Dockerfile）"
    $log = Join-Path $Repo "zh-tools\reports\build-full-$Version.log"
    docker build --build-arg CHOOSEN_TEMPLATE_DIR=templates `
        --build-arg CHOOSEN_SMARTGALLERY_FILE=smartgallery.py `
        --build-arg BUILD_APT_PROXY= `
        -t $Image -f (Join-Path $Repo "Dockerfile") $Repo 2>&1 | Tee-Object -FilePath $log | Select-Object -Last 8
}
else {
    Step "增量构建（基底 $Base）"
    $log = Join-Path $Repo "zh-tools\reports\build-incr-$Version.log"
    docker build --build-arg BASE_IMAGE=$Base -t $Image -f (Join-Path $Repo "zh-tools\Dockerfile.incr") $Repo 2>&1 |
        Tee-Object -FilePath $log | Select-Object -Last 8
}
if ($LASTEXITCODE -ne 0) { throw "构建失败，日志见 $log" }
$elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1)
Write-Host "构建耗时: ${elapsed}s" -ForegroundColor Green

# 记录本次构建指纹（下次据此判断要不要强制完整构建）
@{ version = $Version; base = $(if ($Full) { "full" } else { $Base }); dockerfile_sha256 = $shaDockerfile;
    requirements_sha256 = $shaReq; built_at = (Get-Date).ToString("s") } |
    ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding utf8

# ---------- 5. 镜像内自检 ----------
if (-not $SkipVerify) {
    Step "镜像内自检"
    $mount = "$(Join-Path $Repo 'zh-tools'):/chk:ro"
    docker run --rm -v $mount --entrypoint /app/venv/bin/python $Image /chk/verify_image.py
    if ($LASTEXITCODE -ne 0) { throw "自检未通过，已停止推送" }
}

# ---------- 6. 打标签并推送 ----------
docker tag $Image "${Registry}:${Version}"
docker tag $Image "${Registry}:latest"

if ($NoPush) {
    Write-Host "已跳过推送（-NoPush）。本地标签已打好。" -ForegroundColor Yellow
}
else {
    Step "推送到 Harbor"
    docker push "${Registry}:${Version}"
    if ($LASTEXITCODE -ne 0) { throw "推送 ${Registry}:${Version} 失败" }
    docker push "${Registry}:latest"
    if ($LASTEXITCODE -ne 0) { throw "推送 latest 失败" }
    Write-Host "完成: ${Registry}:${Version} / :latest" -ForegroundColor Green
}
