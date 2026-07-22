#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "Leadroom"
#define AppPublisher "Borun Studios Ltd"
#define AppUrl "https://borunstudios.co.uk/"
#define AppProjectUrl "https://github.com/bayonsa/Leadroom"
#define AppExeName "Leadroom.exe"

[Setup]
AppId={{5F1B25A7-284C-4EEC-9827-75658E758A55}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppProjectUrl}/issues
AppUpdatesURL={#AppProjectUrl}/releases
DefaultDirName={localappdata}\Programs\Leadroom
DefaultGroupName=Leadroom
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=Leadroom.exe
OutputDir=..\dist
OutputBaseFilename=Leadroom-Setup
SetupIconFile=..\assets\leadroom-icon.ico
UninstallDisplayIcon={app}\Leadroom.exe
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
DisableWelcomePage=no
ShowLanguageDialog=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Leadroom Windows Installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Leadroom.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\leadroom-icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\DEPENDENCY_LICENSES.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\scripts\install-bootstrap.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\clean-install-state.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\setup-local-data.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\import-osm.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\setup-local-updates.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\infra\osm\*"; DestDir: "{app}\infra\osm"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Leadroom"; Filename: "{app}\Leadroom.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\leadroom-icon.ico"
Name: "{autodesktop}\Leadroom"; Filename: "{app}\Leadroom.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\leadroom-icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Leadroom.exe"; Description: "Launch Leadroom"; Flags: nowait postinstall skipifsilent

[Code]
var
  ModePage: TInputOptionWizardPage;
  StoragePage: TInputDirWizardPage;
  DependencyPage: TInputOptionWizardPage;
  BootstrapProgress: TOutputProgressWizardPage;
  BootstrapStatusPath: String;
  BootstrapCompletionPath: String;

function ParamValue(const Name, Default: String): String;
begin
  Result := ExpandConstant('{param:' + Name + '|' + Default + '}');
end;

function ParamEnabled(const Name: String; Default: Boolean): Boolean;
var
  Value: String;
begin
  if Default then Value := '1' else Value := '0';
  Value := Lowercase(ParamValue(Name, Value));
  Result := (Value = '1') or (Value = 'true') or (Value = 'yes');
end;

function IsAbsoluteWindowsPath(const Value: String): Boolean;
begin
  Result := ((Length(Value) >= 3) and (Value[2] = ':') and ((Value[3] = '\') or (Value[3] = '/'))) or
    (Copy(Value, 1, 2) = '\\');
end;

function PowerShellQuote(const Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '"', '""', True);
  Result := '"' + Result + '"';
end;

procedure ApplyModeSelection;
var
  FullLocal: Boolean;
begin
  FullLocal := ModePage.SelectedValueIndex = 1;
  DependencyPage.CheckListBox.ItemEnabled[3] := FullLocal;
  if not FullLocal then DependencyPage.Values[3] := False;
  if FullLocal then
    DependencyPage.SubCaptionLabel.Caption :=
      'Full Local can download roughly 2 GB and use 25-40 GB after import. It requires WSL2, Ubuntu, PostgreSQL, and PostGIS.'
  else
    DependencyPage.SubCaptionLabel.Caption :=
      'Recommended components are downloaded only with your approval. Existing installations are reused.';
end;

procedure InitializeWizard;
var
  DefaultData, DefaultDownloads, RequestedMode: String;
begin
  DefaultData := ExpandConstant('{localappdata}\Leadroom');
  DefaultDownloads := ExpandConstant('{localappdata}\Leadroom\downloads');
  RequestedMode := Lowercase(ParamValue('INSTALLMODE', 'standard'));

  ModePage := CreateInputOptionPage(wpSelectDir,
    'Choose the Leadroom experience',
    'Start lightweight or prepare the full local discovery stack.',
    'Standard is recommended. Full Local is intended for powerful Windows computers with plenty of disk space.',
    True, False);
  ModePage.Add('Standard - web discovery and local AI enrichment');
  ModePage.Add('Full Local - add private OpenStreetMap discovery');
  ModePage.SelectedValueIndex := 0;
  if RequestedMode = 'full' then ModePage.SelectedValueIndex := 1;

  StoragePage := CreateInputDirPage(ModePage.ID,
    'Choose where Leadroom stores data',
    'Keep the application small and place workspace data or large downloads on any drive.',
    'The first folder holds the SQLite workspace. The second holds models, browser files, cache, and optional map data.',
    False, 'New Folder');
  StoragePage.Add('Workspace data:');
  StoragePage.Add('Large downloads:');
  StoragePage.Values[0] := ParamValue('DATAROOT', DefaultData);
  StoragePage.Values[1] := ParamValue('DOWNLOADSROOT', DefaultDownloads);

  DependencyPage := CreateInputOptionPage(StoragePage.ID,
    'Prepare this computer',
    'Choose the components Leadroom may download.',
    'Recommended components are downloaded only with your approval. Existing installations are reused.',
    False, False);
  DependencyPage.Add('Install Microsoft Edge WebView2 Runtime if missing');
  DependencyPage.Add('Install Ollama if missing');
  DependencyPage.Add('Download the recommended llama3.2:3b model');
  DependencyPage.Add('Download and prepare the Full Local OpenStreetMap stack');
  DependencyPage.Values[0] := ParamEnabled('INSTALL_WEBVIEW', True);
  DependencyPage.Values[1] := ParamEnabled('INSTALL_OLLAMA', True);
  DependencyPage.Values[2] := ParamEnabled('DOWNLOAD_MODEL', True);
  DependencyPage.Values[3] := ParamEnabled('SETUP_LOCAL_DATA', False);
  ApplyModeSelection;

  BootstrapProgress := CreateOutputProgressPage(
    'Preparing Leadroom',
    'Progress for each selected component appears below.');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ModePage.ID then ApplyModeSelection;
  if CurPageID = StoragePage.ID then begin
    if not IsAbsoluteWindowsPath(StoragePage.Values[0]) then begin
      MsgBox('Choose an absolute workspace folder, such as D:\LeadroomData\workspace.', mbError, MB_OK);
      Result := False;
    end else if not IsAbsoluteWindowsPath(StoragePage.Values[1]) then begin
      MsgBox('Choose an absolute downloads folder, such as D:\LeadroomData\downloads.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function BootstrapArguments: String;
var
  Mode: String;
begin
  if ModePage.SelectedValueIndex = 1 then Mode := 'FullLocal' else Mode := 'Standard';
  Result := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
    PowerShellQuote(ExpandConstant('{app}\scripts\install-bootstrap.ps1')) +
    ' -Mode ' + Mode +
    ' -InstallRoot ' + PowerShellQuote(ExpandConstant('{app}')) +
    ' -DataRoot ' + PowerShellQuote(StoragePage.Values[0]) +
    ' -DownloadsRoot ' + PowerShellQuote(StoragePage.Values[1]) +
    ' -Model ' + PowerShellQuote('llama3.2:3b') +
    ' -StatusPath ' + PowerShellQuote(BootstrapStatusPath) +
    ' -CompletionPath ' + PowerShellQuote(BootstrapCompletionPath);
  if DependencyPage.Values[0] then Result := Result + ' -InstallWebView';
  if DependencyPage.Values[1] then Result := Result + ' -InstallOllama';
  if DependencyPage.Values[2] then Result := Result + ' -DownloadModel';
  if DependencyPage.Values[3] then Result := Result + ' -SetupLocalData';
  if ParamEnabled('FORCE_STORAGE', False) then Result := Result + ' -ForceStorage';
end;

procedure RefreshBootstrapProgress;
var
  Lines: TArrayOfString;
  Percent: Integer;
begin
  if not LoadStringsFromFile(BootstrapStatusPath, Lines) then Exit;
  if GetArrayLength(Lines) < 3 then Exit;
  Percent := StrToIntDef(Trim(Lines[0]), 0);
  if Percent < 0 then Percent := 0;
  if Percent > 100 then Percent := 100;
  BootstrapProgress.SetText(Trim(Lines[1]), Trim(Lines[2]));
  BootstrapProgress.SetProgress(Percent, 100);
  WizardForm.Refresh;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  CompletionLines: TArrayOfString;
begin
  if CurStep <> ssPostInstall then Exit;
  BootstrapStatusPath := ExpandConstant('{tmp}\leadroom-bootstrap.status');
  BootstrapCompletionPath := ExpandConstant('{tmp}\leadroom-bootstrap.complete');
  DeleteFile(BootstrapStatusPath);
  DeleteFile(BootstrapCompletionPath);
  BootstrapProgress.SetText('Checking this computer',
    'Preparing the selected components');
  BootstrapProgress.SetProgress(0, 100);
  BootstrapProgress.Show;
  try
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      BootstrapArguments, '', SW_HIDE, ewNoWait, ResultCode) then
      RaiseException('Windows could not start the Leadroom setup helper.');
    while not FileExists(BootstrapCompletionPath) do begin
      Sleep(200);
      RefreshBootstrapProgress;
    end;
    RefreshBootstrapProgress;
    if not LoadStringsFromFile(BootstrapCompletionPath, CompletionLines) then
      RaiseException('Leadroom setup did not report a completion status.');
    if (GetArrayLength(CompletionLines) < 1) or (Trim(CompletionLines[0]) <> '0') then
      RaiseException('Leadroom prerequisites could not be prepared. Review ' +
        ExpandConstant('{localappdata}\Leadroom\logs\install.log') + ' and run setup again.');
  finally
    DeleteFile(BootstrapStatusPath);
    DeleteFile(BootstrapCompletionPath);
    BootstrapProgress.Hide;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep <> usUninstall then Exit;
  if SuppressibleMsgBox(
    'Keep your Leadroom workspace, downloaded models, cache, and local map data?' + #13#10 + #13#10 +
    'Choose Yes to preserve them for a future install. Choose No for a clean removal.',
    mbConfirmation, MB_YESNO, IDYES) = IDNO then
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
      PowerShellQuote(ExpandConstant('{app}\scripts\clean-install-state.ps1')) +
      ' -IncludeWorkspaceData -IncludeDownloads -Confirm',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
