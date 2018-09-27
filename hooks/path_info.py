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

import sgtk

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
FRAME_REGEX = re.compile("(.*)([._-])(\d+)\.([^.]+)$", re.IGNORECASE)


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

        # use template_key "SEQ" as default search regex
        if not frame_spec:
            seq_key = self.sgtk.template_keys.get("SEQ")
            if seq_key:
                frame_spec = seq_key.default
            else:
                frame_spec = "%%04d"

        # see if there is a frame number
        SPEC_REGEX = re.compile("(.*)([._-])(%s)\.([^.]+)$" % frame_spec)
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
