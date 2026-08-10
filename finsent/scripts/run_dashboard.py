from __future__ import annotations

from finsent.app.dashboard.app import create_app
from finsent.app.utils.logging import configure_logging


def main() -> None:
    configure_logging()
    app = create_app()
    app.run(debug=False)


if __name__ == "__main__":
    main()
