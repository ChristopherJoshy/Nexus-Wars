import subprocess
p = subprocess.Popen(["nsjail", "-C", "/etc/nsjail/nsjail.cfg", "-R", "/tmp:/work", "--", "/usr/local/bin/python3", "/work/chris.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
out, err = p.communicate('{"step": 0, "planets": [], "fleets": [], "player": 0, "angular_velocity": 0.05, "initial_planets": []}\n')
print("STDOUT:", out)
print("STDERR:", err)
print("RETURNCODE:", p.returncode)
