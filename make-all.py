import sys
from subprocess import check_call as run

run([sys.executable, "make.py"])
run([sys.executable, "make-msix.py"])
run([sys.executable, "make-msi.py"])
