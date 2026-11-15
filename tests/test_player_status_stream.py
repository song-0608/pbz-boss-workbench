import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from player_status_stream import StatusStream


class StreamTests(unittest.TestCase):
    def line(self,text='状态',session='mine',at=10):
        return ('[Lua] PBZ_PLAYER_UI:STATUS='+json.dumps({'session':session,'at':at,'expires_at':30,'player':'pc','text':text},ensure_ascii=False)+'\n').encode()
    def test_append_only_and_no_reparse_without_changes(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'log';path.write_bytes(self.line());stream=StatusStream(path,'mine')
            self.assertEqual(stream.read(10)['text'],'状态');count=stream.bytes_read
            for _ in range(10):self.assertIsNotNone(stream.read(10))
            self.assertEqual(stream.bytes_read,count)
            with path.open('ab')as out:out.write(self.line('工作台'))
            self.assertEqual(stream.read(11)['text'],'工作台')
            self.assertEqual(stream.bytes_read,count+len(self.line('工作台')))
    def test_split_utf8_line_foreign_session_staleness_and_truncation(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'log';raw=self.line();path.write_bytes(raw[:-3]);stream=StatusStream(path,'mine')
            self.assertIsNone(stream.read(10))
            with path.open('ab')as out:out.write(raw[-3:]+self.line('foreign','other'))
            self.assertEqual(stream.read(10)['text'],'状态');self.assertIsNone(stream.read(14))
            path.write_bytes(b'new log\n');self.assertIsNone(stream.read(14))

    def test_waits_for_new_generation_status_and_recovers_missing_log(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'log';path.write_bytes(self.line('previous assembly'))
            stream=StatusStream(path,'mine',tail_existing=False)
            self.assertIsNone(stream.read(10));self.assertEqual(stream.bytes_read,0)
            with path.open('ab')as out:out.write(self.line('new assembly'))
            self.assertEqual(stream.read(10)['text'],'new assembly')
            path.unlink();self.assertIsNone(stream.read(10))
            path.write_bytes(self.line('new file'));self.assertIsNone(stream.read(10))
            with path.open('ab')as out:out.write(self.line('new status'))
            self.assertEqual(stream.read(10)['text'],'new status')

    def test_backlog_is_bounded_and_nonfinite_or_boolean_times_rejected(self):
        from player_status_stream import valid_status
        value=json.loads(self.line().decode().split('STATUS=',1)[1])
        for at in (True,float('nan'),float('inf')):
            self.assertFalse(valid_status(dict(value,at=at),'mine',10))
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'log';path.write_bytes(b'');stream=StatusStream(path,'mine');stream.read(10)
            path.write_bytes(b'x'*300000+b'\n'+self.line())
            self.assertEqual(stream.read(10)['text'],'状态');self.assertLessEqual(stream.bytes_read,65536)


if __name__=='__main__':unittest.main()
