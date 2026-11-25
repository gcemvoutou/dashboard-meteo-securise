"""Point d'entrée de l'application : streamlit run app.py"""

import logging

from src import config
from src.dashboard import main


def setup_logging() -> None:
    """Journalisation console + fichier (data/app.log), configurée une seule fois par processus."""
    root = logging.getLogger()
    if getattr(root, "_dashboard_configured", False):
        return
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    for handler in (logging.StreamHandler(), logging.FileHandler(config.DATA_DIR / "app.log", encoding="utf-8")):
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    root._dashboard_configured = True


setup_logging()
main()
