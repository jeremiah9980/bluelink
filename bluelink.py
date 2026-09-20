#!/usr/bin/env python3
"""Ioniq 5 Bluelink runner for GitHub Actions.

Usage:
  python bluelink.py status              # read Hyundai's cached status (does not wake the car)
  python bluelink.py refresh             # ask the car for fresh data (wakes the car; use sparingly)
  python bluelink.py lock | unlock
  python bluelink.py climate_start --temp 70 --duration 10 [--defrost]
  python bluelink.py climate_stop
  python bluelink.py charge_start | charge_stop
  python bluelink.py charge_limits --ac 80 --dc 80

Credentials come from env vars: BLUELINK_USERNAME, BLUELINK_PASSWORD, BLUELINK_PIN,
optional BLUELINK_VIN (if the account has more than one car).
Set BLUELINK_MOCK=1 to run with fake data (no Hyundai login).

Output goes to ./data/: status.json, last_command.json, history.jsonl
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
import time
from pathlib import Path

DATA = Path(os.environ.get("BLUELINK_DATA_DIR", "data"))
HISTORY_MAX = 1500  # ~2 months of hourly points
NOW = lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

COMMANDS = [
    "status", "refresh", "lock", "unlock", "climate_start", "climate_stop",
    "charge_start", "charge_stop", "charge_limits",
]


def g(v, name, default=None):
    try:
        val = getattr(v, name)
    except Exception:
        return default
    if hasattr(val, "value") and not isinstance(val, (int, float, str, bool)):
        val = getattr(val, "value", val)  # enums
    if isinstance(val, (dt.datetime, dt.date)):
        return val.isoformat()
    return val if val is not None else default


def snapshot(v) -> dict:
    """Flatten the library's Vehicle object into plain JSON for the dashboard."""
    doors_open = {k: g(v, k + "_is_open") for k in (
        "front_left_door", "front_right_door", "back_left_door", "back_right_door")}
    windows_open = {k: g(v, k + "_is_open") for k in (
        "front_left_window", "front_right_window", "back_left_window", "back_right_window")}
    tires = {k: g(v, f"tire_pressure_{k}_warning_is_on") for k in (
        "front_left", "front_right", "rear_left", "rear_right")}
    return {
        "name": g(v, "name"), "model": g(v, "model"), "year": g(v, "year"),
        "vin_last6": (g(v, "VIN") or g(v, "id") or "")[-6:],
        "last_updated_at": g(v, "last_updated_at"),
        "fetched_at": NOW(),
        "battery": {
            "percent": g(v, "ev_battery_percentage"),
            "range": g(v, "ev_driving_range"), "range_unit": g(v, "ev_driving_range_unit", "mi"),
            "is_charging": g(v, "ev_battery_is_charging"),
            "is_plugged_in": g(v, "ev_battery_is_plugged_in"),
            "charging_power_kw": g(v, "ev_charging_power"),
            "charge_limit_ac": g(v, "ev_charge_limits_ac"),
            "charge_limit_dc": g(v, "ev_charge_limits_dc"),
            "minutes_to_full": g(v, "ev_estimated_current_charge_duration"),
            "soh_percent": g(v, "ev_battery_soh_percentage"),
            "aux_12v_percent": g(v, "car_battery_percentage"),
            "charge_port_open": g(v, "ev_charge_port_door_is_open"),
        },
        "security": {
            "is_locked": g(v, "is_locked"),
            "doors_open": doors_open,
            "windows_open": windows_open,
            "trunk_open": g(v, "trunk_is_open"),
            "hood_open": g(v, "hood_is_open"),
            "sunroof_open": g(v, "sunroof_is_open"),
        },
        "climate": {
            "is_on": g(v, "air_control_is_on"),
            "set_temp": g(v, "air_temperature"),
            "defrost_on": g(v, "defrost_is_on"),
            "outside_temp": g(v, "outside_temperature"),
        },
        "tires_warning": tires,
        "odometer": g(v, "odometer"), "odometer_unit": g(v, "odometer_unit", "mi"),
        "location": {
            "lat": g(v, "location_latitude"), "lon": g(v, "location_longitude"),
            "updated_at": g(v, "location_last_updated_at"),
        },
    }


# ---------------------------------------------------------------- mock mode
class MockVehicle:
    def __init__(self):
        r = random.Random(int(time.time() // 3600))
        self.name, self.model, self.year, self.VIN = "Ioniq 5", "IONIQ 5", 2024, "KM8KRDAF0RU000000"
        self.last_updated_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=r.randint(3, 50))
        self.ev_battery_percentage = r.randint(38, 92)
        self.ev_driving_range = round(self.ev_battery_percentage * 2.6)
        self.ev_driving_range_unit = "mi"
        self.ev_battery_is_plugged_in = r.random() < 0.5
        self.ev_battery_is_charging = self.ev_battery_is_plugged_in and r.random() < 0.7
        self.ev_charging_power = 7.2 if self.ev_battery_is_charging else 0
        self.ev_charge_limits_ac, self.ev_charge_limits_dc = 80, 80
        self.ev_estimated_current_charge_duration = 210 if self.ev_battery_is_charging else 0
        self.ev_battery_soh_percentage = 97
        self.car_battery_percentage = 82
        self.ev_charge_port_door_is_open = self.ev_battery_is_plugged_in
        self.is_locked = True
        for d in ("front_left", "front_right", "back_left", "back_right"):
            setattr(self, f"{d}_door_is_open", False)
            setattr(self, f"{d}_window_is_open", False)
            setattr(self, f"tire_pressure_{d.replace('back', 'rear')}_warning_is_on", False)
        self.trunk_is_open = self.hood_is_open = self.sunroof_is_open = False
        self.air_control_is_on, self.air_temperature, self.defrost_is_on = False, 70, False
        self.outside_temperature = 84
        self.odometer, self.odometer_unit = 18342, "mi"
        self.location_latitude, self.location_longitude = 29.3780, -95.1055
        self.location_last_updated_at = self.last_updated_at


# ---------------------------------------------------------------- helpers
def write_json(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, indent=2, default=str))


