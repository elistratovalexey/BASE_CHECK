#define MyAppName "Программа обработки чеков"
#define MyAppExeName "BASE_CHECK.exe"
#define MyAppPublisher "Alex Elistratov"

; версия берётся из уже собранного exe (а тот — из config.py)
#if FileExists("dist\BASE_CHECK\BASE_CHECK.exe")
  #define MyAppVersion GetStringFileInfo("dist\BASE_CHECK\BASE_CHECK.exe", "ProductVersion")
#else
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{7B3C9A21-5D4E-4F62-9A18-2C6E5D8B4F73}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductName={#MyAppName}
DefaultDirName={autopf}\BASE_CHECK
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
; наследуем параметры прошлой установки
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
; чистим рантайм прошлой версии (PyInstaller 6 кладёт всё в _internal)
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
; удаляем только своё, а не весь каталог установки
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\{#MyAppExeName}"
; База, настройки и логи в %APPDATA%\BASE_CHECK НЕ удаляются.

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{7B3C9A21-5D4E-4F62-9A18-2C6E5D8B4F73}_is1';

function OldUninstallCmd(): String;
var
  S: String;
  Roots: array[0..3] of Integer;
  I: Integer;
begin
  Result := '';
  Roots[0] := HKCU32; Roots[1] := HKCU64;
  Roots[2] := HKLM32; Roots[3] := HKLM64;
  for I := 0 to 3 do
  begin
    if RegQueryStringValue(Roots[I], UninstallKey, 'QuietUninstallString', S) then
    begin
      Result := S;
      Exit;
    end;
    if RegQueryStringValue(Roots[I], UninstallKey, 'UninstallString', S) then
    begin
      Result := S;
      Exit;
    end;
  end;
end;

function SplitCmd(const Cmd: String; var ExeName, Params: String): Boolean;
var
  S: String;
  P: Integer;
begin
  Result := False;
  ExeName := ''; Params := '';
  S := Cmd;
  if S = '' then Exit;
  if S[1] = '"' then
  begin
    Delete(S, 1, 1);
    P := Pos('"', S);
    if P = 0 then Exit;
    ExeName := Copy(S, 1, P - 1);
    Params := Trim(Copy(S, P + 1, Length(S)));
  end
  else
  begin
    P := Pos(' ', S);
    if P = 0 then
      ExeName := S
    else
    begin
      ExeName := Copy(S, 1, P - 1);
      Params := Trim(Copy(S, P + 1, Length(S)));
    end;
  end;
  Result := ExeName <> '';
end;

procedure InitializeWizard();
begin
  WizardForm.Caption := WizardForm.Caption + ' — v{#MyAppVersion}';
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Cmd, ExeName, Params: String;
  RC, I: Integer;
begin
  Result := '';
  NeedsRestart := False;

  // 1) закрываем запущенную программу — иначе dll заблокированы
  Exec(ExpandConstant('{cmd}'), '/C taskkill /IM "{#MyAppExeName}" /F', '',
       SW_HIDE, ewWaitUntilTerminated, RC);
  Sleep(600);

  // 2) тихо снимаем ЛЮБУЮ прежнюю версию (в т.ч. установленную в другом режиме).
  //    Именно из-за неё установщик требовал удалить программу вручную.
  Cmd := OldUninstallCmd();
  if SplitCmd(Cmd, ExeName, Params) then
  begin
    Exec(ExeName, Params + ' /SILENT /SUPPRESSMSGBOXES /NORESTART', '',
         SW_HIDE, ewWaitUntilTerminated, RC);
    // деинсталлятор работает из временной копии — ждём, пока запись исчезнет
    for I := 1 to 60 do
    begin
      if OldUninstallCmd() = '' then Break;
      Sleep(500);
    end;
    Sleep(500);
  end;
end;
