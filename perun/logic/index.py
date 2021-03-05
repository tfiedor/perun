"""Collection of methods for manipulation with Index.

This contains both helper constants, enums, and function, and most of all all definitions
of various version of index entries.
"""

import os
import binascii
import struct
import json
from zlib import error

from enum import Enum

import perun.utils.timestamps as timestamps
import perun.utils.log as perun_log
import perun.utils.helpers as helpers
import perun.logic.store as store
import perun.logic.pcs as pcs

from perun.utils.exceptions import (EntryNotFoundException, MalformedIndexFileException,
                                    IndexNotFoundException)


__author__ = 'Tomas Fiedor'

# List of current versions of format and magic constants
INDEX_ENTRIES_START_OFFSET = 12
INDEX_NUMBER_OF_ENTRIES_OFFSET = 8
INDEX_MAGIC_PREFIX = b'pidx'
# Index Version 2.0 FastSloth
INDEX_VERSION = 2

IndexVersion = Enum(
    'IndexVersion',
    'SlowLorris FastSloth'
)


class BasicIndexEntry:
    """Class representation of one index entry

    This corresponds to the basic version of the index called the Slow Lorris.
    The issue with this entry is that it is very minimalistic, and requires loading profiles
    for status and log.

    :ivar str time: modification timestamp of the entry profile
    :ivar str checksum: checksum of the object, i.e. the path to its real content
    :ivar str path: the original path to the profile
    :ivar int offset: offset of the entry within the index
    """
    version = IndexVersion.SlowLorris

    def __init__(self, time, checksum, path, offset, *_):
        """
        :param str time: modification timestamp of the entry profile
        :param str checksum: checksum of the object, i.e. the path to its real content
        :param str path: the original path to the profile
        :param int offset: offset of the entry within the index
        """
        self.time = time
        self.checksum = checksum
        self.path = path
        self.offset = offset

    def __eq__(self, other):
        """Compares two IndexEntries simply by checking the equality of its internal dictionaries

        :param other: other object to be compared
        :return: whether this object is the same as other
        """
        return self.__dict__ == other.__dict__

    @classmethod
    def read_from(cls, index_handle, index_version):
        """Reads the entry from the index handle

        This is basic version, which stores only the information of timestamp, sha and path of the
        file.

        TODO: add check for index version

        :param File index_handle: opened index handle
        :param IndexVersion index_version: version of the opened index
        :return: one read BasicIndexEntry
        """
        if BasicIndexEntry.version.value < index_version.value:
            perun_log.error("internal error: called read_from() for BasicIndexEntry {}".format(
                index_version.value
            ))
        file_offset = index_handle.tell()
        file_time = timestamps.timestamp_to_str(timestamps.read_timestamp_from_file(index_handle))
        file_sha = binascii.hexlify(index_handle.read(20)).decode('utf-8')
        file_path, byte = "", store.read_char_from_handle(index_handle)
        while byte != '\0':
            file_path += byte
            byte = store.read_char_from_handle(index_handle)
        return BasicIndexEntry(file_time, file_sha, file_path, file_offset)

    def write_to(self, index_handle):
        """Writes entry at current location in the index_handle

        :param file index_handle: file handle of the index
        """
        timestamps.write_timestamp(index_handle, timestamps.str_to_timestamp(self.time))
        index_handle.write(bytearray.fromhex(self.checksum))
        index_handle.write(bytes(self.path, 'utf-8'))
        index_handle.write(struct.pack('B', 0))

    def __str__(self):
        """Converts the entry to one string representation

        :return:  string representation of the entry
        """
        return " @{3} {2} -> {1} ({0})".format(
            self.time,
            self.checksum,
            self.path,
            self.offset
        )


