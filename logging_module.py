import sys
import logging
def _setup_logging(level: str | int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger('VoiceAppLauncher')
    formatter = logging.Formatter(fmt="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y.%m.%d %H:%M:%S")
    text_handler = logging.StreamHandler(sys.stdout)
    text_handler.formatter = formatter
    logger.addHandler(text_handler);
    logger.setLevel(level);
    return logger

def get_logger(level: str | int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger('VoiceAppLauncher')
    if logging.getLogger('VoiceAppLauncher').hasHandlers():
        return logger
    else:
        return _setup_logging(level)
