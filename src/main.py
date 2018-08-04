"""BeyondJS is backend framework for building rich internet
application without writing javascript

"""
import logging
import re
from collections import namedtuple
from functools import wraps
from json import dumps
from json import loads
from uuid import uuid4

import daiquiri
import aiohttp
from aiohttp import web


daiquiri.setup(level=logging.DEBUG)

log = logging.getLogger(__name__)


class BeyondException(Exception):
    pass


def generate_unique_key(dictionary):
    for _ in range(255):
        key = uuid4().hex
        if key not in dictionary:
            return key
    raise BeyondException('Seems like the dictionary is full')


class Node(object):  # inspired from nevow
    """Python representaiton of html nodes.

    Text nodes are python strings.

    You must not instantiate this class directly. Instead use the
    global instance `h` of the `PythonHTML` class.

    """

    __slots__ = ('_tag', '_children', '_attributes')

    def __init__(self, tag):
        self._tag = tag
        self._children = list()
        self._attributes = dict()

    def __call__(self, **kwargs):
        """Update node's attributes"""
        self._attributes.update(kwargs)
        return self

    def __repr__(self):
        return '<Node: %s %s>' % (self._tag, self._attributes)

    def append(self, node):
        """Append a single node or string as a child"""
        self._children.append(node)

    def extend(self, nodes):
        [self.append(node) for node in nodes]

    def __getitem__(self, nodes):
        """Add nodes as children"""
        # XXX: __getitem__ is implemented in terms of `Node.append`
        # so that widgets can simply inherit from node and override
        # self.append with the bound `Node.append`.
        if isinstance(nodes, (str, float, int)):
            self.append(nodes)
        elif isinstance(nodes, (list, tuple)):
            [self.append(node) for node in nodes]
        else:
            self.append(nodes)
        return self


def serialize(node):
    """Convert a `Node` hierarchy to a json string.

    Returns two values:

    - the dict representation
    - an event dictionary mapping event keys to callbacks

    """

    events = dict()

    def to_html_attributes(attributes):
        """Filter and convert attributes to html attributes"""
        for key, value in attributes.items():
            if key.startswith('on_'):
                pass
            elif key == 'Class':
                yield 'class', value
            elif key == 'For':
                yield 'for', value
            else:
                yield key, value

    def to_html_events(attributes):
        """Filter and rename attributes referencing callbacks"""
        for key, value in attributes.items():
            if key.startswith('on_'):
                yield key[3:], value

    def to_dict(node):
        """Recursively convert `node` into a dictionary"""
        if isinstance(node, (str, float, int)):
            return node
        else:
            out = dict(tag=node._tag)
            out['attributes'] = dict(to_html_attributes(node._attributes))
            on = dict()
            for event, callback in to_html_events(node._attributes):
                key = generate_unique_key(events)
                events[key] = callback  # XXX: side effect!
                on[event] = key
            if on:
                out['on'] = on
            out['children'] = [to_dict(child) for child in node._children]
            return out

    return to_dict(node), events


class PythonHTML(object):
    """Sugar syntax for creating `Node` instance.

    E.g.

    h.div(id="container", Class="minimal thing", For="something")["Héllo ", "World!"]

    container = h.div(id="container", Class="minimal thing")
    container.append("Héllo World!")

    """

    def __getattr__(self, attribute_name):
        return Node(attribute_name)


h = PythonHTML()


def beyond(callable):
    """There is something beyond javascript ;)"""

    @wraps(callable)
    async def wrapper(*args):
        # execute event handler
        await callable(*args)
        # re-render the page
        event = args[-1]
        html = await event.request.app.render(event)
        # serialize the html and extract event handlers
        html, events = serialize(html)
        # update events handlers
        event.websocket.events = events
        # send html update
        msg = dict(
            html=html,
        )
        await event.websocket.send_str(dumps(msg))

    return wrapper


class Event:

    __slot__ = ('type', 'request', 'websocket', 'path', 'payload')

    def __init__(self, type, request, websocket, path, payload):
        self.type = type
        self.request = request
        self.websocket = websocket
        self.path = path
        self.payload = payload


