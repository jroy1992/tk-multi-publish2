# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from contextlib import contextmanager
import copy
import traceback

import sgtk
from .instance_base import PluginInstanceBase
from .setting import *

logger = sgtk.platform.get_logger(__name__)


class CollectorPluginInstance(PluginInstanceBase):
    """
    Class that wraps around a collector hook

    Each collector plugin object reflects an instance in the app configuration.
    """

    def _create_hook_instance(self, path):
        """
        Create the plugin's hook instance.

        Injects the collector base class in order to provide default
        implementation.
        """
        bundle = sgtk.platform.current_bundle()
        plugin = bundle.create_hook_instance(
            path,
            base_class=bundle.base_hooks.CollectorPlugin,
            plugin=self
        )
        plugin.id = path
        return plugin

    def run_process_file(self, item, path):
        """
        Executes the hook process_file method

        :param item: Item to parent collected items under.
        :param path: The path of the file to collect

        :returns: None (item creation handles parenting)
        """
        try:
            if hasattr(self._hook_instance.__class__, "settings_schema"):
                # this hook has a 'settings_schema' property defined. it is expecting
                # 'settings' to be passed to the processing method.
                return self._hook_instance.process_file(
                    self.settings, item, path)
            else:
                # the hook hasn't been updated to handle collector settings.
                # call the method without a settings argument
                return self._hook_instance.process_file(item, path)
        except Exception:
            error_msg = traceback.format_exc()
            self._logger.error(
                "Error running process_file for %s" % self,
                extra = _get_error_extra_info(error_msg)
            )
        finally:
            if not sgtk.platform.current_engine().has_ui:
                from sgtk.platform.qt import QtCore
                QtCore.QCoreApplication.processEvents()

    def run_process_current_session(self, item):
        """
        Executes the hook process_current_session method

        :param item: Item to parent collected items under.

        :returns: None (item creation handles parenting)
        """
        try:
            if hasattr(self._hook_instance.__class__, "settings_schema"):
                # this hook has a 'settings_schema' property defined. it is expecting
                # 'settings' to be passed to the processing method.
                return self._hook_instance.process_current_session(
                    self.settings, item)
            else:
                # the hook hasn't been updated to handle collector settings.
                # call the method without a settings argument
                return self._hook_instance.process_current_session(item)
        except Exception:
            error_msg = traceback.format_exc()
            self._logger.error(
                "Error running process_current_session for %s" % self,
                extra = _get_error_extra_info(error_msg)
            )
        finally:
            if not sgtk.platform.current_engine().has_ui:
                from sgtk.platform.qt import QtCore
                QtCore.QCoreApplication.processEvents()

    def run_on_context_changed(self, item):
        """
        Executes the on_context_changed logic for this plugin instance.

        :param settings: Dictionary of settings
        :param item: Item to analyze
        """
        with self._handle_plugin_error(None, "Error changing context: %s"):
            self._hook_instance.on_context_changed(self.settings, item)

    def get_settings_for_context(self, context=None):
        """
        Find and resolve settings for the plugin in the specified context

        :param context: Context in which to look for settings.

        :returns: The plugin settings for the given context or None.
        """
        # Set the context if not specified
        context = context or self._context

        # Inject this plugin's schema in the correct location for proper resolution
        plugin_schema = {
            "collector_settings" : {
                "items" : self.settings_schema
            }
        }

        # Resolve and validate the plugin settings
        return get_setting_for_context("collector_settings", context, plugin_schema, validate=True)

    @contextmanager
    def _handle_plugin_error(self, success_msg, error_msg):
        """
        Creates a scope that will properly handle any error raised by the plugin
        while the scope is executed.

        .. note::
            Any exception raised by the plugin is bubbled up to the caller.

        :param str success_msg: Message to be displayed if there is no error.
        :param str error_msg: Message to be displayed if there is an error.
        """

        try:
            # Execute's the code inside the with statement. Any errors will be
            # caught and logged and the events will be processed
            yield
        except Exception as e:
            exception_msg = traceback.format_exc()
            self._logger.error(
                error_msg % (e,),
                extra=_get_error_extra_info(exception_msg)
            )
            raise
        else:
            if success_msg:
                self._logger.debug(success_msg)
        finally:
            if not sgtk.platform.current_engine().has_ui:
                from sgtk.platform.qt import QtCore
                QtCore.QCoreApplication.processEvents()


def _get_error_extra_info(error_msg):
    """
    A little wrapper to return a dictionary of data to show a button in the
    publisher with the supplied error message.
    :param error_msg: The error message to display.
    :return: An logging "extra" dictionary to show the error message.
    """

    return {
        "action_show_more_info": {
            "label": "Error Details",
            "tooltip": "Show the full error tack trace",
            "text": "<pre>%s</pre>" % (error_msg,)
        }
    }
