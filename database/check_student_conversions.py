"""Run the scheduled student-to-alumni eligibility and conversion check."""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from student_conversions import run_scheduled_conversion_check


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
)


if __name__ == '__main__':
    try:
        result = run_scheduled_conversion_check()
        logging.getLogger(__name__).info('Student conversion check result: %s', result)
    except Exception:
        logging.getLogger(__name__).exception('Student conversion cron run failed.')
        raise SystemExit(1)