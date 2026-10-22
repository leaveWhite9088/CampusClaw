$ErrorActionPreference = 'Continue'
$docx = 'C:\temp_lo\report.docx'
$pdf = 'C:\temp_lo\report.pdf'
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($docx)
  Write-Output "OPENED"
  foreach ($toc in $doc.TablesOfContents) { $toc.Update() | Out-Null }
  Write-Output "TOC_UPDATED"
  $doc.ExportAsFixedFormat($pdf, 17)
  Write-Output "PDF_EXPORTED"
  $doc.Close($false)
} catch {
  Write-Output ("FAILED: " + $_.Exception.Message)
} finally {
  $word.Quit()
}
