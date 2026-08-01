import resource
import sys
import subprocess

try:
    resource.setrlimit(resource.RLIMIT_AS, (536870912, 536870912))
except Exception as e:
    print("Failed to set rlimit:", e)

try:
    p = subprocess.Popen([sys.executable, "/tmp/chris.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate("{}\n")
    print("STDOUT:", out)
    print("STDERR:", err)
    print("Return code:", p.returncode)
except Exception as e:
    print("Error:", e)
