import subprocess
import sys

# اجرای همزمان هر دو اسکریپت در یک کانتینر
p1 = subprocess.Popen([sys.executable, "main.py"])
p2 = subprocess.Popen([sys.executable, "retention.py"])

# منتظر ماندن برای اجرای مداوم
try:
    p1.wait()
    p2.wait()
except KeyboardInterrupt:
    p1.terminate()
    p2.terminate()
