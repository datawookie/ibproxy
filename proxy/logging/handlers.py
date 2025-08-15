import logging
import os
import re
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler


class CustomTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(
        self,
        filename: str,
        when: str = "H",
        interval: int = 1,
        backupCount: int = 0,
        encoding: str = "utf-8",
        delay: bool = False,
        utc: bool = False,
    ) -> None:
        super().__init__(filename, when, interval, backupCount, encoding, delay, utc)

        self.suffix = "%Y%m%d-%H%M"
        self.prefix = os.path.splitext(self.baseFilename)[0]
        self.ext = "log"

    def rotation_filename(self, default_name: str) -> str:
        """
        Generates replacement filename used when current log file is rotated.

        The timestamp used is for the time of rotation.
        """
        dtime = datetime.now().strftime(self.suffix)

        return f"{self.prefix}-{dtime}.{self.ext}"

    def getFilesToDelete(self) -> list[str]:
        """
        Which files are to be deleted?

        Only relevant if backupCount is defined.
        """
        dir, base = os.path.split(self.prefix)
        regex = f"{base}-(.*)\\.{self.ext}"
        result = []
        for name in os.listdir(dir):
            if match := re.search(regex, name):
                try:
                    # Does timestamp match format?
                    datetime.strptime(match.group(1), self.suffix)
                    result.append(os.path.join(dir, name))
                except ValueError:
                    continue

        if len(result) < self.backupCount:
            logging.info("🗑️ No log files to delete.")
            return []

        result.sort()

        result = result[: len(result) - self.backupCount]
        logging.info(f"🗑️ Found {len(result)} log file(s) to delete.")

        return result
