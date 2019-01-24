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
import traceback

from .api import PublishManager
from . import base_hooks
from . import util


def _handle_publish_preload_path(app, publish_preload_path, PRELOAD_SIGNALER):
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
        _handle_publish_preload_path(app, publish_preload_path, PRELOAD_SIGNALER)

def run_batch(app, publish_tree_file=None, item_filter=None, task_filter=None, logger=None):
    """
    Runs the publisher in batch mode.

    :param app: The parent App
    :param publish_tree_file: The path to a serialized publish tree.
    :param item_filter: A list of :class:`~PublishItem` names to include.
    :param task_filter: A list of :class:`~PublishTask` names to include.
    :param publish_logger: The logger object to use for logging.

    :returns: `True` if success, `False` otherwise.
    """
    logger = logger or app.logger

    # Create a publish manager
    manager = PublishManager(logger)

    publish_tree_file = publish_tree_file or os.environ.get("SGTK_PUBLISH_TREE_FILE")
    if publish_tree_file:
        # Load the publish tree
        logger.info("Processing Publish Tree File: %s" % publish_tree_file)
        manager.load(publish_tree_file)

    else:
        # this will pre-populate publisher when it is run with --p flag.
        publish_preload_path = os.environ.get('SGTK_PUBLISH_PRELOAD_PATH')
        if publish_preload_path:
            logger.info("Processing Preload Path: %s" % publish_preload_path)
            new_items = manager.collect_files([publish_preload_path])
            num_items_created = len(new_items)
            if num_items_created > 0:
                logger.info("%s item(s) were added." % num_items_created)
            else:
                logger.info("No item(s) were added.")
                return True
        else:
            logger.error("Nothing to process! Exiting...")
            return True

    # See if there is a custom task generator defined
    generator_hook_file = app.get_setting("task_generator_hook")
    if generator_hook_file:
        task_generator = app.create_hook_instance(
            generator_hook_file,
            manager.tree,
            item_filter,
            task_filter
        )

    # Else use the default generator
    else:
        task_generator = manager.default_task_generator(item_filter, task_filter)

    # Run all steps.
    logger.info("Starting Publish!")

    # is the app configured to execute the validation when publish
    # is triggered?
    if app.get_setting("validate_on_publish"):
        logger.info("Running validation pass")
        try:
            failed_to_validate = manager.validate(task_generator)
            num_issues = len(failed_to_validate)
        finally:
            if num_issues > 0:
                logger.error("Validation Complete. %d issues reported. Not proceeding with publish." % num_issues)
                return False
            else:
                logger.info("Validation Complete. All checks passed.")
    else:
        logger.info("'validate_on_publish' is False. Skipping validation pass.")

    logger.info("Running publishing pass")
    try:
        manager.publish(task_generator)
    except Exception:
        logger.error("Error while publishing. Aborting.")
        # ensure the full error shows up in the log file
        logger.error("Publish error stack:\n%s" % (traceback.format_exc(),))
        return False
    logger.info("Publishing pass Complete.")

    logger.info("Running finalize pass")
    try:
        manager.finalize(task_generator)
    except Exception:
        logger.error("Error while finalizing. Aborting.")
        # ensure the full error shows up in the log file
        logger.error("Finalize error stack:\n%s" % (traceback.format_exc(),))
        return False
    logger.info("Finalize pass Complete.")

    logger.info("Publish Complete!")
    return True
