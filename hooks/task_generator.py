# Copyright (c) 2018 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import fnmatch
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class TaskGenerator(HookBaseClass):
    """
    This hook defines a custom task generator method used during the
    validation, publish, and finalization steps to yield the list of items
    in the publish tree to process.
    """

    def execute(self, publish_tree, item_filters=None, task_filters=None, publish_logger=None):
        """
        This method generates all active tasks for all active items in the
        publish tree and yields them to the caller.

        This is the default task generator used by validate, publish, and
        finalize if no custom task generator is supplied.

        :param publish_tree: The dictionary representing the serialized publish tree.
        :param item_filters: A list of patterns to match against the list
                             of items to process. Default is ['*'].
        :param task_filters: A list of patterns to match against the list
                             of tasks to process. Default is ['*'].
        :param publish_logger: a logger object that will be used by the hook
        """
        item_filters = item_filters or ['*']
        task_filters = task_filters or ['*']

        logger = publish_logger or self.logger

        logger.debug("Iterating over tasks...")
        for item in publish_tree:

            item_matched = False
            for item_filter in item_filters:
                if fnmatch.fnmatch(item.name, item_filter):
                    item_matched = True

            if not item_matched:
                logger.debug(
                    "Skipping item '%s' because it doesn't match the specified filter" %
                    (item,)
                )
                continue

            if not item.active:
                logger.debug(
                    "Skipping item '%s' because it is inactive" % (item,))
                continue

            if not item.tasks:
                logger.debug(
                    "Skipping item '%s' because it has no tasks attached." %
                    (item,)
                )
                continue

            logger.debug("Processing item: %s" % (item,))
            for task in item.tasks:

                task_matched = False
                for task_filter in task_filters:
                    if fnmatch.fnmatch(task.name, task_filter):
                        task_matched = True

                if not task_matched:
                    logger.debug(
                        "Skipping task '%s' because it doesn't match the specified filter" %
                        (task,)
                    )
                    continue

                if not task.active:
                    logger.debug("Skipping inactive task: %s" % (task,))
                    continue

                status = (yield task)
                logger.debug("Task %s status: %s" % (task, status))
