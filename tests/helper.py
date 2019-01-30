import os
import sys
import six
import shutil
from contextlib import contextmanager
from enum import Enum

import tests._common as _common

from beets import util
from beets import library
from beets import importer
from beets import mediafile
from beets import config
from beets import plugins

# Make sure the development versions of the plugins are used
import beetsplug  # noqa: E402
beetsplug.__path__ = [os.path.abspath(
    os.path.join(__file__, '..', '..', 'beetsplug')
)]

from beetsplug import copyartifacts

import logging
log = logging.getLogger("beets")


class LogCapture(logging.Handler):

    def __init__(self):
        logging.Handler.__init__(self)
        self.messages = []

    def emit(self, record):
        self.messages.append(six.text_type(record.msg))


@contextmanager
def capture_log(logger='beets'):
    capture = LogCapture()
    log = logging.getLogger(logger)
    log.addHandler(capture)
    try:
        yield capture.messages
    finally:
        log.removeHandler(capture)



class CopyArtifactsTestCase(_common.TestCase):
    """
    Provides common setup and teardown, a convenience method for exercising the
    plugin/importer, tools to setup a library, a directory containing files
    that are to be imported and an import session. The class also provides stubs
    for the autotagging library and assertions helpers.
    """
    def setUp(self):
        super(CopyArtifactsTestCase, self).setUp()

        plugins._classes = set([copyartifacts.CopyArtifactsPlugin])

        self._setup_library()

        # Install the DummyIO to capture anything directed to stdout
        self.io.install()

    def _run_importer(self):
        """
        Create an instance of the plugin, run the importer, and
        remove/unregister the plugin instance so a new instance can
        be created when this method is run again.
        This is a convenience method that can be called to setup, exercise
        and teardown the system under test after setting any config options
        and before assertions are made regarding changes to the filesystem.
        """
        # Setup
        # Create an instance of the plugin
        plugins.find_plugins()

        # Exercise
        # Run the importer
        self.importer.run()
        # Fake the occurence of the cli_exit event
        plugins.send('cli_exit', lib=self.lib)

        # Teardown
        if plugins._instances:
            classes = list(plugins._classes)

            # Unregister listners
            for event in classes[0].listeners:
                del classes[0].listeners[event][0]

            # Delete the plugin instance so a new one gets created for each test
            del plugins._instances[classes[0]]

        log.debug("--- library structure")
        self._list_files(self.lib_dir)

    def _setup_library(self):
        self.lib_db = os.path.join(self.temp_dir, b'testlib.blb')
        self.lib_dir = os.path.join(self.temp_dir, b'testlib_dir')

        os.mkdir(self.lib_dir)

        self.lib = library.Library(self.lib_db)
        self.lib.directory = self.lib_dir
        self.lib.path_formats = [
            (u'default', os.path.join(u'$artist', u'$album', u'$title')),
            (u'singleton:true', os.path.join(u'singletons', u'$title')),
            (u'comp:true', os.path.join(u'compilations', u'$album', u'$title')),
        ]

    def _create_flat_import_dir(self):
        """
        Creates a directory with media files and artifacts.
        Sets ``self.import_dir`` to the path of the directory. Also sets
        ``self.import_media`` to a list :class:`MediaFile` for all the media files in
        the directory.

        The directory has the following layout
          the_album/
            track_1.mp3
            artifact.file
            artifact.file2
        """
        self._set_import_dir()

        album_path = os.path.join(self.import_dir, b'the_album')
        os.makedirs(album_path)

        # Create artifact
        open(os.path.join(album_path, b'artifact.file'), 'a').close()
        open(os.path.join(album_path, b'artifact.file2'), 'a').close()

        medium = self._create_medium(os.path.join(album_path, b'track_1.mp3'), b'full.mp3')
        self.import_media = [medium]

        log.debug("--- import directory created")
        self._list_files(album_path)

    def _create_medium(self, path, resource_name, album=None):
        """
        Creates and saves a media file object located at path using resource_name
        from the beets test resources directory as initial data
        """

        resource_path = os.path.join(_common.RSRC, resource_name)

        metadata = {
                     'artist': 'Tag Artist',
                     'album':  album or 'Tag Album',
                     'albumartist':  None,
                     'mb_trackid': None,
                     'mb_albumid': None,
                     'comp': None
                   }

        # Copy media file
        shutil.copy(resource_path, path)
        medium = mediafile.MediaFile(path)

        # Set metadata
        metadata['track'] = 1
        metadata['title'] = 'Tag Title 1'
        for attr in metadata:
            setattr(medium, attr, metadata[attr])
        medium.save()

        return medium

    def _set_import_dir(self):
        """
        Sets the import_dir and ensures that it is empty.
        """
        self.import_dir = os.path.join(self.temp_dir, b'testsrcdir')
        if os.path.isdir(self.import_dir):
            shutil.rmtree(self.import_dir)

    def _create_nested_import_dir(self):
        """
        Creates a directory with media files and artifacts nested in subdirectories.
        Sets ``self.import_dir`` to the path of the directory. Also sets
        ``self.import_media`` to a list :class:`MediaFile` for all the media files in
        the directory.

        The directory has the following layout
          the_album/
            disc1/
              track_1.mp3
              artifact1.file
            disc2/
              track_1.mp3
              artifact2.file
        """

    def _setup_import_session(self, import_dir=None,
            delete=False, threaded=False, copy=True,
            singletons=False, move=False, autotag=True):
        config['import']['copy'] = copy
        config['import']['delete'] = delete
        config['import']['timid'] = True
        config['threaded'] = False
        config['import']['singletons'] = singletons
        config['import']['move'] = move
        config['import']['autotag'] = autotag
        config['import']['resume'] = False

        self.importer = TestImportSession(self.lib,
                                loghandler=None,
                                paths=[import_dir or self.import_dir],
                                query=None)

    def _list_files(self, startpath):
        path = startpath.decode('utf8')
        for root, dirs, files in os.walk(path):
            level = root.replace(path, '').count(os.sep)
            indent = u' ' * 4 * (level)
            log.debug(u'{}{}/', indent, os.path.basename(root))
            subindent = u' ' * 4 * (level + 1)
            for f in files:
                log.debug(u'{}{}', subindent, f)

    def assert_in_lib_dir(self, *segments):
        """
        Join the ``segments`` and assert that this path exists in the library
        directory
        """
        self.assertExists(os.path.join(self.lib_dir, *segments))

    def assert_not_in_lib_dir(self, *segments):
        """
        Join the ``segments`` and assert that this path does not exist in
        the library directory
        """
        self.assertNotExists(os.path.join(self.lib_dir, *segments))

    def assert_in_import_dir(self, *segments):
        """
        Join the ``segments`` and assert that this path exists in the import
        directory
        """
        self.assertExists(os.path.join(self.import_dir, *segments))

    def assert_not_in_import_dir(self, *segments):
        """
        Join the ``segments`` and assert that this path does not exist in
        the library directory
        """
        self.assertNotExists(os.path.join(self.import_dir, *segments))

    def assert_number_of_files_in_dir(self, count, *segments):
        """
        Assert that there are ``count`` files in path formed by joining ``segments``
        """
        self.assertEqual(len([name for name in os.listdir(os.path.join(*segments))]), count)


