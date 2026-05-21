; Inno Setup script for Network Monitor.
;
; Build the exe with PyInstaller first (see build/windows-build.ps1), then
; run Inno Setup Compiler on this file. The result is NetworkMonitor-Setup.exe
; which installs into Program Files and registers Add/Remove Programs entries.
;
; The {#AppVersion} is expected to be passed via the command line:
;     ISCC.exe /DAppVersion=1.2.3 installer\windows.iss

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName        "Network Monitor"
#define AppPublisher   "NetworkMonitor"
#define AppExeName     "NetworkMonitor.exe"
#define AppId          "{{B5E4F0F1-7B2E-4D2C-9A1F-NETWORKMONITOR}}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\NetworkMonitor
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
OutputDir=..\installer_output
OutputBaseFilename=NetworkMonitor-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=force
RestartApplications=yes
DisableProgramGroupPage=yes
SetupIconFile=..\assets\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked
Name: "startup";     Description: "Launch Network Monitor when I sign in";  GroupDescription: "Startup:";              Flags: unchecked

[Files]
; The PyInstaller-produced exe lives in ..\dist\NetworkMonitor.exe
Source: "..\dist\NetworkMonitor.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";                  Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}";        Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";          Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";            Filename: "{app}\{#AppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
