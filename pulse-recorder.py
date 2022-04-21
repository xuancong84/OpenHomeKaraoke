#!/usr/bin/env python3
# Based on code from these stackoverflow answers:
# https://askubuntu.com/questions/60837/record-a-programs-output-with-pulseaudio/910879#910879
import re
import subprocess
import sys
import os
import signal
from time import sleep

INDEX_RE = re.compile(r'[0-9]+$')
APP_NAME_RE = re.compile(r'"([^"]+)"')
SINK_RE=re.compile("\s*sink: ([0-9]+) <.*>")

DEFAULT_OUTPUT_RE = re.compile(r'^\s*name: <([^ >]+)>')

record_module_id = None

def get_default_output():
    #pacmd list-sinks | grep -A1 "* index" | grep -oP "<\K[^ >]+"
    output = subprocess.run(["pacmd", "list-sinks"], stdout=subprocess.PIPE, check=True).stdout
    for line in output.decode('utf-8').split('\n'):
        match = DEFAULT_OUTPUT_RE.match(line)
        if match:
            return match[1]
    print("Can't seem to find proper input sink, are you using pulseaudio?")
    sys.exit(3)

def load_record_module():
    default_output = get_default_output()
    output = subprocess.run(
        ["pactl", "load-module", "module-combine-sink", "sink_name=record-n-play", f"slaves={default_output}", 
        "sink_properties=device.description=Record-and-Play"], 
        stdout=subprocess.PIPE, check=True).stdout
    return int(output.strip())

def load_apps():
    output = subprocess.run(["pacmd", "list-sink-inputs"], stdout=subprocess.PIPE, check=True).stdout
    output = output.decode('utf-8').split('\n')

    indexes = []
    app_names = []
    sinks = []

    for line in output:
        if "index" in line:
            index = INDEX_RE.findall(line)[0]
            indexes.append(index)
        elif "application.name" in line:
            app_name = APP_NAME_RE.findall(line)[0]
            app_names.append(app_name)
        elif len(sinks) < len(indexes) and "sink: " in line:
            sink = SINK_RE.match(line)[1]
            sinks.append(sink)

    if len(indexes) == 0:
        print("Sorry, couldn't find any input audio channels")
        sys.exit(1)
    return indexes, app_names, sinks

def cleanup(*args, **kwargs):
    if record_module_id is None:
        sys.exit(0)
        return

    os.system(f"pactl move-sink-input {indexes[user_selection]} {sinks[user_selection]}")
    os.system(f"pactl unload-module {record_module_id}")
    print("Terminated")
    sys.exit(0)
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)


if os.path.exists("temp.mp3"):
    print("temp.mp3 already exist, aborting")
    sys.exit(2)

_, app_names, _ = load_apps()
print("")
for idx, app_name in enumerate(app_names):
    print(f"{idx + 1} - {app_name}")
print("")

while True:
    try:
        user_selection = int(input("Please enter a number: "))
    except ValueError:
        print("Only numbers are allowed")
        continue

    if user_selection > len(app_names) or user_selection <= 0:
        print("Number out of range")
        continue

    user_selection = int(user_selection) - 1
    break

app_name = app_names[user_selection]
print(f"Your selection was: {app_name}")
input("Please press enter when you are ready to start")

while True:
    indexes, app_names, sinks = load_apps()
    if app_name not in app_names:
        print("Couldn't find selected audio channel, retrying")
        sleep(0.2)
        continue
    user_selection = app_names.index(app_name)
    record_module_id=load_record_module()
    os.system(f"pactl move-sink-input {indexes[user_selection]} record-n-play")
    os.system(f"parec --format=s16le -d record-n-play.monitor | lame -r -q 3 --lowpass 17 --abr 192 - 'temp.mp3'")
    cleanup()