class ExtendedIndexEntry(BasicIndexEntry):
    """Class representation of one extended index entry

    This corresponds to the extended version of the index called the Fast Sloth.
    It contains additional informations about profile, so one do not have to load
    the profiles everytime it wants to print some basic information.

    :ivar str time: modification timestamp of the entry profile
    :ivar str checksum: checksum of the object, i.e. the path to its real content
    :ivar str path: the original path to the profile
    :ivar int offset: offset of the entry within the index
    :ivar str cmd: command for which we collected data
    :ivar str args: arguments of the command
    :ivar str workload: workload of the command
    :ivar str collector: collector used to collect data
    :ivar list postprocessors: list of postprocessors used to postprocess data
    """
    version = IndexVersion.FastSloth

    def __init__(self, time, checksum, path, offset, profile):
        """
        :param str time: modification timestamp of the entry profile
        :param str checksum: checksum of the object, i.e. the path to its real content
        :param str path: the original path to the profile
        :param int offset: offset of the entry within the index
        :param dict profile: basic information for profiles
        """
        super().__init__(time, checksum, path, offset)
        self.type = profile['header']['type']
        self.cmd = profile['header']['cmd']
        self.args = profile['header'].get('args', '')
        self.workload = profile['header'].get('workload', '')
        self.collector = profile['collector_info']['name']
        self.postprocessors = [
            postprocessor['name'] for postprocessor in profile['postprocessors']
        ]

    def __eq__(self, other):
        """Compares two IndexEntries simply by checking the equality of its internal dictionaries

        :param other: other object to be compared
        :return: whether this object is the same as other
        """
        return self.__dict__ == other.__dict__

    @classmethod
    def read_from(cls, index_handle, index_version):
        """Reads the entry from the index handle

        :param File index_handle: opened index handle
        :param IndexVersion index_version: version of the opened index
        :return: one read ExtendedIndexEntry
        """
        if ExtendedIndexEntry.version.value > index_version.value:
            # Since we are reading from the older index, we will have to fix some stuff
            return ExtendedIndexEntry._read_from_older_index(index_handle, index_version)
        return ExtendedIndexEntry._read_from_same_index(index_handle, index_version)

    @classmethod
    def _read_from_older_index(cls, index_handle, index_version):
        """Reads the ExtendedIndexEntry from older version of index.

        This means, that not everything was stored in the index, and the profile itself has to be
        loaded to extract additional details.

        :param index_handle:
        :param index_version:
        :return:
        """
        basic_entry = super().read_from(index_handle, index_version)
        _, profile_name = store.split_object_name(pcs.get_object_directory(), basic_entry.checksum)
        profile = store.load_profile_from_file(profile_name, is_raw_profile=False)
        return ExtendedIndexEntry(
            basic_entry.time, basic_entry.checksum, basic_entry.path, basic_entry.offset, profile
        )


    @classmethod
    def _read_from_same_index(cls, index_handle, index_version):
        """

        :param index_handle:
        :return:
        """
        basic_entry = BasicIndexEntry.read_from(index_handle, get_older_version(index_version))
        profile = {'header': {}, 'collector_info': {}, 'postprocessors': []}

        profile['header']['type'] = store.read_string_from_handle(index_handle)
        profile['header']['cmd'] = store.read_string_from_handle(index_handle)
        profile['header']['args'] = store.read_string_from_handle(index_handle)
        profile['header']['workload'] = store.read_string_from_handle(index_handle)
        profile['collector_info']['name'] = store.read_string_from_handle(index_handle)
        profile['postprocessors'] = [
            {'name': post} for post in store.read_list_from_handle(index_handle)
        ]

        # Read the rest of the stored profile
        return ExtendedIndexEntry(
            basic_entry.time, basic_entry.checksum, basic_entry.path, basic_entry.offset, profile
        )

    def write_to(self, index_handle):
        """Writes entry at current location in the index_handle

        :param file index_handle: file handle of the index
        """
        super().write_to(index_handle)
        store.write_string_to_handle(index_handle, self.type)
        store.write_string_to_handle(index_handle, self.cmd)
        store.write_string_to_handle(index_handle, self.args)
        store.write_string_to_handle(index_handle, self.workload)
        store.write_string_to_handle(index_handle, self.collector)
        store.write_list_to_handle(index_handle, self.postprocessors)

    def __str__(self):
        """Converts the entry to one string representation

        :return:  string representation of the entry
        """
        return " @{3} {2} -> {1} ({0}) {4}; {5}; {6} {7}".format(
            self.time,
            self.checksum,
            self.path,
            self.offset,
            self.type,
            " ".join([self.cmd, self.args, self.workload]),
            self.collector,
            " ".join(self.postprocessors)
        )


