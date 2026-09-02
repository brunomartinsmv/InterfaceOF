import os

os.environ.setdefault('MPLBACKEND', 'QtAgg')

from app.gui.main_window import run_app


if __name__ == "__main__":
    run_app()
