# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
This hook will submit the publish tree to the "farm".
"""
import sgtk


class FarmSubmission(sgtk.get_hook_baseclass()):

    def post_publish(self, tree):
        """
        This hook method is invoked after the publishing phase.

        :param tree: The tree of items and tasks that has just been published.
        :type tree: :ref:`publish-api-tree`
        """
        if not self.is_on_farm_machine():
            # Do nothing
            return

        if not self._has_farm_submissions(tree):
            self.logger.info("No task(s) were specified to submit to the farm.")
            return

        # Grab some information about the context Toolkit is running in so
        # we can initialize Toolkit properly on the farm.
        engine = sgtk.platform.current_engine()
        app_state = {
            "pipeline_configuration_id": engine.sgtk.configuration_id,
            "context": engine.context.to_dict(),
            "engine_instance_name": engine.instance_name,
            "app_instance_name": self.parent.instance_name
        }

        job_ids = self.submit_to_farm(app_state, tree)
        self.logger.info("The following job(s) have been submitted to the farm:\n%s" % job_ids)

    def _has_farm_submissions(self, tree):
        """
        :returns: ``True`` if any task is submitting to the farm, ``False`` otherwise.
        """
        for item in tree:
            for task in item.tasks:
                if task.plugin._hook_instance.has_steps_on_farm(task.settings, item):
                    return True
        return False

    def submit_to_farm(self, app_state, tree):
        """
        Submits the job to the render farm.

        :param dict app_state: State information about the :class:`Sgtk.Platform.Application`.
        :param tree: The tree of items and tasks that has just been published.
        :type tree: :ref:`publish-api-tree`

        :returns: A ``List`` of job ids
        """
        # TODO: You are the render farm experts.
        raise NotImplementedError

    @classmethod
    def is_on_farm_machine(cls):
        """
        :returns: ``True`` if on the render farm, ``False`` otherwise.
        """
        raise NotImplementedError
