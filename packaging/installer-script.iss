#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif

#define AppName "COA Generator"
#define AppExeName "COAGenerator.exe"

[Setup]
AppId={{AEE908C5-55DF-4CF0-9FF8-22D5344E2F0F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=COA Generator Contributors
DefaultDirName={localappdata}\Programs\COA Generator
DefaultGroupName=COA Generator
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=release
OutputBaseFilename=COA-Generator-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\COAGenerator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\COA Generator"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\COA Generator"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch COA Generator"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\{#AppExeName}"; Parameters: "--stop"; Flags: runhidden waituntilterminated skipifdoesntexist

; Deliberately no [UninstallDelete] entry for %LOCALAPPDATA%\COAGenerator.
; Numbering state, user settings, and user-created documents survive upgrades and uninstall.
