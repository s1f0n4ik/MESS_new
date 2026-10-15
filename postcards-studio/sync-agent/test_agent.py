import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from agent import Agent


class SyncAgentTests(unittest.TestCase):
    def test_verified_release_is_installed_and_current_switches_last(self):
        payloads = {f"pdf{number}.pdf": f"pdf-{number}".encode() for number in range(1, 5)}
        release_id = "release-test"
        manifest = {"releaseId": release_id, "files": [
            {"slot": name[:-4], "name": name, "size": len(data),
             "sha256": hashlib.sha256(data).hexdigest()}
            for name, data in payloads.items()
        ]}

        def handler(request: httpx.Request):
            self.assertEqual(request.headers.get("X-Sync-Token"), "token")
            if request.url.path == "/api/sync/latest":
                return httpx.Response(200, json=manifest)
            name = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, content=payloads[name])

        with tempfile.TemporaryDirectory() as directory:
            agent = Agent("http://studio", "token", Path(directory), application="")
            agent.client.close()
            agent.client = httpx.Client(transport=httpx.MockTransport(handler),
                                        headers={"X-Sync-Token": "token"})
            self.assertTrue(agent.sync_once())
            current = json.loads((Path(directory) / "current.json").read_text("utf-8"))
            self.assertEqual(current["releaseId"], release_id)
            for name, data in payloads.items():
                self.assertEqual((Path(directory) / release_id / name).read_bytes(), data)
            self.assertFalse(agent.sync_once())


if __name__ == "__main__":
    unittest.main()

