"""Actual binary protocol tests; no services, accounts or runtime are accessed."""
import asyncio
import gzip
import random
import struct
import unittest
from alliance.battle_wire import Node, WireError, parse, serialize, message, encode, decode, receive, MAX_FRAME, MAX_TEXT

class WireTests(unittest.TestCase):
    def test_nested_repeated_tags_and_binary_roundtrip(self):
        root=Node(children=[Node('turn',children=[Node('command',{'from_side':'1'},[
            Node('move',{'x':'1,2,3','y':'4,5,6'}),Node('label',{'text':'日本語 "quoted"\nsecond line'})]),
            Node('command',children=[Node('end_turn',{'next_player_number':'2'})])])])
        encoded=encode(root)
        self.assertEqual(struct.unpack('!I',encoded[:4])[0],len(encoded)-4)
        self.assertEqual(decode(encoded[4:]),root)
        self.assertEqual(parse(serialize(root)),root)
    def test_wesnoth_quoted_escape_and_comment(self):
        text='# generated\n[turn]\n[command]\ntext=_ "hello ""world"""\nnumber=12\n[/command]\n[/turn]\n'
        node=parse(text).one('turn').one('command')
        self.assertEqual(node.attrs,{'text':'hello "world"','number':'12'})
    def test_reject_ambiguous_or_unbalanced_documents(self):
        values=['x="a"\nx="b"\n','[a]\n[/b]\n','[/a]\n','[a]\n','x="unclosed',
                'x="one" y="two"\n','[+a]\n[/a]','{FILE file}\n','x=bad[value]\n','x="nul\0"\n',
                '[a]\n'*49+'[/a]\n'*49,'[a]\n[/a]\n'*20001]
        for value in values:
            with self.subTest(value=value[:50]),self.assertRaises(WireError):parse(value)
    def test_reject_truncated_invalid_or_multimember_gzip(self):
        good=encode(message('alliance_health'))[4:]
        for payload in (b'',b'x',good[:-1],good+good,good+b'trailing',gzip.compress(b'\xff'),
                        gzip.compress(b'x'*(MAX_TEXT+1)),b'a'*(MAX_FRAME+1)):
            with self.subTest(length=len(payload)),self.assertRaises(WireError):decode(payload)
    def test_randomized_roundtrip_preserves_all_runtime_text(self):
        rng=random.Random(12)
        chars='azAZ019 []=\t\n"日本語é'
        for _ in range(300):
            text=''.join(rng.choice(chars) for _ in range(rng.randrange(500)))
            node=message('message',message=text,sender='Player')
            self.assertEqual(decode(encode(node)[4:]),node)
    def test_partial_socket_reads_and_header_bounds(self):
        async def check():
            reader=asyncio.StreamReader();node=message('alliance_health');payload=encode(node)
            async def feed():
                for byte in payload:
                    reader.feed_data(bytes([byte]));await asyncio.sleep(0)
                reader.feed_eof()
            producer=asyncio.create_task(feed())
            self.assertEqual(await receive(reader,1),node);await producer
            for length in (0,MAX_FRAME+1):
                bad=asyncio.StreamReader();bad.feed_data(struct.pack('!I',length));bad.feed_eof()
                with self.assertRaises(WireError):await receive(bad,1)
            truncated=asyncio.StreamReader();truncated.feed_data(payload[:-1]);truncated.feed_eof()
            with self.assertRaises(asyncio.IncompleteReadError):await receive(truncated,1)
            with self.assertRaises(asyncio.TimeoutError):await receive(asyncio.StreamReader(),.01)
        asyncio.run(check())

if __name__=='__main__':unittest.main()
