$desktop = [Environment]::GetFolderPath('Desktop')
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$desktop\SistPrev.lnk")
$Shortcut.TargetPath = 'C:\Users\Administrador\Documents\Documents\previdenciario\iniciar.bat'
$Shortcut.WorkingDirectory = 'C:\Users\Administrador\Documents\Documents\previdenciario'
$Shortcut.Description = 'SistPrev - Sistema Previdenciario'
$Shortcut.IconLocation = 'C:\Users\Administrador\Documents\Documents\previdenciario\feliciano.ico'
$Shortcut.Save()
Write-Host "Atalho criado em: $desktop\SistPrev.lnk"
