Set WshShell = CreateObject("WScript.Shell")
strPath = "D:\AI\.miss_minute\"
pythonPath = "C:\Users\Mirko\AppData\Local\Programs\Python\Python312\python.exe "
WshShell.CurrentDirectory = strPath
WshShell.Run pythonPath & "miss_minute_watcher.py", 0
WshShell.Run pythonPath & "miss_minute_dashboard.py", 0
WshShell.Run pythonPath & "miss_minute_widget.py", 0
