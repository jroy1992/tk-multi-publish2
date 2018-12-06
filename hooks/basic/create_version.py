# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import copy
import sgtk
import traceback

HookBaseClass = sgtk.get_hook_baseclass()


class CreateVersionPlugin(HookBaseClass):
    """
    Plugin for publishing an open nuke session.
    """
    def __init__(self, parent, **kwargs):
        """
        Construction
        """
        # call base init
        super(CreateVersionPlugin, self).__init__(parent, **kwargs)

        # cache the review submission app
        self.__review_submission_app = self.parent.engine.apps.get("tk-multi-reviewsubmission")

    @property
    def icon(self):
        """
        Path to an png icon on disk
        """
        # look for icon one level up from this hook's folder in "icons" folder
        return self.parent.expand_path("{self}/hooks/icons/review.png")

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Submit for Review"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        publisher = self.parent

        shotgun_url = publisher.sgtk.shotgun_url

        media_page_url = "%s/page/media_center" % (shotgun_url,)
        review_url = "https://www.shotgunsoftware.com/features-review"

        return """
        Create and upload a movie to Shotgun for review.<br><br>

        A high resolution movie will be created in the movie_path_template
        location set on the tk-multi-reviewsubmission app, a <b>Version</b>
        entry will be created in Shotgun and a transcoded copy of the file will
        be attached to it. The file can then be reviewed via the project's
        <a href='%s'>Media</a> page, <a href='%s'>RV</a>, or the
        <a href='%s'>Shotgun Review</a> mobile app.
        """ % (media_page_url, review_url, review_url)

    @property
    def settings_schema(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """
        schema = super(CreateVersionPlugin, self).settings_schema
        schema["Item Type Filters"]["default_value"] = ["file.*.sequence"]
        return schema

    def init_task_settings(self, item):
        """
        Method called by the publisher to determine the initial settings for the
        instantiated task.

        :param item: Item to process
        :returns: dictionary of settings for this item's task
        """
        # Return the plugin settings
        return self.plugin.settings

    def accept(self, task_settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """
        # Run the parent acceptance method
        accept_data = super(CreateVersionPlugin, self).accept(task_settings, item)
        if not accept_data.get("accepted"):
            return accept_data

        path = item.properties.get("path")
        if not path:
            msg = "'path' property is not set for item: %s" % item.name
            accept_data["extra_info"] = {
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": msg
                }
            }
            accept_data["accepted"] = False
            return accept_data

        if not self.__review_submission_app:
            msg = "Unable to run %s without the tk-multi-reviewsubmission app!" % self.name
            accept_data["extra_info"] = {
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": msg
                }
            }
            accept_data["enabled"] = False
            accept_data["checked"] = False
            return accept_data

        upload_to_shotgun = self.__review_submission_app.get_setting("upload_to_shotgun")
        store_on_disk = self.__review_submission_app.get_setting("store_on_disk")
        if not upload_to_shotgun and not store_on_disk:
            msg = "tk-multi-reviewsubmission app is not configured to store " \
                    + "images on disk nor upload to Shotgun!"
            accept_data["extra_info"] = {
                "action_show_more_info": {
                    "label": "Show Info",
                    "tooltip": "Show more info",
                    "text": msg
                }
            }
            accept_data["enabled"] = False
            accept_data["checked"] = False
            return accept_data

        # return the accepted info
        return accept_data

    def validate(self, task_settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        publisher = self.parent

        # ---- ensure that work file(s) exist on disk

        if item.properties.is_sequence:
            if not item.properties.sequence_paths:
                self.logger.warning("File sequence does not exist for item: %s" % item.name)
                return False
        else:
            if not os.path.exists(item.properties.path):
                self.logger.warning("File does not exist for item: %s" % item.name)
                return False

        return True

    def publish(self, task_settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        sg_publish_data_list = []

        if "sg_publish_data_list" in item.properties:
            sg_publish_data_list.extend(item.properties.sg_publish_data_list)

        # path to frames should point to the primary publish file. #766
        path_to_frames = item.properties.publish_path

        colorspace = self._get_colorspace(task_settings, item)
        first_frame, last_frame = self._get_frame_range(task_settings, item)

        # First copy the item's fields
        fields = copy.copy(item.properties.fields)

        # Update with the fields from the context
        fields.update(item.context.as_template_fields())

        # set review_submission app's env/context based on item (ingest)
        self.__review_submission_app.change_context(item.context)

        exception = None
        sg_version = None
        try:
            sg_version = self.__review_submission_app.render_and_submit_path(path_to_frames, fields, first_frame,
                                                                             last_frame, sg_publish_data_list,
                                                                             item.context.task, item.description,
                                                                             item.get_thumbnail_as_path(),
                                                                             self._progress_cb, colorspace)
        except Exception as e:
            exception = e
            self.logger.error(
                "Couldn't Create Version for %s" % item.name,
                extra={
                    "action_show_more_info": {
                        "label": "Show Error Log",
                        "tooltip": "Show the error log",
                        "text": traceback.format_exc()
                    }
                }
            )

        # delete the rendered movie if any.
        if not sg_version:
            self.undo(task_settings, item)

        if exception:
            raise exception

        # stash the version info in the item just in case
        item.properties.sg_version_data = sg_version

        self.logger.info("Version Creation complete!")

    def undo(self, task_settings, item):
        """
        Execute the undo method. This method will
        delete the files that have been copied to the disk
        it will also delete any PublishedFile entity that got created due to the publish.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the task_settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        movie_path = self._get_movie_path(task_settings, item)
        if os.path.exists(movie_path):
            self.logger.info("Cleaning up rendered movie for %s..." % item.name)

            try:
                os.unlink(movie_path)
            except Exception:
                self.logger.error(
                    "Failed to delete Rendered Movie for %s" % item.name,
                    extra={
                        "action_show_more_info": {
                            "label": "Show Error Log",
                            "tooltip": "Show the error log",
                            "text": traceback.format_exc()
                        }
                    }
                )

    def finalize(self, task_settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param task_settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """
        version = item.properties.sg_version_data

        self.logger.info(
            "Version created for item: %s" % (item.name,),
            extra={
                "action_show_in_shotgun": {
                    "label": "Show Version",
                    "tooltip": "Reveal the version in Shotgun.",
                    "entity": version
                }
            }
        )


    ############################################################################
    # protected methods

    def _get_movie_path(self, task_settings, item):
        """
        Returns the path of the movie that's supposed to be output of review submit.
        """

        # Make sure we don't overwrite the item's fields
        fields = copy.copy(item.properties.fields)
        # Update with the fields from the context
        fields.update(item.context.as_template_fields())

        # Movie output width and height
        width = self.__review_submission_app.get_setting("movie_width")
        height = self.__review_submission_app.get_setting("movie_height")
        fields["width"] = width
        fields["height"] = height

        # Get an output path for the movie.
        output_path_template = self.__review_submission_app.get_template("movie_path_template")
        output_path = output_path_template.apply_fields(fields)

        return output_path

    def _get_colorspace(self, task_settings, item):
        """
        Intended to be overridden by subclasses
        """
        return None

    def _get_frame_range(self, task_settings, item):
        """
        Intended to be overridden by subclasses
        """
        publisher = self.parent

        # Determine if this is a sequence of paths
        if item.properties.is_sequence:
            first_frame = int(publisher.util.get_frame_number(item.properties.sequence_paths[0]))
            last_frame = int(publisher.util.get_frame_number(item.properties.sequence_paths[-1]))
        else:
            first_frame = last_frame = 0

        return (first_frame, last_frame)

    def _progress_cb(self, msg=None, stage=None):
        """
        """
        # if stage matches a task then we want to include
        # the task details at the start of the message:
        if msg is not None:
            try:
                item_name = stage["item"]["name"]
                output_name = stage["output"]["name"]

                # update message to include task info:
                self.logger.info("%s - %s: %s" % (output_name, item_name, msg))
            except:
                pass
