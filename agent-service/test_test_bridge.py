import tempfile
import unittest
from pathlib import Path
import test_bridge

class BridgeGuards(unittest.TestCase):
    def test_wrong_capability_is_denied_before_database_access(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'runtime').mkdir()
            with self.assertRaises(PermissionError):test_bridge.execute(root,{'action':'status'},'wrong')
    def test_arbitrary_sql_is_not_an_operation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'runtime').mkdir();key=test_bridge.credentials(root)
            with self.assertRaises(ValueError):test_bridge.execute(root,{'action':'query','sql':'SELECT 1'},key)
    def test_production_database_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'runtime').mkdir();key=test_bridge.credentials(root)
            (root/'runtime/test-environment.json').write_text('{"DB_NAME":"ticketlab"}')
            with self.assertRaises(ValueError):test_bridge.execute(root,{'action':'status'},key)

if __name__=='__main__':unittest.main()
