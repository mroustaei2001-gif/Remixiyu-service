import subprocess
import sys
import time


SCRIPTS = ["main.py", "retention.py", "reel_bot.py"]


def start_process(script_name: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, script_name])


def main():
    processes = {name: start_process(name) for name in SCRIPTS}

    try:
        while True:
            for name, proc in list(processes.items()):
                code = proc.poll()
                if code is not None:
                    print(f"[Runner] فرآیند {name} با کد {code} متوقف شد. در حال راه‌اندازی مجدد...", flush=True)
                    time.sleep(5)
                    processes[name] = start_process(name)
            time.sleep(3)
    except KeyboardInterrupt:
        print("[Runner] در حال بستن فرآیندها...", flush=True)
        for proc in processes.values():
            if proc.poll() is None:
                proc.terminate()
        for proc in processes.values():
            proc.wait()


if __name__ == "__main__":
    main()
