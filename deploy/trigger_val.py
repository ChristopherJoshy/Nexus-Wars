import sys
sys.path.insert(0, '/app')
import db
import jobs
import subprocess
import threading

old_popen = subprocess.Popen
def new_popen(*args, **kwargs):
    if kwargs.get('stderr') == subprocess.DEVNULL:
        kwargs['stderr'] = subprocess.PIPE
    p = old_popen(*args, **kwargs)
    if hasattr(p, 'stderr') and p.stderr:
        def _log():
            try:
                for line in p.stderr:
                    sys.stdout.write(f"BOT_ERR: {line}")
                    sys.stdout.flush()
            except:
                pass
        threading.Thread(target=_log, daemon=True).start()
    return p

subprocess.Popen = new_popen

conn = db.get_conn()
jobs.run_validation(conn, 'fc605dae-3f14-468c-a625-bab3424f3060')
print("Validation finished.")
