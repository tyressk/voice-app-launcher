from __future__ import annotations
import threading
import time
from typing import Any, Dict
import logging_module
import shutil
import subprocess
import pyaudio
import numpy as np
from openwakeword.model import Model
from pathlib import Path
import shlex

class VoiceAppLauncherEngine:
    def __init__(self, config: Dict[str, Any], stop_event: threading.Event) -> None:
        self.config = config
        self.stop_event = stop_event
        self._running = False

    def start(self) -> None:
        logger = logging_module.get_logger()
        logger.info("VoiceAppLauncherEngine starting with config: %s", self.config)
        self._running = True

    def run(self) -> None:
        logger = logging_module.get_logger()
        logger.info("VoiceAppLauncherEngine running")

        # Configuration
        gen = self.config.get("general", {}) if isinstance(self.config, dict) else {}
        audio_cfg = self.config.get("audio", {}) if isinstance(self.config, dict) else {}
        model_paths = gen.get("model_paths")
        wakewords = self.config.get("wakewords", {}) if isinstance(self.config, dict) else {}
        sensitivity = float(gen.get("sensitivity"))
        launch_cooldown_secs = float(gen.get("launch_cooldown_secs"))
        chunk = int(audio_cfg.get("chunk_size"))
        sample_rate = int(audio_cfg.get("sample_rate"))
        channels = int(audio_cfg.get("channels"))
        # Initialize audio
        pa = pyaudio.PyAudio()
        stream = None
        try:
            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                frames_per_buffer=chunk,
            )
        except Exception as exc: 
            logger.error("Failed to open microphone stream: %s", exc)
            try:
                pa.terminate()
            except Exception:
                pass
            return

        try:
            resolved_paths = None
            if model_paths and isinstance(model_paths, (list, tuple)):
                resolved_paths = [str(Path(p).expanduser()) for p in model_paths if p]
            if resolved_paths:
                m = Model(wakeword_model_paths=resolved_paths)
            else:
                # Do not initialize Model() without explicit model paths (because it downloads all sample models).
                raise RuntimeError("No model_paths provided in config")
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.error("Failed to initialize openwakeword Model: %s", exc)
            try:
                stream.close()
                pa.terminate()
            except Exception:
                pass
            return

        # Debug: show what the loaded model exposes (attributes and key collections)
        try:
            # Collect public attributes
            attrs = [a for a in dir(m) if not a.startswith("_")]
            logger.info("Model object attributes: %s", ", ".join(attrs))

            # If model exposes mapping of models / prediction buffers show keys
            if hasattr(m, "models"):
                try:
                    logger.info("Model.models keys: %s", list(getattr(m, "models").keys()))
                except Exception:
                    logger.debug("Could not read m.models contents")
            if hasattr(m, "prediction_buffer"):
                try:
                    logger.info("Model.prediction_buffer keys: %s", list(getattr(m, "prediction_buffer").keys()))
                except Exception:
                    logger.debug("Could not read m.prediction_buffer contents")
        except Exception as exc:
            logger.debug("Failed to introspect model object for debugging: %s", exc)

        # Map of model -> opened flag to avoid repeated opens
        last_hit = {model: 0.0 for model in m.prediction_buffer.keys()}

        # Debug: show configured wakewords mapping
        try:
            logger.info("Configured wakewords mapping: %s", wakewords)
        except Exception:
            pass

        try:
            while not self.stop_event.is_set():
                try:
                    raw = stream.read(chunk, exception_on_overflow=False)
                except Exception as exc:
                    logger.warning("Audio read failed: %s", exc)
                    continue

                audio_buf = np.frombuffer(raw, dtype=np.int16)

                try:
                    _ = m.predict(audio_buf)
                except Exception as exc:
                    logger.debug("Model prediction failed: %s", exc)
                    continue
                # For each tracked model, check the latest score and
                # launch the assigned executable
                for model in m.prediction_buffer.keys():
                    scores = m.prediction_buffer[model]; 
                    curr = scores[-1] if scores else None
                    if not curr:
                        continue
                    detected = curr > sensitivity

                    if detected:
                        time_passed = time.monotonic() - last_hit.get(model, 0.0)
                        if time_passed < launch_cooldown_secs:
                            continue
                        last_hit[model] = time.monotonic()
                        cmds = []
                        try:
                            cmds = wakewords.get(model) or []
                        except Exception:
                            cmds = []
                        for cmd in cmds:
                            if not cmd:
                                continue
                            exec_with_args = shlex.split(cmd)
                            if not exec_with_args:
                                continue
                            exec_path = exec_with_args[0]
                            if Path(exec_path).exists() or shutil.which(exec_path):
                                try:
                                    subprocess.Popen(exec_with_args)
                                except Exception as exc:
                                    logger.warning("Failed to launch %s: %s", exec_path, exc)
                            else:
                                logger.debug("Configured command '%s' not found on PATH or as file", exec_path)

        finally:
            try:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass
            try:
                pa.terminate()
            except Exception:
                pass

        logger.info("VoiceAppLauncherEngine run loop exiting")

    def stop(self) -> None:
        logger = logging_module.get_logger()
        logger.info("VoiceAppLauncherEngine stopping")
        self._running = False

    def reload_config(self, config: Dict[str, Any]) -> None:
        logger = logging_module.get_logger()
        logger.info("VoiceAppLauncherEngine reloading config")
        self.config = config
