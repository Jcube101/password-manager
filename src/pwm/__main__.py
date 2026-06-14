"""Allow `python -m pwm` to launch the CLI (even without the console script being installed)."""

from .cli import app

if __name__ == "__main__":
    app()
