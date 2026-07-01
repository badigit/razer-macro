Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "C:\Users\Dee\GitHub\razer-macro"
sh.Run """C:\Users\Dee\GitHub\razer-macro\.venv\Scripts\pythonw.exe"" ""C:\Users\Dee\GitHub\razer-macro\razer_macro_daemon.py""", 0, False