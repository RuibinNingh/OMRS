"""内容验收决策必须守住样本身份、覆盖率和改善门槛。"""
from pathlib import Path
import tempfile
import unittest
from tools.boxdetect.audit import immutable
from tools.boxdetect.decision import select,compare
from omrs.trainaudit import save_review


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def fixture(self,name,passed,split='test',conf=.55,reviewed=True,sha='same'):
        out=self.root/'audits'/name
        cases=[{'id':f'{i}-{role}','sample':str(i),'source_sha256':sha+str(i),'role':role} for i in range(5) for role in ('question','answer')]
        immutable(out/'audit.json',{'id':name,'split':split,'conf':conf,'manifest_sha256':'manifest','model_sha256':'model','prompt_sha256':'prompt','cases':cases})
        for c in cases:
            verdict='usable' if int(c['sample'])<passed or c['role']=='question' else 'needs_adjustment'
            immutable(out/(c['id']+'.json'),{'state':'done','judgment':{'verdict':verdict}})
            if reviewed:save_review(self.root,name,c['id'],0,'agree',source='executor')
        return out

    def test_improvement_and_eighty_percent_required(self):
        old=self.fixture('old',3);new=self.fixture('new',4)
        self.assertEqual(compare(old,new,self.root/'ok.json')['recommendation'],'candidate_local')
        same=self.fixture('same',3)
        self.assertEqual(compare(old,same,self.root/'keep.json')['recommendation'],'retain_old')

    def test_unreviewed_or_different_population_rejected(self):
        old=self.fixture('old',3)
        for name,new in [('unreviewed',self.fixture('unreviewed',5,reviewed=False)),('other',self.fixture('other',5,sha='different'))]:
            with self.assertRaises(ValueError):compare(old,new,self.root/(name+'.json'))

    def test_only_predefined_validation_trials_select_threshold(self):
        paths=[self.fixture(str(c),4,split='val',conf=c) for c in (.1,.25,.4,.55)]
        self.assertEqual(select(paths,self.root/'selection.json')['selected'],.55)
        with self.assertRaises(ValueError):select(paths[:3],self.root/'incomplete.json')
        unseen=self.fixture('unseen',5,split='val',conf=.55,reviewed=False)
        with self.assertRaises(ValueError):select(paths[:3]+[unseen],self.root/'unreviewed-val.json')
        bad=self.fixture('test-leak',5,split='test',conf=.55)
        with self.assertRaises(ValueError):select(paths[:3]+[bad],self.root/'leak.json')

    def test_independent_regression_blocks_candidate(self):
        old=self.fixture('old',3);new=self.fixture('new',4)
        ib=self.fixture('ib',5,split='independent');ic=self.fixture('ic',4,split='independent')
        value=compare(old,new,self.root/'decision.json',ib,ic)
        self.assertEqual(value['recommendation'],'retain_old')
        self.assertFalse(value['checks']['independent_pass'])

if __name__=='__main__':unittest.main()
