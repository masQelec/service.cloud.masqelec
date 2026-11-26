import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock

from lib import pvr_credentials as credentials


DATA = (
    'USER_CODE="test-user"\n'
    'PASS_CODE="test-pass"\n'
)


class CredentialsTests(unittest.TestCase):

    def setUp(self):

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)

        self.path = Path(temp.name) / "user"

        self.net = Mock(return_value={
            "eth0": "00:11:22:33:44:55"
        })

        self.copy = Mock(
            side_effect=self.download
        )

    def download(self, remote, source, folder):

        self.assertEqual(remote, "masqelec")

        self.assertEqual(
            source,
            "masqelec/user/001122334455",
        )

        (
            Path(folder) / "001122334455"
        ).write_text(DATA)

        return True

    def ensure(self):

        return credentials.ensure_credentials(
            self.path,
            get_net_info=self.net,
            copy_remote=self.copy,
        )

    def test_existing_credentials_no_rclone(self):

        self.path.write_text(DATA)

        self.assertEqual(
            self.ensure(), "UNCHANGED"
        )

        self.net.assert_not_called()
        self.copy.assert_not_called()

    def test_initial_provision(self):

        self.assertEqual(
            self.ensure(), "PROVISIONED"
        )

        self.assertEqual(
            self.path.read_text(), DATA
        )

        self.assertEqual(
            self.path.stat().st_mode & 0o777,
            0o600,
        )

        self.assertEqual(
            self.ensure(), "UNCHANGED"
        )

        self.copy.assert_called_once()

    def test_network_failure(self):

        self.copy.side_effect = None
        self.copy.return_value = False

        with self.assertRaises(
            credentials.CredentialsError
        ):
            self.ensure()

        self.assertFalse(self.path.exists())

    def test_invalid_mac(self):

        self.net.return_value = {
            "eth0": "invalid",
        }

        with self.assertRaises(
            credentials.CredentialsError
        ):
            self.ensure()

        self.copy.assert_not_called()

    def test_invalid_existing_preserved(self):

        self.path.write_text("invalid")

        with self.assertRaises(
            credentials.playlist.PlaylistError
        ):
            self.ensure()

        self.assertEqual(
            self.path.read_text(), "invalid"
        )

        self.copy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