def get_older_version(index_version):
    """Returns older version of the index

    :param IndexVersion index_version:
    :return: older version of the index
    """
    return IndexVersion(index_version.value-1)


def walk_index(index_handle):
    """Iterator through index entries

    Reads the beginning of the file, verifying the version and type of the index. Then it iterates
    through all of the index entries and returns them as a BasicIndexEntry structure for further
    processing.

    :param file index_handle: handle to file containing index
    :returns BasicIndexEntry: Index entry named tuple
    """
    # Get end of file position
    index_handle.seek(0, 2)
    last_position = index_handle.tell()

    # Move to the begging of the handle
    index_handle.seek(0)
    magic_bytes = index_handle.read(4)
    if magic_bytes != INDEX_MAGIC_PREFIX:
        raise MalformedIndexFileException("read blob is not an index file")

    index_version = store.read_int_from_handle(index_handle)
    if index_version > INDEX_VERSION:
        raise MalformedIndexFileException("read index file is in format of different index version"
                                          " (read index file = {}".format(index_version) +
                                          ", supported = {})".format(INDEX_VERSION))

    number_of_objects = store.read_int_from_handle(index_handle)
    loaded_objects = 0
    entry_constructor = INDEX_ENTRY_CONSTRUCTORS[INDEX_VERSION - 1]

    while index_handle.tell() + 24 < last_position and loaded_objects < number_of_objects:
        entry = entry_constructor.read_from(index_handle, IndexVersion(index_version))
        loaded_objects += 1
        yield entry

    if loaded_objects != number_of_objects:
        perun_log.error("fatal: "
                        "malformed index file: too many or too few objects registered in index")


def print_index(index_file):
    """Helper function for printing the contents of the index

    :param str index_file: path to the index file
    """
    with open(index_file, 'rb') as index_handle:
        print_index_from_handle(index_handle)


def print_index_from_handle(index_handle):
    """Helper funciton for printing the contents of index inside the handle.

    :param file index_handle: opened file handle
    """
    index_prefix = index_handle.read(4)
    index_version = store.read_int_from_handle(index_handle)
    number_of_entries = store.read_int_from_handle(index_handle)

    print("{}, index version {} with {} entries\n".format(
        index_prefix, index_version, number_of_entries
    ))

    for entry in walk_index(index_handle):
        print(str(entry))


def touch_index(index_path):
    """Initializes and creates the index if it does not exists

    The Version 1 index is of following form:
      -  4B magic prefix 'pidx' (perun index) for quick identification of the file
      -  4B version number (currently 1)
      -  4B number of index entries

    Followed by the entries of profiles of form:
      -  4B time of the file creation
      - 20B SHA-1 representation of the object
      -  ?B Variable length path
      -  ?B zero byte padding

    :param str index_path: path to the index
    """
    if not os.path.exists(index_path):
        helpers.touch_file(index_path)

        # create the index
        with open(index_path, 'wb') as index_handle:
            initialize_index_in_handle(index_handle)


def initialize_index_in_handle(index_handle):
    """Initialize the index prefix in the handle.

    First the magic bytes are written, then the version of the index and at last the
    number of the registered entries.

    :param index_handle:
    :return:
    """
    index_handle.write(INDEX_MAGIC_PREFIX)
    index_handle.write(struct.pack('i', INDEX_VERSION))
    index_handle.write(struct.pack('i', 0))