async def websocket(request):
    """websocket handler"""
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    async for msg in websocket:

        if msg.type == aiohttp.WSMsgType.ERROR:
            msg = 'websocket connection closed with exception %s'
            msg = msg % websocket.exception()
            print(msg)
        elif msg.type == aiohttp.WSMsgType.CLOSE:
            break
        elif msg.type == aiohttp.WSMsgType.TEXT:
            event = loads(msg.data)
            log.debug('websocket got message type: %s', event["type"])
            if event['type'] == 'init':

                # Render the page
                event = Event('init', request, websocket, event['path'], None)
                html = await request.app.render(event)
                # serialize html and extract event handlers
                html, events = serialize(html)
                # update event handlers
                websocket.events = events
                # send html update
                msg = dict(html=html)
                await websocket.send_str(dumps(msg))
            elif event['type'] == 'dom-event':
                # Build backend event
                key = event['key']
                event = Event('dom-event', request, websocket, event['path'], event['event'])  # noqa
                # retrieve callback for event
                callback = websocket.events[key]
                # exec, prolly sending back a response via event.websocket
                await callback(event)
                # render page
                html = await request.app.render(event)
                # serialize html and extract event handlers
                html, events = serialize(html)
                # update event handlers
                websocket.events = events
                # send html update
                msg = dict(html=html)
                await websocket.send_str(dumps(msg))
            else:
                msg = "msg type '%s' is not supported yet" % msg['type']
                raise NotImplementedError(msg)
        else:
            raise NotImplementedError(msg)

    print('websocket connection closed')

    return websocket


with open('index.html', 'rb') as f:
    INDEX = f.read()


async def index(request):
    """Return the index page"""
    return web.Response(body=INDEX, content_type='text/html')


app = web.Application()
app.router.add_route('GET', '/websocket', websocket)
app.router.add_route('GET', '/', index)
app.router.add_static('/static', path='static')
app.router.add_route('GET', '/{path:.+}', index)


Route = namedtuple('Route', ('regex', 'init', 'render'))


class Router:
    """Why yet another router..."""

    def __init__(self):
        self._routes = list()

    def add_route(self, pattern, init, render):
        regex = re.compile(pattern)
        route = Route(regex, init, render)
        self._routes.append(route)

    async def __call__(self, event):
        path = event.path
        print('rendering path: %s' % path)
        for route in self._routes:
            match = route.regex.match(path)
            if match is not None:
                # This is a match
                args = match.groups()
                if event.type == 'init':
                    # call init function for the route
                    await route.init(*args, event)
                # render the route
                html = route.render(*args, event)
                return html
            else:
                # keep looking
                continue
        else:
            # Ark! The route is not defined!
            return h.h1()['No route found']


# XXX: Here begins custom code #########################################

app.database = dict()

app.render = router = Router()  # sic

@beyond
async def chatbox_inputed(event):
    model = event.request.model
    command = event.payload['target.value']
    message = {
        'command': command,
        'prices': {},
        'replies': {'echo': command},
    }
    model['conversation'].append(message)
    return event


def render_chatbot(model):
    log.debug('render chatbot: %r', model)
    shell = h.div(id="shell", Class="chatbot")

    shell.append(h.h1()["LVA"])

    for messages in model['conversation']:
        command = messages['command']
        prices = messages['prices']
        replies = messages['replies']
        shell.append(h.p()[command])
        for chat, reply in replies.items():
            # afficher les replies les moins cheres et proposer les autres
            # avec un code couleur sur le prix
            shell.append(h.p(Class='reply ' + chat)[chat + ': ' + reply])

    chatbox = h.div(id="chatbox")
    chatbox.append(h.input(type="text", on_change=chatbox_inputed))
    # chatbox.append(h.input(type="submit"))

    shell.append(chatbox)

    return shell


async def index_init(event):
    model = {
        'conversation': [],
    }
    event.request.model = model


def index_render(event):
    out = render_chatbot(event.request.model)
    return out


router.add_route(r'^/$', index_init, index_render)


# counter

# async def counter_init(event):
#     event.request.count = 0


# @beyond
# async def increment(event):
#     event.request.count += 1


# def counter_render(event):
#     shell = make_shell()
#     msg = 'The count is %s' % event.request.count
#     subtitle = h.h2()[msg]
#     shell.append(subtitle)
#     button = h.button(on_click=increment)['increment the count']
#     shell.append(button)
#     return shell


# router.add_route(r'^/counter$', counter_init, counter_render)


# start the app at localhost:8080
web.run_app(app)

# <3
