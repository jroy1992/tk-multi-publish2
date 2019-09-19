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
                "default_value": False,
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