def update_index_version(index_handle):
    """Updates the index handle to newer version

    :param File index_handle: opened index handle
    """
    previous_position = index_handle.tell()
    index_handle.seek(4)
    index_handle.write(struct.pack('i', INDEX_VERSION))
    index_handle.seek(previous_position)


def modify_number_of_entries_in_index(index_handle, modify):
    """Helper function of inplace modification of number of entries in index

    :param file index_handle: handle of the opened index
    :param function modify: function that will modify the value of number of entries
    """
    index_handle.seek(INDEX_NUMBER_OF_ENTRIES_OFFSET)
    number_of_entries = store.read_int_from_handle(index_handle)
    index_handle.seek(INDEX_NUMBER_OF_ENTRIES_OFFSET)
    index_handle.write(struct.pack('i', modify(number_of_entries)))


def write_entry_to_index(index_file, file_entry):
    """Writes the file_entry to its appropriate position within the index.

    Given the file entry, writes the entry within the file, moving everything by the given offset
    and then incrementing the number of entries within the index.

    :param str index_file: path to the index file
    :param BasicIndexEntry file_entry: index entry that will be written to the file
    """
    with open(index_file, 'rb+') as index_handle:
        # Lookup the position of the registered file within the index
        if file_entry.offset == -1:
            try:
                predicate = (
                    lambda entry: entry.path > file_entry.path or (
                        entry.path == file_entry.path and entry.time >= file_entry.time
                    )
                )
                looked_up_entry = lookup_entry_within_index(
                    index_handle, predicate, file_entry.path
                )

                # If there is an exact match, we do not add the entry to the index
                if looked_up_entry.path == file_entry.path and \
                                looked_up_entry.time == file_entry.time:
                    perun_log.msg_to_stdout("{0.path} ({0.time}) already registered in {1}".format(
                        file_entry, index_file
                    ), 0)
                    return
                offset_in_file = looked_up_entry.offset
            except EntryNotFoundException:
                # Move to end of the file and set the offset to the end of the file
                index_handle.seek(0, 2)
                offset_in_file = index_handle.tell()
        else:
            offset_in_file = file_entry.offset

        # Modify the number of entries in index and return to position
        modify_number_of_entries_in_index(index_handle, lambda x: x + 1)
        index_handle.seek(offset_in_file)

        # Read previous entries to buffer and return back to the position
        buffer = index_handle.read()
        index_handle.seek(offset_in_file)

        # Write the index_file entry to index
        file_entry.write_to(index_handle)

        # Write the stuff stored in buffer
        index_handle.write(buffer)

        # Finally update the index version, if it was the older one
        update_index_version(index_handle)


def write_list_of_entries(index_file, entry_list):
    """Rewrites the index file to contain the list of entries only

    Clears the index and writes list of entries into the index

    :param str index_file:
    :param list of ExtendedIndexEntry entry_list:
    """
    # First delete the index
    with open(index_file, 'wb+') as index_handle:
        index_handle.truncate(0)
        initialize_index_in_handle(index_handle)
        modify_number_of_entries_in_index(index_handle, lambda x: len(entry_list))
        index_handle.seek(INDEX_ENTRIES_START_OFFSET)
        for entry in entry_list:
            entry.write_to(index_handle)


def lookup_entry_within_index(index_handle, predicate, looked_up_entry_name):
    """Looks up the first entry within index that satisfies the predicate

    :param file index_handle: file handle of the index
    :param function predicate: predicate that tests given entry in index BasicIndexEntry -> bool
    :param str looked_up_entry_name: name of the entry we are looking up (for exception)
    :returns BasicIndexEntry: index entry satisfying the given predicate
    """
    for entry in walk_index(index_handle):
        if predicate(entry):
            return entry

    raise EntryNotFoundException(looked_up_entry_name)


def lookup_all_entries_within_index(index_handle, predicate):
    """
    :param file index_handle: file handle of the index
    :param function predicate: predicate that tests given entry in index BasicIndexEntry -> bool

    :returns [BasicIndexEntry]: list of index entries satisfying given predicate
    """
    return [entry for entry in walk_index(index_handle) if predicate(entry)]


