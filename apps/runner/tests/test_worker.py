import json
import sys
import tempfile
import time
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runner_worker.policy import Policy, NotReady
from runner_worker.journal import Journal, Conflict
from runner_worker.server import validate_request
from runner_worker.execution import evaluate

class WorkerTests(unittest.TestCase):
    def test_resource_policy_and_no_host_mount_or_environment(self):
        policy=Policy('image@sha256:'+'a'*64,'/reviewed/seccomp.json',Path('/private/state'),Path('/private/catalog'),Path('/private/attestation'))
        argv=policy.argv('tutor-demo','abc',time.time()+15,'fixed program')
        for token in ('none','--read-only','65532:65532','ALL','no-new-privileges=true','32','512m','--memory-swap','runsc'):
            self.assertIn(token,argv)
        self.assertNotIn('--volume',argv);self.assertNotIn('--mount',argv);self.assertNotIn('--env',argv)
        self.assertIn('nr_inodes=4000', ' '.join(argv))

    def test_missing_or_expired_attestation_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            policy=Policy('image@sha256:'+'a'*64,str(root/'seccomp'),root,root/'catalog',root/'attestation')
            with self.assertRaises(NotReady):policy.verify()
            (root/'seccomp').write_text('{}');(root/'catalog').write_text('[]')
            (root/'attestation').write_text(json.dumps({'policy':'python-authored-v1','isolation_verified':True,'expires_at':0}))
            with self.assertRaises(NotReady):policy.verify()

    def test_journal_survives_restart_and_rejects_conflicting_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=Journal(directory)
            self.assertEqual(journal.claim('api','key',{'source':'one'}),(True,None))
            restarted=Journal(directory)
            self.assertEqual(restarted.claim('api','key',{'source':'one'}),(False,None))
            with self.assertRaises(Conflict):restarted.claim('api','key',{'source':'two'})
            result={'status':'finished','tests_passed':1}
            restarted.finish('api','key',result)
            self.assertEqual(Journal(directory).lookup('api','key',{'source':'one'}),(True,result))
            with self.assertRaises(Conflict):restarted.finish('api','key',{'status':'other'})

    def test_worker_requires_exact_known_version_and_bounded_source(self):
        body={'protocol_version':1,'exercise_id':'exercise-v1-code','exercise_version':1,'language':'python','source':'def solve(x): return x','mode':'function'}
        catalog={('exercise-v1-code',1):{'cases':[]}}
        self.assertIs(validate_request(body,'key',catalog),catalog[('exercise-v1-code',1)])
        for changed in ({**body,'exercise_version':2},{**body,'protocol_version':True},{**body,'source':'x'*20001},{**body,'extra':'field'}):
            with self.assertRaises(ValueError):validate_request(changed,'key',catalog)

    def test_host_grades_result_and_never_sends_expected_values(self):
        policy=MagicMock();policy.argv.return_value=['docker','create']
        process=MagicMock();process.poll.return_value=0;process.stdin.closed=True
        case={'args':[{'x':2}],'kwargs':{},'expected':4,'visibility':'hidden'}
        seen=[]
        def capture(proc,deadline,budget,payload):
            value=json.loads(payload);seen.append(value)
            self.assertEqual(set(value),{'source','args','kwargs'})
            return 'finished',b'{"value":5}',12
        with patch('runner_worker.execution.command',return_value=b'container'),patch('runner_worker.execution.subprocess.Popen',return_value=process),patch('runner_worker.execution.capture',side_effect=capture),patch('runner_worker.execution.cleanup') as cleanup:
            result=evaluate(policy,'key',{'source':'def solve(p): return 5'},{'cases':[case]})
        self.assertEqual(result['tests_passed'],0);self.assertEqual(result['tests_total'],1)
        cleanup.assert_called_once();self.assertEqual(len(seen),1)

    def test_runtime_cleanup_runs_when_cli_wait_times_out(self):
        policy=MagicMock();policy.argv.return_value=['docker','create']
        process=MagicMock();process.poll.return_value=None;process.stdin.closed=True
        process.wait.side_effect=subprocess.TimeoutExpired('docker',5)
        case={'args':[],'kwargs':{},'expected':1,'visibility':'hidden'}
        with patch('runner_worker.execution.command',return_value=b'container'),patch('runner_worker.execution.subprocess.Popen',return_value=process),patch('runner_worker.execution.capture',return_value=('timeout',b'',0)),patch('runner_worker.execution.cleanup') as cleanup:
            result=evaluate(policy,'key',{'source':'def solve(): return 1'},{'cases':[case]})
        self.assertEqual(result['status'],'timeout')
        process.kill.assert_called_once();cleanup.assert_called_once()

if __name__=='__main__':unittest.main()
