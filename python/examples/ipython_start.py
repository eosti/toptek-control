import logging
from argparse import ArgumentParser

from IPython import get_ipython  # type: ignore

from toptek import Toptek

parser = ArgumentParser(
    prog="ipython_start",
    description="Configures a iPython shell. MUST BE RUN IN IPYTHON!",
)
parser.add_argument(
    "port",
    help="Serial port connected to an Arduino (typically /dev/ttyUSB0)",
)

logging.basicConfig(level=logging.INFO)

args = parser.parse_args()

pa = Toptek(args.port)

try:
    ipython = get_ipython()
    ipython.run_line_magic("load_ext", "autoreload")
    ipython.run_line_magic("autoreload", "2")
except ValueError:
    print("This script needs to be run in an iPython shell!")
    exit()
