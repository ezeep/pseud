import uuid

import gevent
from gevent.timeout import Timeout
import msgpack
import pytest
import zmq.green as zmq


def read_once(socket):
    return socket.recv_multipart()


def test_client_creation():
    from pybidirpc._gevent import Client
    from pybidirpc import auth, heartbeat  # NOQA
    identity = __name__
    peer_identity = 'echo'
    client = Client(identity, peer_identity)
    assert client.peer_identity == peer_identity
    assert client.identity == identity
    assert client.security_plugin == 'noop_auth_backend'


def test_client_can_bind():
    from pybidirpc import Client
    from pybidirpc import auth, heartbeat  # NOQA
    endpoint = 'tcp://127.0.0.1:5000'
    identity = __name__
    peer_identity = 'echo'
    client = Client(identity, peer_identity)
    client.bind(endpoint)
    client.stop()


def test_client_can_connect():
    from pybidirpc import Client
    from pybidirpc import auth, heartbeat  # NOQA
    endpoint = 'tcp://127.0.0.1:5000'
    identity = __name__
    peer_identity = 'echo'
    client = Client(identity, peer_identity)
    client.connect(endpoint)
    client.stop()


def make_one_server_socket(identity, endpoint):
    context = zmq.Context.instance()
    router_sock = context.socket(zmq.ROUTER)
    router_sock.identity = identity
    port = router_sock.bind_to_random_port(endpoint)
    return port, router_sock


def make_one_client(identity, peer_identity):
    from pybidirpc._gevent import Client
    from pybidirpc import auth, heartbeat  # NOQA
    client = Client(identity, peer_identity)
    return client


def test_client_method_wrapper():
    from pybidirpc.common import AttributeWrapper
    endpoint = 'inproc://{}'.format(__name__)
    identity = __name__
    peer_identity = 'echo'
    client = make_one_client(identity, peer_identity)
    method_name = 'a.b.c.d'
    with pytest.raises(RuntimeError):
        # If not connected can not call anything
        wrapper = getattr(client, method_name)
    client.connect(endpoint)
    client.start()
    wrapper = getattr(client, method_name)
    assert isinstance(wrapper, AttributeWrapper)
    assert wrapper._part_names == method_name.split('.')
    assert wrapper.name == method_name
    print 'waiting for result'
    with pytest.raises(Timeout):
        future = wrapper()
        future.get(timeout=.2)
    client.stop()


def test_job_executed():
    from pybidirpc.interfaces import OK, VERSION, WORK
    from pybidirpc import auth, heartbeat  # NOQA
    identity = 'client0'
    peer_identity = 'echo'
    endpoint = 'tcp://127.0.0.1'
    port, socket = make_one_server_socket(peer_identity, endpoint)

    client = make_one_client(identity, peer_identity)
    client.connect(endpoint + ':{}'.format(port))

    future = client.please.do_that_job(1, 2, 3, b=4)
    print 'waiting for client work'
    request = gevent.spawn(read_once, socket).get()
    print 'receive from client', request
    server_id, version, uid, message_type, message = request
    assert version == VERSION
    assert uid
    # check it is a real uuid
    uuid.UUID(bytes=uid)
    assert message_type == WORK
    locator, args, kw = msgpack.unpackb(message)
    assert locator == 'please.do_that_job'
    assert args == [1, 2, 3]
    assert kw == {'b': 4}
    reply = [identity, version, uid, OK, msgpack.packb(True)]
    print 'reply from test', reply
    gevent.spawn(socket.send_multipart, reply)
    print 'waiting for result'
    assert future.get() is True
    assert not client.future_pool
    client.stop()
    socket.close()
