# Copyright (c) 2017 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
import os

from .api import PublishManager
from . import base_hooks
from . import util


def _handle_sgtk_publish_preload_path(app, sgtk_publish_preload_path, PRELOAD_SIGNALER):
    from sgtk.platform.qt import QtCore
    folders = list()

    for root, dirs, files in os.walk(sgtk_publish_preload_path):
        if not dirs:
            folders.append(root)

    def on_start():
        PRELOAD_SIGNALER.preload_signal.emit(folders)

    QtCore.QTimer.singleShot(1000, on_start)

def show_dialog(app):
    """
    Show the main dialog ui

    :param app: The parent App
    """
    # defer imports so that the app works gracefully in batch modes
    from .dialog import AppDialog
    from .dialog import PRELOAD_SIGNALER
    import socket

    display_name = sgtk.platform.current_bundle().get_setting("display_name")

    display_host_name = sgtk.platform.current_bundle().get_setting("display_host_name")

    if display_host_name:
        # add host name for more info
        host_name = socket.gethostname()
        display_name = display_name + " ( on %s )" % host_name

    # start ui
    app.engine.show_dialog(display_name, app, AppDialog)

    # this will pre-populate publisher when it is run with --p flag.
    sgtk_publish_preload_path = os.environ.get('SGTK_PUBLISH_PRELOAD_PATH')
    if sgtk_publish_preload_path and os.path.isdir(sgtk_publish_preload_path):
        _handle_sgtk_publish_preload_path(app, sgtk_publish_preload_path, PRELOAD_SIGNALER)




