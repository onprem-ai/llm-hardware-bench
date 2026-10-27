import importlib.util, unittest
from pathlib import Path
import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
            if (a / '.git').exists())
spec=importlib.util.spec_from_file_location("summarize_fabric",ROOT/"harness/2-preflight-conformance/code/summarize_fabric.py")
m=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m)
class FabricTests(unittest.TestCase):
    def test_integrate_rate(self): self.assertEqual(m.integrate([[0,"10"],[2,"20"]]),30)
    def test_counter_reset(self): self.assertEqual(m.counter_delta([[0,"5"],[1,"8"],[2,"2"]]),(5,1))
    def test_percentile(self): self.assertEqual(m.percentile([1,2,3,4],.5),2.5)
if __name__=="__main__": unittest.main()
