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


    def test_mediation_archive_is_verified_and_never_replaces_exhibition_release(self):
        payloads={'editable.json':'{"pages":{}}'.encode(),'pdf4.pdf':b'%PDF-test'}
        manifest={'projectId':42,'version':'r0000000001','files':[{'name':name,'size':len(data),
            'sha256':hashlib.sha256(data).hexdigest()} for name,data in payloads.items()]}
        def handler(request):
            if request.url.path=='/api/sync/mediations':return httpx.Response(200,json=[manifest])
            return httpx.Response(200,content=payloads[request.url.path.rsplit('/',1)[-1]])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'current.json').write_text('{"releaseId":"keep-this-release"}','utf-8')
            agent=Agent('http://studio','token',root,application='')
            agent.client.close();agent.client=httpx.Client(transport=httpx.MockTransport(handler))
            self.assertEqual(agent.sync_mediations(),1)
            self.assertEqual(agent.sync_mediations(),0)
            self.assertEqual(json.loads((root/'current.json').read_text())['releaseId'],'keep-this-release')
            latest=root/'Медиации/42/latest.json'
            self.assertEqual(json.loads(latest.read_text('utf-8'))['version'],'r0000000001')
            manifest['version']='r0000000002';manifest['files'][0]['sha256']='bad-hash'
            with self.assertRaises(RuntimeError):agent.sync_mediations()
            self.assertEqual(json.loads(latest.read_text('utf-8'))['version'],'r0000000001')


if __name__ == "__main__":
    unittest.main()

