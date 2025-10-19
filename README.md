# Voice App Launcher

A wake-word detection app/background service in Python using [openWakeWord](https://github.com/dscripka/openWakeWord/), currently only for Linux. It listens for specific wake words (like ‘Open Browser’) and launches apps and/or commands when detected.


## How to run on CLI

You should have python installed (tested with Python 3.13.7).

Clone the repository, install the required libs and run through the executable script (or through `python main.py`) in venv:

```bash
git clone https://github.com/tyressk/voice-app-launcher.git
cd voice-app-launcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod a+x run_openwakeword
./run_openwakeword
```


## Run under systemd

The systemd service file is available at `systemd/voiceapplauncher.service`. You will need to modify it if you did not clone this repo on your home directory.

Copy the file to `~/.config/systemd/user` and enable the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now voiceapplauncher # also starts the service
```

If you modify the toml configuration file, you can reload the config using `systemctl --user reload voiceapplauncher`. Logs will be written to the systemd journal and can be viewed with `journalctl` (e.g. `journalctl --user -u voiceapplauncher -f`)


## Configuration (TOML)

Running the app automatically creates a config file in `~/.config/voice_app_launcher/config.toml` with default values

```toml

[general]
model_paths = ["/path/to/model2.onnx", "/path/to/model1.onnx"] # etc. Expanded file paths to each model
sensitivity = 0.5 # decision threshold used for interpreting model scores
log_level = "INFO" # e.g. `DEBUG`, `WARN`, etc.
launch_cooldown_secs = 3.0 # how long to wait between executing the same command

[wakewords]
"Open_Terminal" = ["wezterm start --always-new-process"] # Flags are supported
"Open_Browser" = ["firefox"] # You can also execute multiple commands, e.g. `"Open_Browser" =  ["firefox","chrome"]`
"Open_Editor" = ["code"]
"Open_Youtube" = ["firefox --new-tab https://www.youtube.com"]

[audio]
sample_rate = 16000 # Sample rate of input audio
channels = 1 
chunk_size = 1280 # number of audio frames per read. chunk_size / sample_rate determines seconds per read

```

## Creating your own custom models

At the moment only 4 models are included, all of which were created using the first jupyter notebook hosted on Google Colab from [this guide](https://github.com/dscripka/openWakeWord/?tab=readme-ov-file#training-new-models). If you have a good enough GPU, I suggest you run the notebook locally (like I did). At this point it seems to have dependencies that do not have wheels on the latest Python, so you will need to use an older version like 3.11 (using pyenv, etc. if you have a newer installed Python version). 