def find_minor_index(minor_version):
    """ Finds the corresponding index for the minor version or raises EntryNotFoundException if
    the index was not found.

    :param str minor_version: the minor version representation or None for HEAD

    :return str: path to the index file
    """
    # Find the index file
    _, index_file = store.split_object_name(pcs.get_object_directory(), minor_version)
    if not os.path.exists(index_file):
        raise IndexNotFoundException(index_file)
    return index_file


def register_in_pending_index(registered_file, profile):
    """Registers file in the index corresponding to the minor_version

    If the index for the minor_version does not exist, then it is touched and initialized
    with empty prefix. Then the entry is added to the file.

    :param path registered_file: filename that is registered
    :param dict profile: profile to be registered
    """
    # Create the directory and index (if it does not exist)
    index_filename = pcs.get_job_index()
    touch_index(index_filename)
    registered_checksum = store.compute_checksum(registered_file.encode('utf-8'))

    register_in_index(index_filename, registered_file, registered_checksum, profile)


def register_in_minor_index(base_dir, minor_version, registered_file, registered_checksum, profile):
    """Registers file in the index corresponding to the minor_version

    If the index for the minor_version does not exist, then it is touched and initialized
    with empty prefix. Then the entry is added to the file.

    :param str base_dir: base directory of the minor version
    :param str minor_version: sha-1 representation of the minor version of vcs (like e.g. commit)
    :param path registered_file: filename that is registered
    :param str registered_checksum: sha-1 representation fo the registered file
    :param dict profile: profile to be registered
    """
    # Create the directory and index (if it does not exist)
    minor_dir, minor_index_file = store.split_object_name(base_dir, minor_version)
    helpers.touch_dir(minor_dir)
    touch_index(minor_index_file)

    register_in_index(minor_index_file, registered_file, registered_checksum, profile)


def register_in_index(index_filename, registered_file, registered_file_checksum, profile):
    """Registers file in the index corresponding to either minor_version or pending profiles

    :param str index_filename: source index filename
    :param path registered_file: filename that is registered
    :param str registered_file_checksum: sha-1 representation fo the registered file
    :param dict profile: profile to be registered
    """
    modification_stamp = timestamps.timestamp_to_str(os.stat(registered_file).st_mtime)
    entry_name = os.path.split(registered_file)[-1]
    entry = INDEX_ENTRY_CONSTRUCTORS[INDEX_VERSION - 1](
        modification_stamp, registered_file_checksum, entry_name, -1, profile
    )
    write_entry_to_index(index_filename, entry)

    reg_rel_path = os.path.relpath(registered_file)
    perun_log.info("'{}' successfully registered in minor version index".format(reg_rel_path))


def remove_from_index(base_dir, minor_version, removed_file_generator):
    """Removes stream of removed files from the index.

    Iterates through all of the removed files, and removes their partial/full occurence from the
    index. The index is walked just once.

    :param str base_dir: base directory of the minor version
    :param str minor_version: sha-1 representation of the minor version of vcs (like e..g commit)
    :param generator removed_file_generator: generator of filenames, that will be removed from the
        tracking
    """
    # Get directory and index
    _, minor_version_index = store.split_object_name(base_dir, minor_version)
    removed_profile_number = len(removed_file_generator)

    if not os.path.exists(minor_version_index):
        raise EntryNotFoundException("", "empty index")

    # Lookup all entries for the given function
    with open(minor_version_index, 'rb+') as index_handle:
        # Gather all of the entries from the index
        all_entries = list(walk_index(index_handle))
        all_entries.sort(key=lambda unsorted_entry: unsorted_entry.offset)
        removed_entries = []

        for i, removed_file in enumerate(removed_file_generator):
            def lookup_function(entry):
                """Helper lookup function according to the type of the removed file"""
                if store.is_sha1(removed_file):
                    return entry.checksum == removed_file
                else:
                    return entry.path == removed_file

            found_entry = lookup_entry_within_index(index_handle, lookup_function, removed_file)
            removed_entries.append(found_entry)

            perun_log.info("{}/{} deregistered {} from index".format(
                helpers.format_counter_number(i+1, removed_profile_number),
                removed_profile_number,
                perun_log.in_color(found_entry.path, 'grey')
            ))

        # Update number of entries
        index_handle.seek(INDEX_NUMBER_OF_ENTRIES_OFFSET)
        index_handle.write(struct.pack('i', len(all_entries) - len(removed_entries)))

        # For each entry remove from the index, starting from the greatest offset
        for entry in all_entries:
            if entry in removed_entries:
                continue
            entry.write_to(index_handle)

        index_handle.truncate()
    if removed_profile_number:
        result_string = perun_log.in_color("{}".format(
            helpers.str_to_plural(removed_profile_number, "profile")
        ), 'white', 'bold')
        perun_log.info("successfully deregistered {} from {} index".format(
            result_string, perun_log.in_color(minor_version, 'green')
        ))


