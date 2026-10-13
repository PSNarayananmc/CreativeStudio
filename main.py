#!/usr/bin/env python3
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from creative_studio.ui import Window


def main():
    import os
    if os.environ.get('CREATIVE_STUDIO_SMOKE'):  # packaged self-test mode
        from creative_studio.smoke import run_smoke
        return run_smoke()
    app = QApplication(sys.argv)
    app.setApplicationName('Creative Studio')
    app.setOrganizationName('CreativeStudio')
    def exception_handler(kind, value, trace):
        import traceback
        traceback.print_exception(kind, value, trace)
        QMessageBox.critical(None, 'Creative Studio', str(value))
    sys.excepthook = exception_handler
    window = Window(); window.show()
    return app.exec()

if __name__ == '__main__':
    raise SystemExit(main())
