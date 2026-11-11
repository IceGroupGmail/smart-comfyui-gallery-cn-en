# 增量汉化：拉取上游更新（SmartGallery）
# 用法：
#   .\sync-upstream.ps1            拉取 + 合并 + 自动体检
#   .\sync-upstream.ps1 -NoScan    只合并，不跑体检
#   .\sync-upstream.ps1 -Abort     放弃本次合并，回到合并前
#
# 设计原则：
#   汉化成果只在你的提交里，上游永远不在同一行改你的翻译，冲突天然很少；
#   rerere 会记住你解决过的冲突，下次同样的冲突会自动套用旧解法。

[CmdletBinding()]
param(
    [string]$Repo = (Split-Path -Path $PSScriptRoot -Parent),
    [string]$Remote = "origin",
    [string]$Branch = "main",
    [switch]$Abort,
    [switch]$NoScan
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args1)
    $out = & git -C $Repo @Args1 2>&1
    return @{ Code = $LASTEXITCODE; Out = ($out | Out-String).Trim() }
}

function Write-Step($text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath (Join-Path $Repo ".git"))) {
    Write-Host "不是 Git 仓库：$Repo" -ForegroundColor Red
    exit 2
}

# ---------- 放弃合并 ----------
if ($Abort) {
    $r = Invoke-Git merge --abort
    if ($r.Code -eq 0) {
        Write-Host "已放弃合并，工作区回到合并前状态。" -ForegroundColor Yellow
    }
    else {
        Write-Host "没有可放弃的合并（或已失败）：$($r.Out)" -ForegroundColor DarkGray
    }
    exit 0
}

# ---------- 冲突记忆：解决过一次，下次自动套用 ----------
Invoke-Git config --local rerere.enabled true | Out-Null
Invoke-Git config --local rerere.autoupdate true | Out-Null

# ---------- 拉取 ----------
Write-Step "拉取 $Remote/$Branch"
$fetch = Invoke-Git fetch $Remote --prune
if ($fetch.Code -ne 0) {
    Write-Host "拉取失败，先解决网络/代理问题：" -ForegroundColor Red
    Write-Host $fetch.Out
    exit 1
}

$newCommits = (Invoke-Git log --oneline "HEAD..$Remote/$Branch").Out
if ([string]::IsNullOrWhiteSpace($newCommits)) {
    Write-Host "上游没有新提交，已是最新。" -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "上游新提交：" -ForegroundColor Yellow
Write-Host $newCommits

$stat = (Invoke-Git diff --stat "HEAD...$Remote/$Branch").Out
Write-Host ""
Write-Host "这次上游改动范围：" -ForegroundColor Yellow
Write-Host $stat

# ---------- 合并 ----------
Write-Step "合并 $Remote/$Branch 到当前分支"
$merge = Invoke-Git merge --no-edit "$Remote/$Branch"
Write-Host $merge.Out

if ($merge.Code -ne 0) {
    Write-Host ""
    Write-Host "有冲突，需要手工处理：" -ForegroundColor Red
    $files = (Invoke-Git diff --name-only --diff-filter=U).Out
    Write-Host $files
    Write-Host ""
    Write-Host "处理原则（模板类冲突）：" -ForegroundColor Yellow
    Write-Host "  1. 上游新增的标签/元素，一律保留"
    Write-Host "  2. 本地已包裹 {{ _('...') }} 的文案，保留包裹"
    Write-Host "  3. 上游改了同一句英文文案时，用上游的新英文，并把 _() 里的键一起换掉"
    Write-Host "  4. 改完执行：git add <文件>   再跑到 .\sync-upstream.ps1 -NoScan 或直接 git commit"
    Write-Host ""
    Write-Host "不想处理了：.\sync-upstream.ps1 -Abort" -ForegroundColor DarkGray
    exit 1
}

# ---------- 合并成功，自动体检 ----------
Write-Step "合并完成，开始增量汉化体检"
if ($NoScan) {
    Write-Host "已跳过体检（-NoScan）"
    exit 0
}

& python (Join-Path $PSScriptRoot "zh_scan.py")
$scanCode = $LASTEXITCODE

Write-Host ""
if ($scanCode -eq 0) {
    Write-Host "体检通过：这个版本已经全部汉化，可以直接提交/推送。" -ForegroundColor Green
}
else {
    Write-Host "体检查出待汉化内容，处理步骤：" -ForegroundColor Yellow
    Write-Host "  1. 需要自动包裹：python zh_scan.py --apply    然后 git diff 复核"
    Write-Host "  2. 生成待翻译清单：python zh_scan.py --emit   编辑 zh-tools\reports\待翻译.json"
    Write-Host "  3. 合并译文：python zh_scan.py --merge zh-tools\reports\待翻译.json"
    Write-Host "  4. 复查：python zh_scan.py"
}
exit $scanCode
