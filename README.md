# HotkeyTool

A lightweight Windows hotkey manager and productivity suite. Bind global hotkeys to sequences of actions — open URLs, launch apps, type text, run commands, control media, and more.

## Running the app

The pre-built executable is located in the `dist/` folder:

```
dist/HotkeyTool.exe
```

Just double-click it — no installation required.

## Building from source

```
pip install -r requirements.txt
python main.py
```

## Building the .exe

```
python -m PyInstaller --noconfirm --onefile --windowed --name "HotkeyTool" --icon "assets/hotkeytool.ico" --collect-all customtkinter main.py
```

The output will be placed in `dist/HotkeyTool.exe`.
