"""
main.py — ADB Extractor & Analyser 2.0
Entry point. Run this file to launch the application.

Project layout:
    main.py   — entry point (this file)
    gui.py    — UI theme, reusable widgets, ADBExtractorApp window
    core.py   — constants, logging, preferences, ADB helpers,
                extraction and analysis logic
"""

from gui import ADBExtractorApp


if __name__ == "__main__":
    app = ADBExtractorApp()
    app.mainloop()
