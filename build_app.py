import PyInstaller.__main__
import os
import shutil

# Название выходного файла
APP_NAME = "MediaHub"
MAIN_SCRIPT = "main.py"

# Проверка наличия бинарников
if not os.path.exists("ffmpeg.exe") or not os.path.exists("ffprobe.exe"):
    print("WARNING: ffmpeg.exe or ffprobe.exe not found in project root!")
    print("Bundling might complete, but downloading features will fail if not provided.")

# Параметры сборки
params = [
    MAIN_SCRIPT,
    '--name=%s' % APP_NAME,
    '--onefile',         # Собрать в один EXE
    '--noconsole',       # Без консольного окна
    '--clean',           # Очистить кэш перед сборкой
    
    # Добавление ffmpeg и ffprobe внутрь EXE
    '--add-data=ffmpeg.exe;.',
    '--add-data=ffprobe.exe;.',
    
    # Рекурсивный поиск зависимостей (на всякий случай)
    '--hidden-import=customtkinter',
    '--hidden-import=vlc',
    '--hidden-import=yt_dlp',
]

print(f"Starting build for {APP_NAME}...")
PyInstaller.__main__.run(params)
print(f"Build finished! Check the 'dist' folder for {APP_NAME}.exe")
