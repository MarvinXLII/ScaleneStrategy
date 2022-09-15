# -*- mode: python -*-

block_cipher = None

a = Analysis(
    [
        'gui.py',
        'release.py',
        'src/Assets.py',
        'src/Growth.py',
        'src/Items.py',
        'src/Jobs.py',
        'src/Level.py',
        'src/Lub.py',
        'src/Maps.py',
        'src/Pak.py',
        'src/Positions.py',
        'src/Randomizer.py',
        'src/Text.py',
        'src/TileMap.py',
        'src/Units.py',
        'src/Utility.py',
        'src/Weapons.py',
        'src/World.py',
    ],
    pathex=[],
    binaries=[],
    datas=[
        ('json/*.json', 'json'),
        ('txt/*.txt', 'txt'),
        ('patch/*.patch', 'patch'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
    name='mybuild'
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ScaleneStrategy.exe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False
)