def get_profile_list_for_minor(base_dir, minor_version):
    """Read the list of entries corresponding to the minor version from its index.

    :param str base_dir: base directory of the models
    :param str minor_version: representation of minor version
    :returns list: list of IndexEntries
    """
    _, minor_index_file = store.split_object_name(base_dir, minor_version)

    result = []
    if os.path.exists(minor_index_file):
        with open(minor_index_file, 'rb+') as index_handle:
            index_handle.seek(4)
            index_version = store.read_int_from_handle(index_handle)
            result = list(walk_index(index_handle))
        # Update the version of the index
        if index_version < INDEX_VERSION:
            write_list_of_entries(minor_index_file, result)
    return result


def get_profile_number_for_minor(base_dir, minor_version):
    """
    :param str base_dir: base directory of the profiles
    :param str minor_version: representation of minor version
    :returns dict: dictionary of number of profiles inside the index of the minor_version of types
    """
    _, minor_index_file = store.split_object_name(base_dir, minor_version)

    if os.path.exists(minor_index_file):
        profile_numbers_per_type = {
            profile_type: 0 for profile_type in helpers.SUPPORTED_PROFILE_TYPES
            }

        with open(minor_index_file, 'rb') as index_handle:
            # Read the overall
            index_handle.seek(INDEX_NUMBER_OF_ENTRIES_OFFSET)
            profile_numbers_per_type['all'] = store.read_int_from_handle(index_handle)

            # Check the types of the entry
            for entry in walk_index(index_handle):
                if entry.type in helpers.SUPPORTED_PROFILE_TYPES:
                    profile_numbers_per_type[entry.type] += 1
            return profile_numbers_per_type
    else:
        return {'all': 0}


def load_custom_index(index_path):
    """Loads the content of a custom index file (e.g. temp or stats) as a dictionary.

    The index is json-formatted and compressed. In case the index cannot be read for some reason,
    an empty dictionary is returned.

    :param str index_path: path to the index file

    :return: the decompressed and json-decoded index content.
    """
    # Create and init the index file if it does not exist yet
    if not os.path.exists(index_path):
        helpers.touch_file(index_path)
        save_custom_index(index_path, {})
    # Open and load the file
    try:
        with open(index_path, 'rb') as index_handle:
            return json.loads(store.read_and_deflate_chunk(index_handle))
    except (ValueError, error):
        # Contents either empty or corrupted, init the content to empty dict
        return {}


def save_custom_index(index_path, records):
    """Saves the index records to the custom index file.
    The index file is created if it does not exist or overwritten if it does.

    :param str index_path: path to the index file
    :param records: the index entries/records in a format that can be transformed to json
    """
    with open(index_path, 'w+b') as index_handle:
        compressed = store.pack_content(json.dumps(records, indent=2).encode('utf-8'))
        index_handle.write(compressed)


INDEX_ENTRY_CONSTRUCTORS = [
    BasicIndexEntry,
    ExtendedIndexEntry
]
