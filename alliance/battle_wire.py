"""Bounded Wesnoth wire framing and the runtime WML subset used by Alliance.

No macro expansion, file inclusion, Lua evaluation or translation is performed.
All input is data. Repeated child tags preserve their order; duplicate attributes
are rejected rather than allowing an authorization field to be overwritten.
"""
from dataclasses import dataclass, field
import asyncio
import gzip
import re
import struct
import zlib

MAX_FRAME = 65536
MAX_TEXT = 2 * 1024 * 1024
_TAG=re.compile(r"\[(/?)([A-Za-z_][A-Za-z0-9_]*)\]")
_ATTRIBUTE=re.compile(r"([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*")


class WireError(ValueError):
    pass


@dataclass
class Node:
    name: str = ''
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def one(self, name):
        values = [item for item in self.children if item.name == name]
        if len(values) != 1:
            raise WireError('Expected one message tag.')
        return values[0]


def parse(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > MAX_TEXT or '\0' in text:
        raise WireError('Invalid WML size.')
    root = Node()
    stack = [root]
    pos = nodes = 0
    size = len(text)
    while pos < size:
        if text[pos].isspace():
            pos += 1
            continue
        if text[pos] == '#':
            end = text.find('\n', pos)
            pos = size if end < 0 else end + 1
            continue
        if text[pos] == '[':
            match = _TAG.match(text,pos)
            if not match:
                raise WireError('Invalid WML tag.')
            closing, name = match.groups()
            pos = match.end()
            if closing:
                if len(stack) == 1 or stack[-1].name != name:
                    raise WireError('Unbalanced WML tags.')
                stack.pop()
            else:
                nodes += 1
                if nodes > 20000 or len(stack) >= 48:
                    raise WireError('WML structure exceeds limit.')
                child = Node(name)
                stack[-1].children.append(child)
                stack.append(child)
            continue
        match = _ATTRIBUTE.match(text,pos)
        if not match:
            raise WireError('Invalid WML attribute.')
        name = match[1]
        pos = match.end()
        if name in stack[-1].attrs:
            raise WireError('Duplicate WML attribute.')
        if text[pos:pos+2] == '_ ':
            pos += 2
        if pos < size and text[pos] == '"':
            pos += 1
            value = []
            while pos < size:
                if text[pos] == '"':
                    if pos+1 < size and text[pos+1] == '"':
                        value.append('"'); pos += 2; continue
                    pos += 1
                    break
                value.append(text[pos]); pos += 1
            else:
                raise WireError('Unclosed WML string.')
            value = ''.join(value)
            while pos < size and text[pos] in ' \t\r':
                pos += 1
            if pos < size and text[pos] != '\n':
                raise WireError('Unexpected WML string suffix.')
        else:
            end = text.find('\n', pos)
            if end < 0:
                end = size
            value = text[pos:end].strip()
            if any(c in value for c in '[]"'):
                raise WireError('Invalid unquoted WML value.')
            pos = end
        stack[-1].attrs[name] = value
    if len(stack) != 1:
        raise WireError('Unclosed WML tag.')
    return root


def serialize(node):
    def render(item):
        lines = []
        if item.name:
            lines.append('['+item.name+']')
        for key, value in item.attrs.items():
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                raise WireError('Invalid output attribute.')
            value = str(value)
            if '\0' in value:
                raise WireError('Invalid output text.')
            lines.append(key+'="'+value.replace('"', '""')+'"')
        for child in item.children:
            lines.extend(render(child))
        if item.name:
            lines.append('[/'+item.name+']')
        return lines
    return '\n'.join(render(node))+'\n'


def message(name, **attrs):
    return Node(children=[Node(name, attrs)])


def encode(node):
    plain = serialize(node).encode('utf-8')
    if len(plain) > MAX_TEXT:
        raise WireError('Message too large.')
    data = gzip.compress(plain, mtime=0)
    if not 1 <= len(data) <= MAX_FRAME:
        raise WireError('Compressed message too large.')
    return struct.pack('!I', len(data)) + data


def decode(data):
    if not 1 <= len(data) <= MAX_FRAME:
        raise WireError('Frame too large.')
    inflater = zlib.decompressobj(31)
    try:
        plain = inflater.decompress(data, MAX_TEXT + 1)
    except zlib.error:
        raise WireError("Invalid gzip frame.") from None
    if len(plain) > MAX_TEXT or inflater.unconsumed_tail or inflater.unused_data or not inflater.eof:
        raise WireError('Invalid bounded gzip frame.')
    try:
        return parse(plain.decode('utf-8', 'strict'))
    except UnicodeError:
        raise WireError('Invalid UTF-8.') from None


async def receive(reader, timeout=600):
    header = await asyncio.wait_for(reader.readexactly(4), timeout)
    length = struct.unpack('!I', header)[0]
    if not 1 <= length <= MAX_FRAME:
        raise WireError('Invalid frame length.')
    return decode(await asyncio.wait_for(reader.readexactly(length), 15))


async def send(writer, node):
    writer.write(encode(node))
    await asyncio.wait_for(writer.drain(), 15)
