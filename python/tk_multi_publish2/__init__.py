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

logger = sgtk.platform.get_logger(__name__)

def _handle_publish_preload_path(publish_preload_path, PRELOAD_SIGNALER):
    from sgtk.platform.qt import QtCore
    folders = list()

    for root, dirs, files in os.walk(publish_preload_path):
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

    display_name = app.get_setting("display_name")

    display_host_name = sgtk.platform.current_bundle().get_setting("display_host_name")

    if display_host_name:
        # add host name for more info
        host_name = socket.gethostname()
        display_name = display_name + " ( on %s )" % host_name

    # start ui
    app.engine.show_dialog(display_name, app, AppDialog)

    # this will pre-populate publisher when it is run with --p flag.
    publish_preload_path = os.environ.get('SGTK_PUBLISH_PRELOAD_PATH')
    if publish_preload_path and os.path.isdir(publish_preload_path):
        _handle_publish_preload_path(publish_preload_path, PRELOAD_SIGNALER)

def run_batch(app):
    """
    Runs the publisher in batch mode.

    :param app: The parent App

    :returns: `True` if success, `False` otherwise.
    """
    # Create a publish manager
    manager = PublishManager()

    # See if a publish tree file is specified in the environment
    publish_tree_file = os.environ.get("SGTK_PUBLISH_TREE_FILE")
    if publish_tree_file:
        logger.info("Processing Publish Tree File: %s" % publish_tree_file)
        manager.load(publish_tree_file)

        # Subtract to account for root node
        num_items_added = len(list(manager.tree)) - 1
        if num_items_added > 0:
            logger.info("%s item(s) were added." % num_items_added)
        else:
            logger.info("No item(s) were added.")

    # See if a file preload path is specified in the environment
    publish_preload_path = os.environ.get("SGTK_PUBLISH_PRELOAD_PATH")
    if publish_preload_path:
        logger.info("Processing Publish Preload Path: %s" % publish_preload_path)
        new_items = manager.collect_files([publish_preload_path])
        num_items_created = len(new_items)
        if num_items_created > 0:
            logger.info("%s item(s) were added." % num_items_created)
        else:
            logger.info("No item(s) were added.")

    # Process the loaded items
    return manager.run()
