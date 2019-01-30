import os
import sys

from tests.helper import CopyArtifactsTestCase, capture_log
import beets
from beets import config

class CopyArtifactsFilename(CopyArtifactsTestCase):
    """
    Tests to check handling of artifacts with filenames containing unicode characters
    """
    def setUp(self):
        super(CopyArtifactsFilename, self).setUp()

        self._set_import_dir()
        self.album_path = os.path.join(self.import_dir, b'the_album')
        os.makedirs(self.album_path)

        self._setup_import_session(autotag=False)

        config['copyartifacts']['extensions'] = '.file'

    def test_import_dir_with_unicode_character_in_artifact_name_copy(self):
        open(os.path.join(self.album_path, beets.util.bytestring_path(u'\xe4rtifact.file')), 'a').close()
        medium = self._create_medium(os.path.join(self.album_path, b'track_1.mp3'), b'full.mp3')
        self.import_media = [medium]

        self._run_importer()

        self.assert_in_lib_dir(b'Tag Artist', b'Tag Album', beets.util.bytestring_path(u'\xe4rtifact.file'))

    def test_import_dir_with_unicode_character_in_artifact_name_move(self):
        config['import']['move'] = True

        open(os.path.join(self.album_path, beets.util.bytestring_path(u'\xe4rtifact.file')), 'a').close()
        medium = self._create_medium(os.path.join(self.album_path, b'track_1.mp3'), b'full.mp3')
        self.import_media = [medium]

        self._run_importer()

        self.assert_in_lib_dir(b'Tag Artist', b'Tag Album', beets.util.bytestring_path(u'\xe4rtifact.file'))

    def test_import_dir_with_illegal_character_in_album_name(self):
        config['paths']['ext:file'] = str('$albumpath/$artist - $album')

        # Create import directory, illegal filename character used in the album name
        open(os.path.join(self.album_path, b'artifact.file'), 'a').close()
        medium = self._create_medium(os.path.join(self.album_path, b'track_1.mp3'),
                                     b'full.mp3',
                                     b'Tag Album?')
        self.import_media = [medium]

        self._run_importer()

        self.assert_in_lib_dir(b'Tag Artist', b'Tag Album_', b'Tag Artist - Tag Album_.file')

    def test_import_dir_with_format_string_character_in_filename(self):
        # Create import directory, use some Python format string characters in
        # the name. This should catch issues in message logging.
        test_filename = b'albumart{0}.%s.file'

        open(os.path.join(self.album_path, beets.util.bytestring_path(test_filename)), 'a').close()
        medium = self._create_medium(os.path.join(self.album_path, b'track_1.mp3'), b'full.mp3')
        self.import_media = [medium]

        with capture_log() as logs:
            self._run_importer()

        self.assert_in_lib_dir(b'Tag Artist', b'Tag Album', test_filename)
