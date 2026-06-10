from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from nuedc_gen.__main__ import main

main()
