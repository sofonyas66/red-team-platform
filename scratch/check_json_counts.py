import json
import glob
import os

folder = "/home/klythron/Documents/projects/BloodHoundAD/Bloodhound-CE-Sample-Data/north_extracted"
files = glob.glob(os.path.join(folder, "*.json"))

print("JSON file counts:")
for fpath in sorted(files):
    with open(fpath) as f:
        raw = json.load(f)
    meta = raw.get("meta", {})
    mtype = meta.get("type")
    count = len(raw.get("data", []))
    print(f"  File: {os.path.basename(fpath)}, Type: {mtype}, Count: {count}")
