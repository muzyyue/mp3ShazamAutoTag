' ============================================================
'  Imusic GUI launcher - background, no persistent console.
'  Double-click this file to launch the GUI.
'
'  NOTE: uses python.exe + launcher_hidden.py, NOT pythonw.exe.
'  .venv's pythonw.exe is incompatible with PySide6 here
'  (Qt windows never appear, only a fake console window).
'  launcher_hidden.py hides its console right after startup.
'  ============================================================
Option Explicit

Dim fso, shell, scriptDir, exePath, pyPath, cmd
Set fso  = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Directory containing this script (project root)
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

exePath = scriptDir & "\.venv\Scripts\python.exe"
pyPath  = scriptDir & "\launcher_hidden.py"

' Guard: virtual environment must exist
If Not fso.FileExists(exePath) Then
    MsgBox "Virtual environment not found: " & exePath & vbCrLf & _
           "Create it first with:  uv venv", vbExclamation, "Imusic"
    WScript.Quit 1
End If

' 1 = SW_SHOWNORMAL: python.exe console flashes ~100ms,
' then launcher_hidden.py hides it. Qt window stays visible.
shell.CurrentDirectory = scriptDir
shell.Run """" & exePath & """ """ & pyPath & """", 1, False