import os
import sqlite3

path = os.path.expandvars(r"%LOCALAPPDATA%\budget\dev\bronze.db").replace("\\", "/")
c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
iso = "substr(d,7,4)||'-'||substr(d,4,2)||'-'||substr(d,1,2)"
q = f"""
select r.declared_account_id, r.outcome, r.exported_on, r.started_at,
  (select max({iso}) from (select json_extract(fields,'$.Dato') d
     from source_records s where s.payload_id = r.payload_id)) last_tx
from import_runs r order by 1, r.started_at
"""
for row in c.execute(q):
    print(*row, sep=" | ")
