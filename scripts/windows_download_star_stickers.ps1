# Download TCDB /Images/Cards/ scans for 1987 Fleer Star Stickers onto the SMB share.
# Run on the Hyper-V host (MEDIA) in PowerShell:
#   cd D:\phillies-card-images
#   .\download-1987-star-stickers.ps1
#
# Files land in .\10070\ and are visible in the VM at /mnt/phillies-images/10070/

$ErrorActionPreference = "Stop"
$ShareRoot = "D:\phillies-card-images"
$SidDir = Join-Path $ShareRoot "10070"
New-Item -ItemType Directory -Force -Path $SidDir | Out-Null

$cards = @(
    @{ Name = "Steve Bedrosian"; Referer = "https://www.tcdb.com/ViewCard.cfm/sid/10070/cid/436508/1987-Fleer-Star-Stickers-8-Steve-Bedrosian"; Front = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436508RepFr.jpg"; Back = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436508RepBk.jpg" },
    @{ Name = "Von Hayes"; Referer = "https://www.tcdb.com/ViewCard.cfm/sid/10070/cid/436555/1987-Fleer-Star-Stickers-55-Von-Hayes"; Front = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436555RepFr.jpg"; Back = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436555RepBk.jpg" },
    @{ Name = "Shane Rawley"; Referer = "https://www.tcdb.com/ViewCard.cfm/sid/10070/cid/436596/1987-Fleer-Star-Stickers-96-Shane-Rawley"; Front = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436596RepFr.jpg"; Back = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436596RepBk.jpg" },
    @{ Name = "Juan Samuel"; Referer = "https://www.tcdb.com/ViewCard.cfm/sid/10070/cid/436604/1987-Fleer-Star-Stickers-104-Juan-Samuel"; Front = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436604RepFr.jpg"; Back = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436604RepBk.jpg" },
    @{ Name = "Mike Schmidt"; Referer = "https://www.tcdb.com/ViewCard.cfm/sid/10070/cid/436607/1987-Fleer-Star-Stickers-107-Mike-Schmidt"; Front = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-107Fr.jpg"; Back = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-107Bk.jpg" },
    @{ Name = "Kent Tekulve"; Referer = "https://www.tcdb.com/ViewCard.cfm/sid/10070/cid/436616/1987-Fleer-Star-Stickers-116-Kent-Tekulve"; Front = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436616RepFr.jpg"; Back = "https://www.tcdb.com/Images/Cards/Baseball/10070/10070-436616RepBk.jpg" }
)

function Save-TcdbImage {
    param(
        [string]$Url,
        [string]$Referer,
        [string]$Dest
    )
    $headers = @{
        "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        "Referer"    = $Referer
        "Accept"     = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
    }
    Invoke-WebRequest -Uri $Url -Headers $headers -OutFile $Dest -UseBasicParsing
    $size = (Get-Item $Dest).Length
    if ($size -lt 512) { throw "Download too small ($size bytes): $Url" }
    Write-Host "  saved $Dest ($size bytes)"
}

foreach ($card in $cards) {
    Write-Host "Downloading $($card.Name)..."
    $frontName = Split-Path $card.Front -Leaf
    $backName = Split-Path $card.Back -Leaf
    Save-TcdbImage -Url $card.Front -Referer $card.Referer -Dest (Join-Path $SidDir $frontName)
    Start-Sleep -Milliseconds 500
    Save-TcdbImage -Url $card.Back -Referer $card.Referer -Dest (Join-Path $SidDir $backName)
    Start-Sleep -Milliseconds 500
}

Write-Host "Done. $($cards.Count) cards -> $SidDir"
Write-Host "On the VM, run:"
Write-Host "  sg devagent -c './venv/bin/python scripts/demo_download_set_images.py --set 4886 --register-existing'"
