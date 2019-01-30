# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


import sgtk

try:
    from sgtk.platform.qt import QtCore, QtGui
except ImportError:
    CustomWidgetController = None
else:
    class FarmWrapperWidget(QtGui.QWidget):
        """
        This is the plugin's custom UI.

        It is meant to allow the user to send a task to the
        render farm or not.
        """
        def __init__(self, parent):
            super(FarmWrapperWidget, self).__init__(parent)

            # Create a nice simple layout with a checkbox in it.
            layout = QtGui.QFormLayout(self)
            self.setLayout(layout)

            label = QtGui.QLabel(
                "Clicking this checkbox will submit this task to the render farm.",
                self
            )
            label.setWordWrap(True)
            layout.addRow(label)

            self._check_box = QtGui.QCheckBox("Submit to Farm", self)
            self._check_box.setTristate(False)
            layout.addRow(self._check_box)

        @property
        def state(self):
            """
            :returns: ``True`` if the checkbox is checked, ``False`` otherwise.
            """
            return self._check_box.checkState() == QtCore.Qt.Checked

        @state.setter
        def state(self, is_checked):
            """
            Update the status of the checkbox.

            :param bool is_checked: When set to ``True``, the checkbox will be
                checked.
            """
            if is_checked:
                self._check_box.setCheckState(QtCore.Qt.Checked)
            else:
                self._check_box.setCheckState(QtCore.Qt.Unchecked)


class FarmWrapperPlugin(sgtk.get_hook_baseclass()):

    # User setting used to track if a task will be publish locally
    # or on the farm.
    _SUBMIT_TO_FARM = "Submit to Farm"
    _FARM_STEPS = "Farm Steps"

    @property
    def name(self):
        """
        :returns: Name of the plugin.
        """
        return self._SUBMIT_TO_FARM

    @property
    def settings_schema(self):
        """
        Exposes the list of settings for this hook.

        :returns: Dictionary of settings definitions for the app.
        """
        schema = super(FarmWrapperPlugin, self).settings_schema
        schema.update({
            self._SUBMIT_TO_FARM: {
                "type": "bool",
                "default_value": True,
                "description": "When set to True, this task will not be "
                               "published inside the DCC and will be published "
                               "on the render farm instead."
            },
            self._FARM_STEPS: {
                "type": "list",
                "values": {
                    "type": "str"
                },
                "default_value": ["publish"],
                "description": "The step(s) to run on the farm: ['validate', 'publish']"
            }
        })
        return schema

    def create_settings_widget(self, parent):
        """
        Creates the widget for our plugin.

        :param parent: Parent widget for the settings widget.
        :type parent: :class:`QtGui.QWidget`

        :returns: Custom widget for this plugin.
        :rtype: :class:`QtGui.QWidget`
        """
        tab_widget = QtGui.QTabWidget(parent)

        base_gui = super(FarmWrapperPlugin, self).create_settings_widget(tab_widget)
        tab_widget.addTab(base_gui, super(FarmWrapperPlugin, self).name)

        tab_widget.addTab(FarmWrapperWidget(tab_widget), "Farm")

        return tab_widget

    def get_ui_settings(self, widget):
        """
        Retrieves the state of the ui and returns a settings dictionary.

        :param parent: The settings widget returned by :meth:`create_settings_widget`
        :type parent: :class:`QtGui.QWidget`

        :returns: Dictionary of settings.
        """
        submit_widget = widget.findChild(FarmWrapperWidget)
        return {self._SUBMIT_TO_FARM: submit_widget.state}

    def set_ui_settings(self, widget, settings):
        """
        Populates the UI with the settings for the plugin.

        :param parent: The settings widget returned by :meth:`create_settings_widget`
        :type parent: :class:`QtGui.QWidget`
        :param list(dict) settings: List of settings dictionaries, one for each
            item in the publisher's selection.

        :raises NotImplementeError: Raised if this implementation does not
            support multi-selection.
        """
        if len(settings) > 1:
            raise NotImplementedError()
        settings = settings[0]

        submit_widget = widget.findChild(FarmWrapperWidget)
        submit_widget.state = settings[self._SUBMIT_TO_FARM]

    def validate(self, task_settings, item):
        """
        Validates a given task if it's the right time.

        :param dict task_settings: Dictionary of :class:`PluginSetting` object for this task.
        :param item: The item currently being published.
        :type item: :class:`PublishItem` to publish.
        """
        # If this step is to be run on the farm...
        if self.run_step_on_farm(task_settings, item, "validate"):
            # ...and we're still on the local (submitting) host...
            if not self.is_on_farm_machine():
                # Store the current user and do nothing
                item.local_properties.publish_user = sgtk.util.get_current_user(
                    self.parent.sgtk
                )
                self.logger.info("This validation will be submitted to the farm.")
                return True

        # Else run the parent validation
        return super(FarmWrapperPlugin, self).validate(task_settings, item)

    def publish(self, task_settings, item):
        """
        Publishes a given task to Shotgun if it's the right time.

        :param dict task_settings: Dictionary of :class:`PluginSetting` object for this task.
        :param item: The item currently being published.
        :type item: :class:`PublishItem` to publish.
        """
        # If this step is to be run on the farm...
        if self.run_step_on_farm(task_settings, item, "publish"):
            # ...and we're still on the local (submitting) host...
            if not self.is_on_farm_machine():
                # Store the current user and do nothing
                item.local_properties.publish_user = sgtk.util.get_current_user(
                    self.parent.sgtk
                )
                self.logger.info("This publish will be submitted to the farm.")
                return

        # Else run the parent publish
        super(FarmWrapperPlugin, self).publish(task_settings, item)

    def finalize(self, task_settings, item):
        """
        Finalizes a given task if it's the right time.

        :param dict task_settings: Dictionary of :class:`PluginSetting` object for this task.
        :param item: The item currently being published.
        :type item: :class:`PublishItem` to publish.
        """
        # If this step is to be run on the farm...
        if self.run_step_on_farm(task_settings, item, "publish"):
            # ...and we're still on the local (submitting) host...
            if not self.is_on_farm_machine():
                # Do nothing
                return

        # Else run the parent finalization
        super(FarmWrapperPlugin, self).finalize(task_settings, item)

    def run_step_on_farm(self, task_settings, item, step):
        """
        Indicates if this step should be run on the farm.

        :param dict task_settings: Dictionary of :class:`PluginSetting` object for this task.
        :param item: The item currently being published.
        :type item: :class:`PublishItem` to publish.
        :param string step: A ``String`` representing the step being run.

        :returns: ``True`` if the action should be taken, ``False`` otherwise.
        """
        # If the Submit to Farm setting is turned set and we're on the a user's machine
        if task_settings[self._SUBMIT_TO_FARM].value:
            if step in task_settings[self._FARM_STEPS].value:
                # We are indeed submitting to the farm.
                return True

        # We're not currently submitting to the farm.
        return False

    def has_steps_on_farm(self, task_settings, item):
        """
        Indicates if this task has any steps that are being run on the farm.

        :param dict task_settings: Dictionary of :class:`PluginSetting` object for this task.
        :param item: The item currently being published.
        :type item: :class:`PublishItem` to publish.
        :param string step: A ``String`` representing the step being run.

        :returns: ``True`` if the any step is to be run on the farm, ``False`` otherwise.
        """
        for step in task_settings[self._FARM_STEPS].value:
            if self.run_step_on_farm(task_settings, item, step):
                return True
        return False

    @classmethod
    def is_on_farm_machine(cls):
        """
        :returns: ``True`` if on the render farm, ``False`` otherwise.
        """
        raise NotImplementedError
