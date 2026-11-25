import os
import sys
import tempfile
from pathlib import Path

# Répertoire de données isolé pour les tests (pas d'écriture dans data/)
os.environ.setdefault("APP_DATA_DIR", tempfile.mkdtemp(prefix="dashboard-tests-"))
os.environ.setdefault("BCRYPT_ROUNDS", "4")  # tests rapides
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