def append_history(snap):
    b = snap["battery"]
    point = {"t": snap["last_updated_at"] or snap["fetched_at"], "soc": b["percent"],
             "range": b["range"], "charging": b["is_charging"], "odo": snap["odometer"]}
    path = DATA / "history.jsonl"
    lines = path.read_text().splitlines() if path.exists() else []
    if lines:
        try:
            if json.loads(lines[-1]).get("t") == point["t"]:
                return  # car hasn't reported anything new since last run
        except ValueError:
            pass
    lines.append(json.dumps(point))
    path.write_text("\n".join(lines[-HISTORY_MAX:]) + "\n")


def connect():
    from hyundai_kia_connect_api import VehicleManager
    need = ["BLUELINK_USERNAME", "BLUELINK_PASSWORD", "BLUELINK_PIN"]
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        sys.exit(f"Missing secrets: {', '.join(missing)}")
    vm = VehicleManager(region=3, brand=2,  # 3 = USA, 2 = Hyundai
                        username=os.environ["BLUELINK_USERNAME"],
                        password=os.environ["BLUELINK_PASSWORD"],
                        pin=os.environ["BLUELINK_PIN"])
    vm.check_and_refresh_token()
    if not vm.vehicles:
        sys.exit("Login worked but no vehicles are on this Bluelink account.")
    want = (os.environ.get("BLUELINK_VIN") or "").upper()
    vid = next((k for k, v in vm.vehicles.items()
                if want and want in (str(k).upper(), str(getattr(v, "VIN", "")).upper())),
               next(iter(vm.vehicles)))
    return vm, vid


def run(args):
    started = NOW()
    result = {"action": args.action, "requested_at": started, "status": "SUCCESS", "detail": ""}

    if os.environ.get("BLUELINK_MOCK") == "1":
        v = MockVehicle()
        if args.action == "lock": v.is_locked = True
        if args.action == "unlock": v.is_locked = False
        if args.action == "climate_start": v.air_control_is_on, v.air_temperature = True, args.temp
        if args.action == "charge_limits": v.ev_charge_limits_ac, v.ev_charge_limits_dc = args.ac, args.dc
        result["detail"] = "mock mode"
    else:
        from hyundai_kia_connect_api import ClimateRequestOptions
        vm, vid = connect()
        action_id = None
        if args.action == "refresh":
            vm.force_refresh_vehicle_state(vid)
        elif args.action == "lock":
            action_id = vm.lock(vid)
        elif args.action == "unlock":
            action_id = vm.unlock(vid)
        elif args.action == "climate_start":
            opts = ClimateRequestOptions(set_temp=args.temp, duration=args.duration,
                                         defrost=args.defrost, climate=True,
                                         heating=1 if args.defrost else 0)
            action_id = vm.start_climate(vid, opts)
        elif args.action == "climate_stop":
            action_id = vm.stop_climate(vid)
        elif args.action == "charge_start":
            action_id = vm.start_charge(vid)
        elif args.action == "charge_stop":
            action_id = vm.stop_charge(vid)
        elif args.action == "charge_limits":
            action_id = vm.set_charge_limits(vid, args.ac, args.dc)

        if action_id:
            try:
                st = vm.check_action_status(vid, action_id, synchronous=True, timeout=120)
                result["status"] = getattr(st, "value", str(st))
            except Exception as e:  # the command was sent; confirmation polling failed
                result["status"], result["detail"] = "UNKNOWN", f"sent, but could not confirm: {e}"
            time.sleep(5)
        vm.update_vehicle_with_cached_state(vid)
        v = vm.get_vehicle(vid)

    snap = snapshot(v)
    write_json("status.json", snap)
    append_history(snap)
    if args.action != "status":
        result["finished_at"] = NOW()
        write_json("last_command.json", result)
    print(json.dumps({"result": result, "battery": snap["battery"]["percent"],
                      "locked": snap["security"]["is_locked"]}, default=str))
    if result["status"] in ("FAILED", "TIMEOUT"):
        sys.exit(f"Car reported {result['status']} for {args.action}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=COMMANDS)
    p.add_argument("--temp", type=int, default=70, help="climate temp °F (62-82)")
    p.add_argument("--duration", type=int, default=10, help="climate minutes (1-30)")
    p.add_argument("--defrost", action="store_true")
    p.add_argument("--ac", type=int, default=80, help="AC charge limit % (50-100, steps of 10)")
    p.add_argument("--dc", type=int, default=80, help="DC charge limit % (50-100, steps of 10)")
    a = p.parse_args()
    a.temp = max(62, min(82, a.temp))
    a.duration = max(1, min(30, a.duration))
    a.ac = max(50, min(100, round(a.ac / 10) * 10))
    a.dc = max(50, min(100, round(a.dc / 10) * 10))
    run(a)


if __name__ == "__main__":
    main()
