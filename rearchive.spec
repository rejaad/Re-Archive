a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('about.json', '.'),
        ('settings.json', '.'),
        ('LICENSE', '.')
    ],
    hiddenimports=['wx'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='ReArchive',
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon='icon.ico',  # You'll need to create/add this
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)