class TestImportSession(importer.ImportSession):
    """ImportSession that can be controlled programaticaly.

    >>> lib = Library(':memory:')
    >>> importer = TestImportSession(lib, paths=['/path/to/import'])
    >>> importer.add_choice(importer.action.SKIP)
    >>> importer.add_choice(importer.action.ASIS)
    >>> importer.default_choice = importer.action.APPLY
    >>> importer.run()

    This imports ``/path/to/import`` into `lib`. It skips the first
    album and imports thesecond one with metadata from the tags. For the
    remaining albums, the metadata from the autotagger will be applied.
    """

    def __init__(self, *args, **kwargs):
        super(TestImportSession, self).__init__(*args, **kwargs)
        self._choices = []
        self._resolutions = []

    default_choice = importer.action.APPLY

    def add_choice(self, choice):
        self._choices.append(choice)

    def clear_choices(self):
        self._choices = []

    def choose_match(self, task):
        try:
            choice = self._choices.pop(0)
        except IndexError:
            choice = self.default_choice

        if choice == importer.action.APPLY:
            return task.candidates[0]
        elif isinstance(choice, int):
            return task.candidates[choice - 1]
        else:
            return choice

    choose_item = choose_match

    Resolution = Enum('Resolution', 'REMOVE SKIP KEEPBOTH')

    default_resolution = 'REMOVE'

    def add_resolution(self, resolution):
        assert isinstance(resolution, self.Resolution)
        self._resolutions.append(resolution)

    def resolve_duplicate(self, task, found_duplicates):
        try:
            res = self._resolutions.pop(0)
        except IndexError:
            res = self.default_resolution

        if res == self.Resolution.SKIP:
            task.set_choice(importer.action.SKIP)
        elif res == self.Resolution.REMOVE:
            task.should_remove_duplicates = True

