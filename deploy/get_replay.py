import subprocess
import sys

pem = r"C:\Users\chris\Downloads\ssh keys\nexus.pem"
cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-i", pem, "ec2-user@16.170.239.106", "sudo docker exec -i deploy-worker-1 python"]

py_code = """
import sys
sys.path.insert(0, '/app')
import storage
import json
try:
    data = storage.get_json('validation/fc605dae-3f14-468c-a625-bab3424f3060.json')
    print(json.dumps(data['info'], indent=2))
except Exception as e:
    print(f"Error: {e}")
"""

p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
out, err = p.communicate(py_code)
print("STDOUT:")
print(out)
print("STDERR:")
print(err)
