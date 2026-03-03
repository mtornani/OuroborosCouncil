@echo off
cd /d "D:\AI\.miss_minute"
echo Starting Miss Minute System (Jarvis Edition)...
start /B "" "C:\Users\Mirko\AppData\Local\Programs\Python\Python312\python.exe" miss_minute_watcher.py
start /B "" "C:\Users\Mirko\AppData\Local\Programs\Python\Python312\python.exe" miss_minute_widget.py
echo System active. Have a productive day, sugar!
exit
