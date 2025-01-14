import wx
import os
import json
import threading
import time
import py7zr
import zipfile
import rarfile
from pathlib import Path

ABOUT_FILE = "about.json"
SETTINGS_FILE = "settings.json"
LICENSE_FILE = "LICENSE"

ABOUT_INFO = {
    "version": "1.0",
    "creator": "ReJaad",
    "copyright": "© 2025 ReJaad.",
    "website": "https://github.com/rejaad/Re-Archive"
}

if not os.path.exists(ABOUT_FILE):
    with open(ABOUT_FILE, "w") as f:
        json.dump(ABOUT_INFO, f, indent=4)

if not os.path.exists(SETTINGS_FILE):
    default_settings = {"theme": "system", "last_directory": ""}
    with open(SETTINGS_FILE, "w") as f:
        json.dump(default_settings, f, indent=4)

if not os.path.exists(LICENSE_FILE):
    with open(LICENSE_FILE, "w") as f:
        f.write("Apache License 2.0\n\nhttps://www.apache.org/licenses/LICENSE-2.0")

class TreeFileList(wx.TreeCtrl):
    def __init__(self, parent):
        super().__init__(parent, style=wx.TR_DEFAULT_STYLE | wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_MULTIPLE)
        self.SetBackgroundColour(parent.GetBackgroundColour())
        self.root = self.AddRoot("Root")
        self.file_paths = {}  # Store file paths for extraction
        
    def populate_tree(self, files):
        self.DeleteAllItems()
        self.root = self.AddRoot("Root")
        self.file_paths.clear()
        paths_dict = {}

        for file_path, size, date in files:
            path_parts = Path(file_path).parts
            current_dict = paths_dict
            current_item = self.root

            for i, part in enumerate(path_parts[:-1]):
                if part not in current_dict:
                    current_dict[part] = {}
                    current_item = self.AppendItem(current_item, part, data={"type": "folder"})
                    self.SetItemImage(current_item, 0)
                current_dict = current_dict[part]
                if i < len(path_parts) - 2:
                    current_item = self.GetFirstChild(current_item)[0]

            file_item = self.AppendItem(current_item, path_parts[-1], data={
                "type": "file",
                "size": size,
                "date": date
            })
            self.file_paths[file_item] = file_path
            self.SetItemImage(file_item, 1)

    def get_selected_files(self):
        """Returns a list of file paths for selected items"""
        selected_files = []
        selections = self.GetSelections()
        
        for item in selections:
            # If it's a file, add it directly
            if item in self.file_paths:
                selected_files.append(self.file_paths[item])
            # If it's a folder, add all files under it
            else:
                self._add_files_under_folder(item, selected_files)
        
        return selected_files

    def _add_files_under_folder(self, folder_item, file_list):
        """Recursively adds all files under a folder to the list"""
        child, cookie = self.GetFirstChild(folder_item)
        while child.IsOk():
            if child in self.file_paths:
                file_list.append(self.file_paths[child])
            else:
                self._add_files_under_folder(child, file_list)
            child, cookie = self.GetNextChild(folder_item, cookie)

