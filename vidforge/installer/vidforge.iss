; Script de empaquetado Inno Setup 6 para VidForge Studio (Windows x64)
#define MyAppName "VidForge Studio"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "VidForge Clean-Room"
#define MyAppExeName "Iniciar-VidForge.bat"

[Setup]
AppId={{8F4E2B10-9A3C-4D7E-B123-7C8E9D0A1B2C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\VidForge
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\storage\installer_out
OutputBaseFilename=VidForge-Studio-1.0.0-Setup
Compression=lzma2/fast
SolidCompression=no
AppMutex=Local\VidForge.Runtime.v1

[Files]
Source: "..\apps\*"; DestDir: "{app}\apps"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\packages\*"; DestDir: "{app}\packages"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\MANIFEST.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Iniciar-VidForge.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Iniciar-Servidor-Web.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "VidForge.Desktop.v1"

[Run]
Filename: "{app}\runtime\venv\Scripts\python.exe"; Parameters: """{app}\tools\verify-install.py"" ""{app}"""; Flags: runhidden waituntilterminated
