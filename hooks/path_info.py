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
import re
import stat
import traceback
import glob

import sgtk
from sgtk.util import filesystem
from sgtk.templatekey import SequenceKey

HookBaseClass = sgtk.get_hook_baseclass()

# ---- globals

# a regular expression used to extract the version number from the file.
# this implementation assumes the version number is of the form 'v###'
# coming just before an optional extension in the file/folder name and just
# after a '.', '_', or '-'.
VERSION_REGEX = re.compile("(.*)([._-])v(\d+)\.?(\S+)?$", re.IGNORECASE)

# a regular expression used to extract the frame number from the file.
# this implementation assumes the version number is of the form '.####'
# coming just before the extension in the filename and just after a '.', '_',
# or '-'.
FRAME_REGEX = re.compile("(.*)([._-])(\d+)\.(\S+)$", re.IGNORECASE)


class BasicPathInfo(HookBaseClass):
    """
    Methods for basic file path parsing.
    """

    def get_publish_name(self, path):
        """
        Given a file path, return the display name to use for publishing.

        Typically, this is a name where the path and any version number are
        removed in order to keep the publish name consistent as subsequent
        versions are published.

        Example::

            # versioned file. remove the version
            in: /path/to/the/file/scene.v001.ma
            out: scene.ma

            # image sequence. replace the frame number with #s
            in: /path/to/the/file/my_file.001.jpg
            out: my_file.###.jpg

        :param path: The path to a file, likely one to be published.

        :return: A publish display name for the provided path.
        """

        publisher = self.parent

        logger = publisher.logger
        logger.debug("Getting publish name for path: %s ..." % (path,))

        # See if input path is a sequence_path
        seq_path = self.get_path_for_frame(path, 1001)
        if seq_path:
            path = seq_path

        path_info = publisher.util.get_file_path_components(path)
        filename = path_info["filename"]

        frame_pattern_match = re.search(FRAME_REGEX, filename)
        if frame_pattern_match:
            # found a frame number, replace it with #s
            prefix = frame_pattern_match.group(1)
            frame_sep = frame_pattern_match.group(2)
            frame = frame_pattern_match.group(3)
            display_str = "#" * len(frame)
            filename = "%s%s%s" % (prefix, frame_sep, display_str)
            extension = frame_pattern_match.group(4) or ""
            if extension:
                filename = "%s.%s" % (filename, extension)

        # if there's a version in the filename, extract it
        version_pattern_match = re.search(VERSION_REGEX, filename)
        if version_pattern_match:
            # found a version number, use the other groups to remove it
            filename = version_pattern_match.group(1)
            extension = version_pattern_match.group(4) or ""
            if extension:
                filename = "%s.%s" % (filename, extension)

        logger.debug("Returning publish name: %s" % (filename,))
        return filename

    def get_version_number(self, path):
        """
        Extract a version number from the supplied path.

        This is used by plugins that need to know what version number to
        associate with the file when publishing.

        :param path: The path to a file, likely one to be published.

        :return: An integer representing the version number in the supplied
            path. If no version found, ``None`` will be returned.
        """

        publisher = self.parent

        logger = publisher.logger
        logger.debug("Getting version number for path: %s ..." % (path,))

        path_info = publisher.util.get_file_path_components(path)
        filename = path_info["filename"]

        # default if no version number detected
        version_number = None

        # if there's a version in the filename, extract it
        version_pattern_match = re.search(VERSION_REGEX, filename)
        if version_pattern_match:
            version_number = int(version_pattern_match.group(3))

        logger.debug("Returning version number: %s" % (version_number,))
        return version_number

    def get_frame_number(self, path):
        """
        Given a path with a frame number, return the frame number.

        :param path: The input path with a frame number

        :return: The frame number as an integer
        """

        publisher = self.parent
        path_info = publisher.util.get_file_path_components(path)

        # see if there is a frame number
        frame_pattern_match = re.search(FRAME_REGEX, path_info["filename"])

        if not frame_pattern_match:
            # no frame number detected. carry on.
            return None

        # Return the parsed frame number as a string to preserve the frame padding
        return frame_pattern_match.group(3)

    def get_path_for_frame(self, path, frame_num, frame_spec=None):
        """
        Given a path with a frame spec, return the expanded path where the frame
        spec, such as ``{FRAME}`` or ``%04d`` or ``$F``, is replaced with a given
        frame number.

        :param path: The input path with a frame number
        :param frame_num: The frame number to replace the frame spec with.
        :param frame_spec: The frame specification to be replaced.

        :return: The full frame number path
        """

        publisher = self.parent
        path_info = publisher.util.get_file_path_components(path)

        # If the frame_spec is not specified, see if we can determine one
        if not frame_spec:
            # Attempt to match the path to a template
            path_tmpl = self.sgtk.template_from_path(path)
            if path_tmpl:
                # Find the first instance of a SequenceKey
                seq_key = None
                for key in path_tmpl.keys.values():
                    if isinstance(key, SequenceKey):
                        seq_key = key
                        break

                # If found, rebuild the path using the default value for the sequence key
                if seq_key:
                    fields = path_tmpl.get_fields(path)

                    # Delete the key since apply_fields() will plug-in defaults
                    # for missing fields
                    try:
                        del fields[seq_key.name]
                    except KeyError:
                        # if sequence key is not found, it is optional,
                        # and the path is not part of a sequence
                        return None
                    path = path_tmpl.apply_fields(fields)

                    # Re-process the path info
                    path_info = publisher.util.get_file_path_components(path)

                    # Store the default as the frame_spec
                    # NOTE: we do this as opposed to using apply_fields to apply the frame_num
                    # in case the user is requesting to replace with a value that wouldn't
                    # normally meet the TemplateKey value requirements (i.e. "*")
                    frame_spec = seq_key.default

                else:
                    # We matched a path that doesn't contain a sequence key, so we
                    # have nothing to replace
                    return None
            else:
                # We didn't match a template so attempt to use the "SEQ" key default value
                seq_key = self.sgtk.template_keys.get("SEQ")
                if seq_key:
                    frame_spec = seq_key.default
                else:
                    # Else just default to searching for a 4 pad
                    frame_spec = "%04d"

        # see if there is a frame spec
        SPEC_REGEX = re.compile("(.*)([._-])(%s)\.(\S+)$" % re.escape(frame_spec))
        frame_pattern_match = re.search(SPEC_REGEX, path_info["filename"])

        if not frame_pattern_match:
            # no frame spec detected. carry on.
            return None

        prefix = frame_pattern_match.group(1)
        frame_sep = frame_pattern_match.group(2)
        frame_str = frame_pattern_match.group(3)
        extension = frame_pattern_match.group(4) or ""

        seq_filename = "%s%s%s" % (prefix, frame_sep, frame_num)

        if extension:
            seq_filename = "%s.%s" % (seq_filename, extension)

        # build the full sequence path
        return os.path.join(path_info["folder"], seq_filename)

    def get_frame_sequence_path(self, path, frame_spec=None):
        """
        Given a path with a frame number, return the sequence path where the
        frame number is replaced with a given frame specification such as
        ``{FRAME}`` or ``%04d`` or ``$F``.

        :param path: The input path with a frame number
        :param frame_spec: The frame specification to replace the frame number
            with.

        :return: The full frame sequence path
        """
        publisher = self.parent

        # make sure the path is normalized. no trailing separator, separators
        # are appropriate for the current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(path)

        # Check to see if the input path contains a frame_spec
        frame_path = self.get_path_for_frame(path, 1001, frame_spec)
        if frame_path:
            # If we were able to do a successful substitution, then the input
            # path is a sequence path, so just return the input path
            path = frame_path

        path_template = self.sgtk.template_from_path(path)
        if path_template:
            # if the path fits a template, use that and check if it is a file sequence
            if "SEQ" in path_template.keys:
                fields = path_template.get_fields(path)
                del fields["SEQ"]
                return path_template.apply_fields(fields)
            else:
                return None
        else:
            path_info = publisher.util.get_file_path_components(path)

            # see if there is a frame number
            frame_pattern_match = re.search(FRAME_REGEX, path_info["filename"])
            if not frame_pattern_match:
                # no frame number detected. carry on.
                return None

            prefix = frame_pattern_match.group(1)
            frame_sep = frame_pattern_match.group(2)
            frame_str = frame_pattern_match.group(3)
            extension = frame_pattern_match.group(4) or ""

            # make sure we maintain the same padding
            if not frame_spec:
                seq_key = self.sgtk.template_keys.get("SEQ")
                if seq_key:
                    frame_spec = seq_key.default
                else:
                    padding = len(frame_str)
                    frame_spec = "%%0%dd" % (padding,)

            seq_filename = "%s%s%s" % (prefix, frame_sep, frame_spec)

            if extension:
                seq_filename = "%s.%s" % (seq_filename, extension)

            # build the full sequence path
            return os.path.join(path_info["folder"], seq_filename)

    def get_sequence_path_files(self, seq_path, frame_spec=None):
        """
        Given a sequence path, find all related files on disk

        :param path: The input sequence path with a frame spec

        :return: A list of matching file paths
        """
        # make sure the path is normalized. no trailing separator, separators
        # are appropriate for the current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(seq_path)

        # find files that match the pattern
        seq_pattern = self.get_path_for_frame(path, "*", frame_spec)
        seq_files = [f for f in glob.iglob(seq_pattern) if os.path.isfile(f)]

        # Sort the resulting list
        seq_files.sort()

        # Return the seq_files
        return seq_files

    def get_frame_sequences(self, folder, extensions=None, frame_spec=None):
        """
        Given a folder, inspect the contained files to find what appear to be
        files with frame numbers.

        :param folder: The path to a folder potentially containing a sequence of
            files.

        :param extensions: A list of file extensions to retrieve paths for.
            If not supplied, the extension will be ignored.

        :param frame_spec: A string to use to represent the frame number in the
            return sequence path.

        :return: A list of tuples for each identified frame sequence. The first
            item in the tuple is a sequence path with the frame number replaced
            with the supplied frame specification. If no frame spec is supplied,
            a python string format spec will be returned with the padding found
            in the file.


            Example::

            get_frame_sequences(
                "/path/to/the/folder",
                ["exr", "jpg"],
                frame_spec="{FRAME}"
            )

            [
                (
                    "/path/to/the/supplied/folder/key_light1.{FRAME}.exr",
                    [<frame_1_path>, <frame_2_path>, ...]
                ),
                (
                    "/path/to/the/supplied/folder/fill_light1.{FRAME}.jpg",
                    [<frame_1_path>, <frame_2_path>, ...]
                )
            ]
        """

        publisher = self.parent
        logger = publisher.logger

        logger.debug(
            "Looking for sequences in folder: '%s'..." % (folder,))

        # list of already processed file names
        processed_names = {}

        # examine the files in the folder
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)

            if os.path.isdir(file_path):
                # ignore subfolders
                continue

            # see if there is a frame number
            frame_pattern_match = re.search(FRAME_REGEX, filename)

            if not frame_pattern_match:
                # no frame number detected. carry on.
                continue

            prefix = frame_pattern_match.group(1)
            frame_sep = frame_pattern_match.group(2)
            frame_str = frame_pattern_match.group(3)
            extension = frame_pattern_match.group(4) or ""

            # filename without a frame number.
            file_no_frame = "%s.%s" % (prefix, extension)

            if file_no_frame in processed_names:
                # already processed this sequence. add the file to the list
                processed_names[file_no_frame]["file_list"].append(file_path)
                continue

            if extensions and extension not in extensions:
                # not one of the extensions supplied
                continue

            # make sure we maintain the same padding
            if not frame_spec:
                padding = len(frame_str)
                frame_spec = "%%0%dd" % (padding,)

            seq_filename = "%s%s%s" % (prefix, frame_sep, frame_spec)

            if extension:
                seq_filename = "%s.%s" % (seq_filename, extension)

            # build the path in the same folder
            seq_path = os.path.join(folder, seq_filename)

            # remember each seq path identified and a list of files matching the
            # seq pattern
            processed_names[file_no_frame] = {
                "sequence_path": seq_path,
                "file_list": [file_path]
            }

        # build the final list of sequence paths to return
        frame_sequences = []
        for file_no_frame in processed_names:

            seq_info = processed_names[file_no_frame]
            seq_path = seq_info["sequence_path"]

            logger.debug("Found sequence: %s" % (seq_path,))
            frame_sequences.append((seq_path, sorted(seq_info["file_list"])))

        return frame_sequences

    def get_version_path(self, path, version):
        """
        Given a path without a version number, return the path with the supplied
        version number.

        If a version number is detected in the supplied path, the path will be
        returned as-is.

        :param path: The path to inject a version number.
        :param version: The version number to inject.

        :return: The modified path with the supplied version number inserted.
        """

        publisher = self.parent

        logger = publisher.logger
        logger.debug("Getting version %s of path: %s ..." % (version, path))

        path_info = publisher.util.get_file_path_components(path)
        filename = path_info["filename"]

        # see if there's a version in the supplied path
        version_pattern_match = re.search(VERSION_REGEX, filename)

        if version_pattern_match:
            # version number already in the path. return the original path
            return path

        (basename, ext) = os.path.splitext(filename)

        # construct the new filename with the version number inserted
        version_filename = "%s.%s%s" % (basename, version, ext)

        # construct the new, full path
        version_path = os.path.join(path_info["folder"], version_filename)

        logger.debug("Returning version path: %s" % (version_path,))
        return version_path

    def get_next_version_path(self, path):
        """
        Given a file path, return a path to the next version.

        This is typically used by auto-versioning logic in plugins that need to
        save the current work file to the next version number.

        If no version can be identified in the supplied path, ``None`` will be
        returned, indicating that the next version path can't be determined.

        :param path: The path to a file, likely one to be published.

        :return: The path to the next version of the supplied path.
        """

        publisher = self.parent

        logger = publisher.logger
        logger.debug("Getting next version of path: %s ..." % (path,))

        # default
        next_version_path = None
        path_template = self.sgtk.template_from_path(path)

        if path_template:
            # if the path fits a template, use that and increment the version field
            fields = path_template.get_fields(path)
            if "version" in fields:
                fields["version"] = fields["version"] + 1
                next_version_path = path_template.apply_fields(fields)

        if not next_version_path:
            # fallback to regex matching
            # TODO: check entire path instead of just filename?
            path_info = publisher.util.get_file_path_components(path)
            filename = path_info["filename"]

            # see if there's a version in the supplied path
            version_pattern_match = re.search(VERSION_REGEX, filename)

            if version_pattern_match:
                prefix = version_pattern_match.group(1)
                version_sep = version_pattern_match.group(2)
                version_str = version_pattern_match.group(3)
                extension = version_pattern_match.group(4) or ""

                # make sure we maintain the same padding
                padding = len(version_str)

                # bump the version number
                next_version_number = int(version_str) + 1

                # create a new version string filled with the appropriate 0 padding
                next_version_str = "v%s" % (str(next_version_number).zfill(padding))

                new_filename = "%s%s%s" % (prefix, version_sep, next_version_str)
                if extension:
                    new_filename = "%s.%s" % (new_filename, extension)

                # build the new path in the same folder
                next_version_path = os.path.join(path_info["folder"], new_filename)

        logger.debug("Returning next version path: %s" % (next_version_path,))
        return next_version_path

    def get_next_version_info(self, path):
        """
        Return the next version of the supplied path.

        If templates are configured, use template logic. Otherwise, fall back to
        the zero configuration, path_info hook logic.

        :param str path: A path with a version number.
        :param item: The current item being published

        :return: A tuple of the form::

            # the first item is the supplied path with the version bumped by 1
            # the second item is the new version number
            (next_version_path, version)
        """
        publisher = self.parent

        logger = publisher.logger

        if not path:
            logger.debug("Path is None. Can not determine version info.")
            return None, None

        next_version_path = self.get_next_version_path(path)
        cur_version = self.get_version_number(path)
        if cur_version:
            version = cur_version + 1
        else:
            version = None

        return next_version_path, version

    def save_to_next_version(self, path, save_callback, **kwargs):
        """
        Save the supplied path to the next version on disk.

        :param path: The current path with a version number
        :param save_callback: A callback to use to save the file

        Relies on the get_next_version_info() method to retrieve the next
        available version on disk. If a version can not be detected in the path,
        the method does nothing.

        If the next version path already exists, revs to the next available version.

        This method is typically used by subclasses that bump the current
        working/session file after publishing.
        """
        publisher = self.parent

        logger = publisher.logger
        path = sgtk.util.ShotgunPath.normalize(path)

        version_number = self.get_version_number(path)
        if version_number is None:
            logger.debug(
                "No version number detected in the file path. "
                "Skipping the bump file version step."
            )
            return None

        logger.info("Incrementing file version number...")
        next_version_path = self.get_next_version_path(path)

        # nothing to do if the next version path can't be determined or if it
        # already exists.
        if not next_version_path:
            logger.warning("Could not determine the next version path.")
            return None

        elif os.path.exists(next_version_path):

            # determine the next available version_number. just keep asking for
            # the next one until we get one that doesn't exist.
            while os.path.exists(next_version_path):
                next_version_path = self.get_next_version_path(next_version_path)

            # now extract the version number of the next available to display
            # to the user
            next_version = self.get_version_number(next_version_path)

            logger.warning(
                "The next version of this file already exists on disk. "
                "Saving to the next available version number, v%s" % (next_version,),
                extra={
                    "action_show_folder": {
                        "path": next_version_path
                    }
                }
            )

        # save the file to the new path
        save_callback(next_version_path, **kwargs)
        logger.info("File saved as: %s" % (next_version_path,))

        return next_version_path

    def copy_files(self, src_files, dest_path, seal_files=False, is_sequence=False):
        """
        This method handles copying an item's path(s) to a designated location.

        If the item has "sequence_paths" set, it will attempt to copy all paths
        assuming they meet the required criteria.
        """

        publisher = self.parent

        logger = publisher.logger

        # ---- copy the src files to the dest location
        processed_files = []
        for src_file in src_files:

            if is_sequence:
                frame_num = self.get_frame_number(src_file)
                dest_file = self.get_path_for_frame(dest_path, frame_num)
            else:
                dest_file = dest_path

            # If the file paths are the same, lock permissions
            if src_file == dest_file:
                filesystem.freeze_permissions(dest_file)
                continue

            # copy the file
            try:
                dest_folder = os.path.dirname(dest_file)
                filesystem.ensure_folder_exists(dest_folder)
                filesystem.copy_file(src_file, dest_file,
                          permissions=stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
                          seal=seal_files)
            except Exception as e:
                raise Exception(
                    "Failed to copy file from '%s' to '%s'.\n%s" %
                    (src_file, dest_file, traceback.format_exc())
                )

            logger.debug(
                "Copied file '%s' to '%s'." % (src_file, dest_file)
            )
            processed_files.append(dest_file)

        return processed_files

    def symlink_files(self, src_files, dest_path, is_sequence=False):
        """
        This method handles symlink an item's publish_path to publish_symlink_path,
        assuming publish_symlink_path is already populated.

        If the item has "sequence_paths" set, it will attempt to symlink all paths
        assuming they meet the required criteria.
        """

        publisher = self.parent

        logger = publisher.logger

        # ---- symlink the publish files to the publish symlink path
        processed_files = []
        for src_file in src_files:

            if is_sequence:
                frame_num = self.get_frame_number(src_file)
                dest_file = self.get_path_for_frame(dest_path, frame_num)
            else:
                dest_file = dest_path

            # If the file paths are the same, skip...
            if src_file == dest_file:
                continue

            # symlink the file
            try:
                dest_folder = os.path.dirname(dest_file)
                filesystem.ensure_folder_exists(dest_folder)
                filesystem.symlink_file(src_file, dest_file)
            except Exception as e:
                raise Exception(
                    "Failed to link file from '%s' to '%s'.\n%s" %
                    (src_file, dest_file, traceback.format_exc())
                )

            logger.debug(
                "Linked file '%s' to '%s'." % (src_file, dest_file)
            )
            processed_files.append(dest_file)

        return processed_files

    def delete_files(self, paths_to_delete):
        """
        This method handles deleting an item's path(s) from a designated location.

        If the item has "sequence_paths" set, it will attempt to delete all paths
        assuming they meet the required criteria.
        """

        publisher = self.parent

        logger = publisher.logger

        # ---- delete the work files from the publish location
        processed_paths = []
        for deletion_path in paths_to_delete:

            # delete the path
            if os.path.isdir(deletion_path):
                filesystem.safe_delete_folder(deletion_path)
                logger.debug("Deleted folder '%s'." % deletion_path)
            else:
                filesystem.safe_delete_file(deletion_path)
                logger.debug("Deleted file '%s'." % deletion_path)

            processed_paths.append(deletion_path)

        return processed_paths