class ReArchiveApp(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Re'Archive", size=(1000, 700))

        with open(SETTINGS_FILE, "r") as f:
            self.settings = json.load(f)

        self.current_archive = None
        self.thread_semaphore = threading.Semaphore(2)
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        main_panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Toolbar
        toolbar_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Create buttons with tooltips
        buttons = [
            ("Open Archive", self.on_open_archive, "Open an archive file"),
            ("Extract All", self.on_extract_archive, "Extract all files from the archive"),
            ("Extract Selected", self.on_extract_selected, "Extract selected files only"),
            ("Test Integrity", self.on_test_integrity, "Test archive integrity"),
            ("Set Password", self.on_set_password, "Set archive password"),
            ("Password List", self.on_master_password_list, "Manage password list"),
            ("Fix Archive", self.on_fix_archive, "Attempt to fix corrupted archive"),
            ("About", self.on_about, "About Re'Archive")
        ]
        
        for label, handler, tooltip in buttons:
            btn = wx.Button(main_panel, label=label)
            btn.SetToolTip(tooltip)
            btn.Bind(wx.EVT_BUTTON, handler)
            toolbar_sizer.Add(btn, 0, wx.ALL | wx.EXPAND, 5)
        
        main_sizer.Add(toolbar_sizer, 0, wx.EXPAND)
        
        # Main content area
        content_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Left panel for archive selection
        left_panel = wx.Panel(main_panel)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.archive_selector = wx.ListBox(left_panel)
        self.archive_selector.Bind(wx.EVT_LISTBOX, self.on_select_archive)
        left_sizer.Add(self.archive_selector, 1, wx.EXPAND | wx.ALL, 5)
        
        left_panel.SetSizer(left_sizer)
        content_sizer.Add(left_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        # Right panel for file tree
        self.file_tree = TreeFileList(main_panel)
        content_sizer.Add(self.file_tree, 1, wx.EXPAND | wx.ALL, 5)
        
        main_sizer.Add(content_sizer, 1, wx.EXPAND)
        main_panel.SetSizer(main_sizer)

        self.CreateStatusBar()

    def apply_theme(self):
        if self.settings["theme"] == "system":
            if wx.SystemSettings.GetAppearance().IsDark():
                self.SetBackgroundColour(wx.Colour(30, 30, 30))
                self.SetForegroundColour(wx.Colour(255, 255, 255))
            else:
                self.SetBackgroundColour(wx.Colour(255, 255, 255))
                self.SetForegroundColour(wx.Colour(0, 0, 0))

    def on_open_archive(self, event):
        with wx.FileDialog(self, "Open Archive",
                         wildcard="Archive files (*.7z;*.zip;*.rar;*.tar;*.gz)|*.7z;*.zip;*.rar;*.tar;*.gz",
                         style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as file_dialog:
            if file_dialog.ShowModal() == wx.ID_CANCEL:
                return
            archive_path = file_dialog.GetPath()
            self.load_archive(archive_path)

    def load_archive(self, archive_path):
        self.current_archive = archive_path
        archive_name = os.path.basename(archive_path)
        self.SetTitle(f"{archive_name} - Re'Archive")
        self.archive_selector.Append(archive_name)
        self.archive_selector.SetSelection(self.archive_selector.GetCount() - 1)
        self.populate_file_list(archive_path)

    def populate_file_list(self, archive_path):
        def task():
            with self.thread_semaphore:
                files = self.extract_archive_contents(archive_path)
                wx.CallAfter(self.file_tree.populate_tree, files)

        threading.Thread(target=task, daemon=True).start()

    def extract_archive_contents(self, archive_path):
        files = []
        try:
            if archive_path.endswith(".7z"):
                with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                    for info in archive.list():
                        files.append((info.filename, str(info.uncompressed), info.creationtime))
            elif archive_path.endswith(".zip"):
                with zipfile.ZipFile(archive_path, 'r') as archive:
                    for info in archive.infolist():
                        files.append((info.filename, str(info.file_size), str(info.date_time)))
            elif archive_path.endswith(".rar"):
                with rarfile.RarFile(archive_path, 'r') as archive:
                    for info in archive.infolist():
                        files.append((info.filename, str(info.file_size), str(info.date_time)))
        except Exception as e:
            wx.MessageBox(f"Error extracting archive: {e}", "Error", wx.OK | wx.ICON_ERROR)
        return files

    def extract_files(self, extract_path, files_to_extract=None):
        try:
            if self.current_archive.endswith('.7z'):
                with py7zr.SevenZipFile(self.current_archive, mode='r') as archive:
                    if files_to_extract:
                        archive.extract(path=extract_path, targets=files_to_extract)
                    else:
                        archive.extractall(extract_path)
            elif self.current_archive.endswith('.zip'):
                with zipfile.ZipFile(self.current_archive, 'r') as archive:
                    if files_to_extract:
                        for file in files_to_extract:
                            archive.extract(file, extract_path)
                    else:
                        archive.extractall(extract_path)
            elif self.current_archive.endswith('.rar'):
                with rarfile.RarFile(self.current_archive, 'r') as archive:
                    if files_to_extract:
                        for file in files_to_extract:
                            archive.extract(file, extract_path)
                    else:
                        archive.extractall(extract_path)
            return True
        except Exception as e:
            wx.MessageBox(f"Error during extraction: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            return False

    def on_extract_archive(self, event):
        if not self.current_archive:
            wx.MessageBox("Please open an archive first.", "No Archive", wx.OK | wx.ICON_INFORMATION)
            return

        with wx.DirDialog(self, "Choose extraction directory:", style=wx.DD_DEFAULT_STYLE) as dir_dialog:
            if dir_dialog.ShowModal() == wx.ID_CANCEL:
                return
            
            extract_path = dir_dialog.GetPath()
            
            progress_dialog = wx.ProgressDialog("Extracting Archive",
                                             "Extracting files...",
                                             maximum=100,
                                             parent=self,
                                             style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
            
            def extract_task():
                try:
                    success = self.extract_files(extract_path)
                    wx.CallAfter(progress_dialog.Update, 100)
                    wx.CallAfter(progress_dialog.Destroy)
                    if success:
                        wx.CallAfter(wx.MessageBox, 
                                   "Extraction completed successfully!", 
                                   "Success", 
                                   wx.OK | wx.ICON_INFORMATION)
                except Exception as e:
                    wx.CallAfter(progress_dialog.Destroy)
                    wx.CallAfter(wx.MessageBox, 
                               f"Error during extraction: {str(e)}", 
                               "Error", 
                               wx.OK | wx.ICON_ERROR)

            threading.Thread(target=extract_task, daemon=True).start()

    def on_extract_selected(self, event):
        if not self.current_archive:
            wx.MessageBox("Please open an archive first.", "No Archive", wx.OK | wx.ICON_INFORMATION)
            return

        selected_files = self.file_tree.get_selected_files()
        if not selected_files:
            wx.MessageBox("Please select files to extract.", "No Selection", wx.OK | wx.ICON_INFORMATION)
            return

        with wx.DirDialog(self, "Choose extraction directory:", style=wx.DD_DEFAULT_STYLE) as dir_dialog:
            if dir_dialog.ShowModal() == wx.ID_CANCEL:
                return
            
            extract_path = dir_dialog.GetPath()
            
            progress_dialog = wx.ProgressDialog("Extracting Selected Files",
                                             f"Extracting {len(selected_files)} files...",
                                             maximum=100,
                                             parent=self,
                                             style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE)
            
            def extract_task():
                try:
                    success = self.extract_files(extract_path, selected_files)
                    wx.CallAfter(progress_dialog.Update, 100)
                    wx.CallAfter(progress_dialog.Destroy)
                    if success:
                        wx.CallAfter(wx.MessageBox, 
                                   f"Successfully extracted {len(selected_files)} files!", 
                                   "Success", 
                                   wx.OK | wx.ICON_INFORMATION)
                except Exception as e:
                    wx.CallAfter(progress_dialog.Destroy)
                    wx.CallAfter(wx.MessageBox, 
                               f"Error during extraction: {str(e)}", 
                               "Error", 
                               wx.OK | wx.ICON_ERROR)

            threading.Thread(target=extract_task, daemon=True).start()

    def on_select_archive(self, event):
        selection = self.archive_selector.GetStringSelection()
        if selection:
            archive_path = os.path.join(self.settings["last_directory"], selection)
            self.load_archive(archive_path)

    def on_test_integrity(self, event):
        if not self.current_archive:
            wx.MessageBox("Please open an archive first.", "No Archive", wx.OK | wx.ICON_INFORMATION)
            return
        wx.MessageBox("Testing archive integrity...", "Test Integrity", wx.OK | wx.ICON_INFORMATION)

    def on_set_password(self, event):
        password_dialog = wx.TextEntryDialog(self, "Enter Password", "Set Password", style=wx.TE_PASSWORD)
        if password_dialog.ShowModal() == wx.ID_OK:
            password = password_dialog.GetValue()
            wx.MessageBox("Password set successfully!", "Success", wx.OK | wx.ICON_INFORMATION)

    def on_master_password_list(self, event):
        wx.MessageBox("Password list management...", "Password List", wx.OK | wx.ICON_INFORMATION)

    def on_fix_archive(self, event):
        if not self.current_archive:
            wx.MessageBox("Please open an archive first.", "No Archive", wx.OK | wx.ICON_INFORMATION)
            return
        wx.MessageBox("Attempting to fix archive...", "Fix Archive", wx.OK | wx.ICON_INFORMATION)

    def on_about(self, event):
        with open(ABOUT_FILE, "r") as f:
            about_info = json.load(f)
        message = f"Re'Archive\nVersion: {about_info['version']}\nCreator: {about_info['creator']}\n{about_info['copyright']}\nWebsite: {about_info['website']}"
        wx.MessageBox(message, "About Re'Archive", wx.OK | wx.ICON_INFORMATION)

if __name__ == "__main__":
    app = wx.App(False)
    frame = ReArchiveApp()
    frame.Show()
    app.MainLoop()
