import argparse
import signal
import threading
import time
from pathlib import Path
import config_loader
from engine import VoiceAppLauncherEngine
import logging_module

try:
    from sdnotify import SystemdNotifier
    _NOTIFIER_AVAILABLE = True
except Exception:
    SystemdNotifier = None  # type: ignore
    _NOTIFIER_AVAILABLE = False

def run_service(config_path: Path | None = None, 
                notify: bool = True, 
                once: bool = False, 
                log_level_override: str | None = None) -> int:
    try:
        if config_path is None:
            cfg = config_loader.load_config()
        else:
            p = Path(config_path).expanduser()
            if not p.exists():
                config_loader.write_config(p, config_loader.DEFAULT_CONFIG)
            cfg = config_loader.read_config(p)
    except config_loader.ConfigSchemaError as e:
        logger = logging_module.get_logger()
        logger.error(f"Configuration schema error:{e}")
        return 3
    except Exception as e:
        logger = logging_module.get_logger()
        logger.error(f"Failed to load config:{e}")
        return 4

    level_to_use = log_level_override or cfg.get("general", {}).get("log_level", "INFO")
    logger = logging_module.get_logger(level_to_use)

    stop_event = threading.Event()
    reload_event = threading.Event()
    engine = VoiceAppLauncherEngine(cfg, stop_event)

    worker = threading.Thread(target=lambda: _engine_thread(engine, stop_event), daemon=True)

    # Signal handlers
    def _handle_termination(signum, frame):
        logger.info("Received termination signal %s", signum)
        stop_event.set()

    def _handle_sighup(signum, frame):
        logger.info("Received SIGHUP: reloading configuration")
        reload_event.set()

    signal.signal(signal.SIGINT, _handle_termination)
    signal.signal(signal.SIGTERM, _handle_termination)
    signal.signal(signal.SIGHUP, _handle_sighup) # We only support Linux rn

    if _NOTIFIER_AVAILABLE and notify:
        try:
            notifier = SystemdNotifier()
            notifier.notify("STATUS=starting voice_app_launcher")
        except Exception:
            logger.debug("sdnotify notifier failed to initialize")

    try:
        engine.start()
    except Exception:
        logger.exception("Failed to start engine")
        return 4

    worker.start()

    if _NOTIFIER_AVAILABLE and notify:
        try:
            notifier.notify("READY=1")
            notifier.notify("STATUS=running voice_app_launcher")
        except Exception:
            logger.debug("sdnotify notify failed")


    if once:
        # TODO: Debug stuff? Maybe
        time.sleep(1.0)
        stop_event.set()
    else:
        while True:
            worker.join(timeout=1.0)
            if reload_event.is_set():
                logger.info("Reload requested: restarting engine thread")
                # stop current engine
                stop_event.set()
                engine.stop()
                worker.join(timeout=5.0)

                # new thread
                new_cfg = config_loader.load_config()
                stop_event = threading.Event()  
                engine = VoiceAppLauncherEngine(new_cfg, stop_event)
                worker = threading.Thread(target=lambda: _engine_thread(engine, stop_event), daemon=True)
                engine.start()
                worker.start()
                reload_event.clear()
                continue  

            if not worker.is_alive():
                break  

    # Ensure engine stopped
    try:
        engine.stop()
    except Exception:
        logger.exception("Error while stopping engine")

    logger.info("Service exiting")
    return 0


def _engine_thread(engine: VoiceAppLauncherEngine, stop_event: threading.Event) -> None:
    try:
        engine.run()
    except Exception:
        logger = logging_module.get_logger()
        logger.exception("Unhandled exception in engine run loop")
        stop_event.set()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="openwakeword_systemd service runner")
    parser.add_argument("--config", "-c", help="Path to a TOML config file to use (overrides default)")
    parser.add_argument("--no-notify", action="store_true", help="Disable systemd notifications (useful for local runs)")
    parser.add_argument("--log-level", help="Override log level (DEBUG/INFO/WARNING/ERROR)")
    parser.add_argument("--once", action="store_true", help="Run briefly and exit")
    args = parser.parse_args()

    exit_code = run_service(config_path=Path(args.config) if args.config else None, notify=not args.no_notify, once=args.once, log_level_override=args.log_level)
    raise SystemExit(exit_code)
