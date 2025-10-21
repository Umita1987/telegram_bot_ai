import logging
import sys
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")  # UTC+2

class MoscowTimeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, MOSCOW_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.isoformat()

LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "app.log")

formatter = MoscowTimeFormatter(
    fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[stream_handler, file_handler]
)

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
