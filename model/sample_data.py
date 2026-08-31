"""Generate synthetic industrial sensor CSVs for demo - no hardware needed"""
import csv, os, random
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent

def generate_normal(equipment_id="BRG-05-A", n=30):
    base = datetime(2026,8,20,8,0,0)
    rows = []
    for i in range(n):
        rows.append({
            "timestamp": (base + timedelta(hours=i*4)).isoformat(),
            "equipment_id": equipment_id,
            "temperature_c": round(random.uniform(48, 62), 1),
            "vibration_mm_s": round(random.uniform(1.2, 2.6), 2),
            "pressure_bar": round(random.uniform(4.8, 5.2), 2),
            "rpm": 1750
        })
    return rows

def generate_anomaly(equipment_id="BRG-05-A", n=30):
    rows = generate_normal(equipment_id, 15)
    base = datetime(2026,8,22,20,0,0)
    for i in range(15, n):
        # progressive bloom: vibration + temp rise
        factor = (i-15)/14
        rows.append({
            "timestamp": (base + timedelta(hours=(i-15)*4)).isoformat(),
            "equipment_id": equipment_id,
            "temperature_c": round(60 + factor*18 + random.uniform(-1,1),1),
            "vibration_mm_s": round(2.5 + factor*3.2 + random.uniform(-0.2,0.2),2),
            "pressure_bar": round(5.0 + factor*0.8 + random.uniform(-0.1,0.1),2),
            "rpm": 1750
        })
    return rows

def write_csv(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp","equipment_id","temperature_c","vibration_mm_s","pressure_bar","rpm"])
        w.writeheader()
        w.writerows(rows)
    return path

if __name__ == "__main__":
    # Seeded, so regenerating the samples does not silently change the demo.
    random.seed(20260831)
    for name, rows in (("sample_normal.csv", generate_normal()),
                       ("sample_anomaly.csv", generate_anomaly())):
        for directory in (HERE, HERE.parent / "frontend" / "public"):
            if directory.exists():
                print(f"wrote {write_csv(str(directory / name), rows)}")
