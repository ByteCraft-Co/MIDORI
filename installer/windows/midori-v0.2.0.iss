#define MyAppId "midori.language.compiler.v020"
#define MyAppName "MIDORI"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Midori Contributors"
#define MyAppURL "https://github.com/ByteCraft-Co/MIDORI"
#define MyAppUpdatesURL "https://github.com/ByteCraft-Co/MIDORI/releases"
#ifndef MyVsixVersion
  #define MyVsixVersion "0.0.3"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppUpdatesURL}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} Installer
SetupIconFile=midori-logo.ico
DefaultDirName={autopf}\MIDORI-{#MyAppVersion}
DefaultGroupName=MIDORI-{#MyAppVersion}
LicenseFile=..\..\LICENSE
AllowNoIcons=yes
OutputDir=output\v0.2.0
OutputBaseFilename=midori-setup-v0.2.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousLanguage=yes
UsePreviousSetupType=yes
UsePreviousTasks=yes
DisableProgramGroupPage=no
ChangesEnvironment=yes
CloseApplications=yes
DisableDirPage=no
SetupLogging=yes
UninstallDisplayName=MIDORI 0.2.0
UninstallDisplayIcon={app}\assets\midori-logo.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "typical"; Description: "&Typical installation"
Name: "full"; Description: "&Full installation"
Name: "minimal"; Description: "&Minimal installation"

[Components]
Name: "core"; Description: "Compiler core and launcher scripts"; Types: typical full minimal; Flags: fixed
Name: "examples"; Description: "Example MIDORI programs"; Types: typical full
Name: "vscode"; Description: "VS Code extension bundle"; Types: full
Name: "devtools"; Description: "Tests and development files"; Types: full

[Tasks]
Name: "path_user"; Description: "Add MIDORI to PATH for current user"; Flags: checkedonce
Name: "path_machine"; Description: "Add MIDORI to PATH for all users"; Flags: unchecked; Check: IsAdminInstallMode
Name: "assoc_mdr"; Description: "Associate .mdr files with MIDORI"; Flags: unchecked
Name: "desktopicon"; Description: "Create desktop shortcut"; Flags: unchecked
Name: "pipdeps"; Description: "Install Python dependencies with pip after install"; Flags: unchecked
Name: "selfcheck"; Description: "Run MIDORI self-check after install"; Flags: checkedonce
Name: "check_updates"; Description: "Create 'Check for Updates' shortcut"; Flags: checkedonce

[Dirs]
Name: "{app}\installer"; Components: core
Name: "{app}\logs"; Components: core
Name: "{app}\assets"; Components: core

[Files]
Source: "..\..\src\*"; DestDir: "{app}\src"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: core
Source: "..\..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion; Components: core
Source: "midori-logo.ico"; DestDir: "{app}\assets"; Flags: ignoreversion; Components: core
Source: "..\..\vscode-extension\assets\midori-logo.png"; DestDir: "{app}\assets"; Flags: ignoreversion; Components: core
Source: "..\..\examples\*"; DestDir: "{app}\examples"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: examples
Source: "..\..\vscode-extension\package.json"; DestDir: "{app}\vscode-extension"; Flags: ignoreversion; Components: vscode
Source: "..\..\vscode-extension\package-lock.json"; DestDir: "{app}\vscode-extension"; Flags: ignoreversion; Components: vscode
Source: "..\..\vscode-extension\README.md"; DestDir: "{app}\vscode-extension"; Flags: ignoreversion; Components: vscode
Source: "..\..\vscode-extension\LICENSE"; DestDir: "{app}\vscode-extension"; Flags: ignoreversion; Components: vscode
Source: "..\..\vscode-extension\language-configuration.json"; DestDir: "{app}\vscode-extension"; Flags: ignoreversion; Components: vscode
Source: "..\..\vscode-extension\.vscodeignore"; DestDir: "{app}\vscode-extension"; Flags: ignoreversion; Components: vscode
Source: "..\..\vscode-extension\assets\*"; DestDir: "{app}\vscode-extension\assets"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: vscode
Source: "..\..\vscode-extension\icons\*"; DestDir: "{app}\vscode-extension\icons"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: vscode
Source: "..\..\vscode-extension\snippets\*"; DestDir: "{app}\vscode-extension\snippets"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: vscode
Source: "..\..\vscode-extension\src\*"; DestDir: "{app}\vscode-extension\src"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: vscode
Source: "..\..\vscode-extension\syntaxes\*"; DestDir: "{app}\vscode-extension\syntaxes"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: vscode
Source: "..\..\vscode-extension\dist\midori-language-{#MyVsixVersion}.vsix"; DestDir: "{app}\vscode-extension\dist"; Flags: ignoreversion; Components: vscode
Source: "..\..\tests\*"; DestDir: "{app}\tests"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: devtools

[Icons]
Name: "{group}\MIDORI Terminal"; Filename: "{app}\midori-terminal.cmd"; IconFilename: "{app}\assets\midori-logo.ico"; Components: core
Name: "{group}\MIDORI CLI Help"; Filename: "{app}\midori.cmd"; Parameters: "--help"; IconFilename: "{app}\assets\midori-logo.ico"; Components: core
Name: "{group}\MIDORI REPL"; Filename: "{app}\midori.cmd"; Parameters: "repl"; IconFilename: "{app}\assets\midori-logo.ico"; Components: core
Name: "{group}\MIDORI Examples"; Filename: "{app}\examples"; Components: examples
Name: "{group}\Modify, Repair, or Uninstall MIDORI"; Filename: "{app}\midori-maintenance.cmd"; IconFilename: "{app}\assets\midori-logo.ico"; Components: core
Name: "{group}\Uninstall MIDORI"; Filename: "{uninstallexe}"; Components: core
Name: "{group}\Check for Updates"; Filename: "{app}\midori-update.cmd"; IconFilename: "{app}\assets\midori-logo.ico"; Tasks: check_updates; Components: core
Name: "{autodesktop}\MIDORI"; Filename: "{app}\midori-terminal.cmd"; IconFilename: "{app}\assets\midori-logo.ico"; Tasks: desktopicon; Components: core

[Run]
Filename: "{cmd}"; Parameters: "/C py -m pip install -e ""{app}"""; Flags: runhidden waituntilterminated; Tasks: pipdeps; Check: CanInstallPythonDeps; StatusMsg: "Installing Python dependencies..."
Filename: "{app}\midori.cmd"; Parameters: "--version"; Flags: runhidden waituntilterminated; Tasks: selfcheck; Check: CanRunSelfCheck; StatusMsg: "Running MIDORI self-check..."
Filename: "{app}\midori-terminal.cmd"; Parameters: "--version"; Flags: runhidden waituntilterminated; Tasks: selfcheck; Check: CanRunTerminalSelfCheck; StatusMsg: "Running MIDORI terminal self-check..."

[Registry]
Root: HKA; Subkey: "Software\MIDORI"; ValueType: string; ValueName: "InstallRoot"; ValueData: "{app}"; Flags: uninsdeletekeyifempty; Components: core
Root: HKA; Subkey: "Software\MIDORI"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"; Flags: uninsdeletekeyifempty; Components: core
Root: HKA; Subkey: "Software\MIDORI"; ValueType: string; ValueName: "Components"; ValueData: "{code:GetInstalledComponentsValue}"; Flags: uninsdeletekeyifempty; Components: core
Root: HKA; Subkey: "Software\MIDORI"; ValueType: string; ValueName: "Tasks"; ValueData: "{code:GetInstalledTasksValue}"; Flags: uninsdeletekeyifempty; Components: core
Root: HKA; Subkey: "Software\Classes\.mdr"; ValueType: string; ValueData: "Midori.Source"; Tasks: assoc_mdr; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Midori.Source"; ValueType: string; ValueData: "MIDORI Source File"; Tasks: assoc_mdr; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Midori.Source\DefaultIcon"; ValueType: string; ValueData: """{app}\assets\midori-logo.ico"",0"; Tasks: assoc_mdr; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Midori.Source\shell\open\command"; ValueType: string; ValueData: """{app}\midori.cmd"" run ""%1"""; Tasks: assoc_mdr; Flags: uninsdeletekey

[UninstallDelete]
Type: files; Name: "{app}\midori.cmd"
Type: files; Name: "{app}\midori-terminal.cmd"
Type: files; Name: "{app}\midori-maintenance.cmd"
Type: files; Name: "{app}\midori-update.cmd"
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}"

[Code]
const
  MidoriRegPath = 'Software\MIDORI\v0.2.0';
  MidoriUninstallRegPath = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1';

type
  TMaintenanceAction = (maFreshInstall, maUpdate, maModify, maRepair, maUninstall);

var
  ExistingInstallFound: Boolean;
  ExistingInstallDir: string;
  ExistingUninstallExe: string;
  ExistingUninstallArgs: string;
  ExistingComponents: string;
  ExistingTasks: string;
  MaintenancePage: TWizardPage;
  MaintenanceTitle: TNewStaticText;
  MaintenanceSubTitle: TNewStaticText;
  RadioUpdate: TRadioButton;
  RadioModify: TRadioButton;
  RadioRepair: TRadioButton;
  RadioUninstall: TRadioButton;
  SelectedAction: TMaintenanceAction;
  SeededSelections: Boolean;

function NormalizePath(const PathValue: string): string;
begin
  Result := UpperCase(RemoveBackslashUnlessRoot(Trim(PathValue)));
end;

function ParseCommandLine(const CommandLine: string; var ExeName: string; var Params: string): Boolean;
var
  S: string;
  P: Integer;
begin
  Result := False;
  ExeName := '';
  Params := '';
  S := Trim(CommandLine);
  if S = '' then
    Exit;

  if S[1] = '"' then
  begin
    Delete(S, 1, 1);
    P := Pos('"', S);
    if P = 0 then
    begin
      ExeName := S;
      Result := True;
      Exit;
    end;
    ExeName := Copy(S, 1, P - 1);
    Params := Trim(Copy(S, P + 1, MaxInt));
  end
  else
  begin
    P := Pos(' ', S);
    if P = 0 then
      ExeName := S
    else
    begin
      ExeName := Copy(S, 1, P - 1);
      Params := Trim(Copy(S, P + 1, MaxInt));
    end;
  end;

  Result := ExeName <> '';
end;

function LoadExistingInstallData: Boolean;
var
  UninstallRaw: string;
begin
  ExistingInstallFound := False;
  ExistingInstallDir := '';
  ExistingUninstallExe := '';
  ExistingUninstallArgs := '';
  ExistingComponents := '';
  ExistingTasks := '';

  if RegQueryStringValue(HKA, MidoriRegPath, 'InstallRoot', ExistingInstallDir) then
    ExistingInstallFound := DirExists(ExistingInstallDir);

  if RegQueryStringValue(HKA, MidoriRegPath, 'Components', ExistingComponents) then
  begin
  end;
  if RegQueryStringValue(HKA, MidoriRegPath, 'Tasks', ExistingTasks) then
  begin
  end;

  if RegQueryStringValue(HKA, MidoriUninstallRegPath, 'UninstallString', UninstallRaw) then
    ParseCommandLine(UninstallRaw, ExistingUninstallExe, ExistingUninstallArgs);

  Result := ExistingInstallFound;
end;

procedure SeedPreviousSelections;
begin
  if SeededSelections then
    Exit;

  if ExistingComponents <> '' then
    WizardSelectComponents(ExistingComponents);

  if ExistingTasks <> '' then
    WizardSelectTasks(ExistingTasks);

  SeededSelections := True;
end;

procedure CreateMaintenanceModePage;
begin
  MaintenancePage := CreateCustomPage(
    wpWelcome,
    'MIDORI Maintenance',
    'An existing installation was detected. Choose the maintenance action.'
  );

  MaintenanceTitle := TNewStaticText.Create(MaintenancePage);
  MaintenanceTitle.Parent := MaintenancePage.Surface;
  MaintenanceTitle.Caption := 'Current install: ' + ExistingInstallDir;
  MaintenanceTitle.Left := 0;
  MaintenanceTitle.Top := ScaleY(4);
  MaintenanceTitle.Width := MaintenancePage.SurfaceWidth;
  MaintenanceTitle.WordWrap := True;

  MaintenanceSubTitle := TNewStaticText.Create(MaintenancePage);
  MaintenanceSubTitle.Parent := MaintenancePage.Surface;
  MaintenanceSubTitle.Caption := 'You can update, modify features, repair files, or uninstall.';
  MaintenanceSubTitle.Left := 0;
  MaintenanceSubTitle.Top := MaintenanceTitle.Top + ScaleY(22);
  MaintenanceSubTitle.Width := MaintenancePage.SurfaceWidth;
  MaintenanceSubTitle.WordWrap := True;

  RadioUpdate := TRadioButton.Create(MaintenancePage);
  RadioUpdate.Parent := MaintenancePage.Surface;
  RadioUpdate.Caption := 'Update installation (recommended)';
  RadioUpdate.Left := 0;
  RadioUpdate.Top := MaintenanceSubTitle.Top + ScaleY(30);
  RadioUpdate.Checked := True;

  RadioModify := TRadioButton.Create(MaintenancePage);
  RadioModify.Parent := MaintenancePage.Surface;
  RadioModify.Caption := 'Modify installed features';
  RadioModify.Left := 0;
  RadioModify.Top := RadioUpdate.Top + ScaleY(24);

  RadioRepair := TRadioButton.Create(MaintenancePage);
  RadioRepair.Parent := MaintenancePage.Surface;
  RadioRepair.Caption := 'Repair current installation';
  RadioRepair.Left := 0;
  RadioRepair.Top := RadioModify.Top + ScaleY(24);

  RadioUninstall := TRadioButton.Create(MaintenancePage);
  RadioUninstall.Parent := MaintenancePage.Surface;
  RadioUninstall.Caption := 'Uninstall MIDORI';
  RadioUninstall.Left := 0;
  RadioUninstall.Top := RadioRepair.Top + ScaleY(24);
end;

procedure InitializeWizard;
begin
  SelectedAction := maFreshInstall;
  SeededSelections := False;
  MaintenancePage := nil;

  if LoadExistingInstallData then
  begin
    SelectedAction := maUpdate;
    CreateMaintenanceModePage;
    if ExistingInstallDir <> '' then
      WizardForm.DirEdit.Text := ExistingInstallDir;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Code: Integer;
begin
  Result := True;

  if (MaintenancePage <> nil) and (CurPageID = MaintenancePage.ID) then
  begin
    if RadioUninstall.Checked then
      SelectedAction := maUninstall
    else if RadioRepair.Checked then
      SelectedAction := maRepair
    else if RadioModify.Checked then
      SelectedAction := maModify
    else
      SelectedAction := maUpdate;

    if SelectedAction = maUninstall then
    begin
      if ExistingUninstallExe = '' then
      begin
        MsgBox(
          'Unable to locate the existing uninstaller. Use Apps & Features to remove MIDORI.',
          mbError,
          MB_OK
        );
        Result := False;
        Exit;
      end;

      if MsgBox(
        'The existing MIDORI installation will now be uninstalled.' + #13#10 +
        'Continue?',
        mbConfirmation,
        MB_YESNO
      ) <> IDYES then
      begin
        Result := False;
        Exit;
      end;

      if not Exec(
        ExistingUninstallExe,
        Trim(ExistingUninstallArgs + ' /NORESTART'),
        '',
        SW_SHOWNORMAL,
        ewWaitUntilTerminated,
        Code
      ) then
      begin
        MsgBox('Failed to run uninstaller.', mbError, MB_OK);
        Result := False;
        Exit;
      end;

      MsgBox(
        'Uninstall completed. Re-run setup if you want to install MIDORI again.',
        mbInformation,
        MB_OK
      );
      WizardForm.Close;
      Result := False;
      Exit;
    end;

    if SelectedAction = maRepair then
      SeedPreviousSelections;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;

  if (SelectedAction = maRepair) and ((PageID = wpSelectComponents) or (PageID = wpSelectTasks)) then
    Result := True;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if ExistingInstallFound and ((CurPageID = wpSelectComponents) or (CurPageID = wpSelectTasks)) then
    SeedPreviousSelections;

  if ExistingInstallFound and (CurPageID = wpSelectDir) then
  begin
    WizardForm.DirEdit.Text := ExistingInstallDir;
    WizardForm.DirBrowseButton.Enabled := SelectedAction = maModify;
  end;
end;

function Join(const LeftValue: string; const RightValue: string): string;
begin
  if LeftValue = '' then
    Result := RightValue
  else
    Result := LeftValue + ',' + RightValue;
end;

function BuildSelectedComponents: string;
begin
  Result := 'core';
  if WizardIsComponentSelected('examples') then
    Result := Join(Result, 'examples');
  if WizardIsComponentSelected('vscode') then
    Result := Join(Result, 'vscode');
  if WizardIsComponentSelected('devtools') then
    Result := Join(Result, 'devtools');
end;

function BuildSelectedTasks: string;
begin
  Result := '';
  if WizardIsTaskSelected('path_user') then
    Result := Join(Result, 'path_user');
  if WizardIsTaskSelected('path_machine') then
    Result := Join(Result, 'path_machine');
  if WizardIsTaskSelected('assoc_mdr') then
    Result := Join(Result, 'assoc_mdr');
  if WizardIsTaskSelected('desktopicon') then
    Result := Join(Result, 'desktopicon');
  if WizardIsTaskSelected('pipdeps') then
    Result := Join(Result, 'pipdeps');
  if WizardIsTaskSelected('selfcheck') then
    Result := Join(Result, 'selfcheck');
  if WizardIsTaskSelected('check_updates') then
    Result := Join(Result, 'check_updates');
end;

function GetInstalledComponentsValue(Param: string): string;
begin
  Result := BuildSelectedComponents;
end;

function GetInstalledTasksValue(Param: string): string;
begin
  Result := BuildSelectedTasks;
end;

function PathContains(const PathValue: string; const DirValue: string): Boolean;
var
  Needle: string;
  Haystack: string;
begin
  Needle := ';' + NormalizePath(DirValue) + ';';
  Haystack := ';' + UpperCase(PathValue) + ';';
  Result := Pos(Needle, Haystack) > 0;
end;

function AddDirectoryToPath(RootKey: Integer; const DirValue: string): Boolean;
var
  PathValue: string;
begin
  if not RegQueryStringValue(RootKey, 'Environment', 'Path', PathValue) then
    PathValue := '';

  if PathContains(PathValue, DirValue) then
  begin
    Result := False;
    Exit;
  end;

  if (PathValue <> '') and (PathValue[Length(PathValue)] <> ';') then
    PathValue := PathValue + ';';
  PathValue := PathValue + DirValue;

  Result := RegWriteExpandStringValue(RootKey, 'Environment', 'Path', PathValue);
end;

function RemoveDirectoryFromPath(RootKey: Integer; const DirValue: string): Boolean;
var
  PathValue: string;
  OutputValue: string;
  Segment: string;
  P: Integer;
  CompareSegment: string;
  Target: string;
begin
  Result := False;
  if not RegQueryStringValue(RootKey, 'Environment', 'Path', PathValue) then
    Exit;

  OutputValue := '';
  Target := NormalizePath(DirValue);

  while PathValue <> '' do
  begin
    P := Pos(';', PathValue);
    if P > 0 then
    begin
      Segment := Trim(Copy(PathValue, 1, P - 1));
      Delete(PathValue, 1, P);
    end
    else
    begin
      Segment := Trim(PathValue);
      PathValue := '';
    end;

    if Segment = '' then
      Continue;

    CompareSegment := NormalizePath(Segment);
    if CompareSegment = Target then
    begin
      Result := True;
      Continue;
    end;

    if OutputValue <> '' then
      OutputValue := OutputValue + ';';
    OutputValue := OutputValue + Segment;
  end;

  if Result then
    RegWriteExpandStringValue(RootKey, 'Environment', 'Path', OutputValue);
end;

function SaveLauncherFile(const TargetPath: string; const Content: string): Boolean;
begin
  Result := SaveStringToFile(TargetPath, Content, False);
  if not Result then
    Log('Failed to write launcher file: ' + TargetPath);
end;

function WriteLauncherScripts: Boolean;
var
  MidoriCmd: string;
  TerminalCmd: string;
  MaintenanceCmd: string;
  UpdateCmd: string;
  SetupExe: string;
  WroteAll: Boolean;
begin
  WroteAll := True;

  MidoriCmd :=
    '@echo off' + #13#10 +
    'setlocal' + #13#10 +
    'set "MIDORI_HOME=%~dp0"' + #13#10 +
    'if exist "%MIDORI_HOME%\.venv\Scripts\python.exe" (' + #13#10 +
    '  "%MIDORI_HOME%\.venv\Scripts\python.exe" -m midori_cli.main %*' + #13#10 +
    '  exit /b %errorlevel%' + #13#10 +
    ')' + #13#10 +
    'py -m midori_cli.main %*' + #13#10 +
    'if %errorlevel%==9009 (' + #13#10 +
    '  echo Python launcher (py) was not found. Install Python 3.11+ and retry.' + #13#10 +
    ')' + #13#10 +
    'exit /b %errorlevel%' + #13#10;

  TerminalCmd :=
    '@echo off' + #13#10 +
    'setlocal' + #13#10 +
    'set "MIDORI_HOME=%~dp0"' + #13#10 +
    'if exist "%MIDORI_HOME%\.venv\Scripts\python.exe" (' + #13#10 +
    '  "%MIDORI_HOME%\.venv\Scripts\python.exe" -m midori_cli.terminal %*' + #13#10 +
    '  exit /b %errorlevel%' + #13#10 +
    ')' + #13#10 +
    'py -m midori_cli.terminal %*' + #13#10 +
    'if %errorlevel%==9009 (' + #13#10 +
    '  echo Python launcher (py) was not found. Install Python 3.11+ and retry.' + #13#10 +
    ')' + #13#10 +
    'exit /b %errorlevel%' + #13#10;

  UpdateCmd :=
    '@echo off' + #13#10 +
    'start "" "{#MyAppUpdatesURL}"' + #13#10;

  MaintenanceCmd :=
    '@echo off' + #13#10 +
    'setlocal' + #13#10 +
    'set "MIDORI_HOME=%~dp0"' + #13#10 +
    'if exist "%MIDORI_HOME%installer\midori-maintenance.exe" (' + #13#10 +
    '  start "" "%MIDORI_HOME%installer\midori-maintenance.exe"' + #13#10 +
    '  exit /b 0' + #13#10 +
    ')' + #13#10 +
    'echo Local maintenance executable was not found.' + #13#10 +
    'echo Opening MIDORI releases to fetch the latest installer...' + #13#10 +
    'start "" "{#MyAppUpdatesURL}"' + #13#10;

  SetupExe := ExpandConstant('{srcexe}');
  if FileExists(SetupExe) then
    if not CopyFile(SetupExe, ExpandConstant('{app}\installer\midori-maintenance.exe'), False) then
      Log('Failed to copy maintenance executable from setup source.');

  WroteAll := SaveLauncherFile(ExpandConstant('{app}\midori.cmd'), MidoriCmd) and WroteAll;
  WroteAll := SaveLauncherFile(ExpandConstant('{app}\midori-terminal.cmd'), TerminalCmd) and WroteAll;
  WroteAll := SaveLauncherFile(ExpandConstant('{app}\midori-maintenance.cmd'), MaintenanceCmd) and WroteAll;
  WroteAll := SaveLauncherFile(ExpandConstant('{app}\midori-update.cmd'), UpdateCmd) and WroteAll;
  Result := WroteAll;
end;

function TryFindPyLauncherPath(var PyLauncherPath: string): Boolean;
begin
  PyLauncherPath := '';
  if FileExists(ExpandConstant('{sys}\py.exe')) then
    PyLauncherPath := ExpandConstant('{sys}\py.exe')
  else if FileExists(ExpandConstant('{syswow64}\py.exe')) then
    PyLauncherPath := ExpandConstant('{syswow64}\py.exe');

  Result := PyLauncherPath <> '';
end;

function FindPyLauncherPath: string;
begin
  if not TryFindPyLauncherPath(Result) then
    Result := '';
end;

function CanInstallPythonDeps: Boolean;
var
  PyLauncherPath: string;
begin
  Result := TryFindPyLauncherPath(PyLauncherPath);
end;

function CanRunSelfCheck: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\midori.cmd'));
end;

function CanRunTerminalSelfCheck: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\midori-terminal.cmd'));
end;

procedure CleanupPythonMidoriPackage;
var
  PyLauncherPath: string;
  Code: Integer;
begin
  if not TryFindPyLauncherPath(PyLauncherPath) then
  begin
    Log('py.exe not found, skipping pip cleanup.');
    Exit;
  end;

  if Exec(PyLauncherPath, '-m pip uninstall -y midori', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Log(Format('pip uninstall -y midori finished with code %d.', [Code]))
  else
    Log('Failed to execute pip uninstall -y midori.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not WriteLauncherScripts then
      MsgBox(
        'MIDORI installed, but one or more launcher scripts could not be created.' + #13#10 +
        'Run setup again in Repair mode.',
        mbError,
        MB_OK
      );

    if WizardIsTaskSelected('path_user') then
      AddDirectoryToPath(HKCU, ExpandConstant('{app}'));

    if WizardIsTaskSelected('path_machine') and IsAdminInstallMode then
      AddDirectoryToPath(HKLM, ExpandConstant('{app}'));
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    CleanupPythonMidoriPackage;
    RemoveDirectoryFromPath(HKCU, ExpandConstant('{app}'));
    RegDeleteKeyIncludingSubkeys(HKCU, MidoriRegPath);
    if IsAdmin then
    begin
      RemoveDirectoryFromPath(HKLM, ExpandConstant('{app}'));
      RegDeleteKeyIncludingSubkeys(HKLM, MidoriRegPath);
    end;
  end;
end;

