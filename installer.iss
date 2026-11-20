#define MyAppName "Программа обработки чеков"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "Alex Elistratov"
#define MyAppExeName "BASE_CHECK.exe"

[Setup]
AppId={{7B3C9A21-5D4E-4F62-9A18-2C6E5D8B4F73}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\BASE_CHECK
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; --- обновление поверх старой версии ---
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
UsePreviousLanguage=yes
UsePreviousPrivileges=yes
DisableDirPage=auto
DisableProgramGroupPage=auto
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll
RestartApplications=no
OutputDir=dist
OutputBaseFilename=BASE_CHECK-{#MyAppVersion}-win64-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no
MinVersion=10.0
#if FileExists("assets\app.ico")
SetupIconFile=assets\app.ico
#endif

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; чистим рантайм прошлой версии, чтобы не оставались старые dll/pyd
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "dist\BASE_CHECK\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; База, настройки и логи в %APPDATA%\BASE_CHECK НЕ удаляются.

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  RC: Integer;
begin
  Result := '';
  NeedsRestart := False;
  // тихо закрываем запущенную программу, чтобы файлы не были заблокированы
  Exec(ExpandConstant('{cmd}'), '/C taskkill /IM "{#MyAppExeName}" /F', '',
       SW_HIDE, ewWaitUntilTerminated, RC);
  Sleep(800);
end;