"""Entry point: python -m tui"""

from tui.app import AgentsApp


def main() -> None:
    AgentsApp().run()


if __name__ == "__main__":
    main()
