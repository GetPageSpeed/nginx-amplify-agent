"""
Syslog interface using selectors module (Python 3.4+).

Replaces the deprecated asyncore implementation that was removed in Python 3.12.
Adapted from "Tiny Syslog Server in Python" (https://gist.github.com/marcelom/4218010).

SyslogTail spawns a greenlet which runs a UDP syslog server and caches received
messages, returning them when iterated.
"""

# -*- coding: utf-8 -*-
import copy
import selectors
import socket
from collections import deque

from threading import current_thread
from amplify.agent.common.util.threads import spawn

from amplify.agent.common.context import context
from amplify.agent.common.errors import AmplifyException

from amplify.agent.managers.abstract import AbstractManager
from amplify.agent.pipelines.abstract import Pipeline


__author__ = "Grant Hulegaard"
__copyright__ = "Copyright (C) Nginx, Inc. All rights reserved."
__license__ = ""
__maintainer__ = "GetPageSpeed"
__email__ = "info@getpagespeed.com"


SYSLOG_ADDRESSES = set()


class AmplifyAddresssAlreadyInUse(AmplifyException):
    description = "Couldn't start socket listener because address already in use"


class SyslogServer:
    """Simple UDP socket server that listens for and caches syslog packets."""

    def __init__(self, cache, address, chunk_size=8192):
        """Initialize the syslog server.

        Args:
            cache: Shared deque object to store received messages.
            address: Tuple of (host, port) to bind to.
            chunk_size: Maximum size of UDP packets to receive.
        """
        self.cache = cache
        self.chunk_size = chunk_size
        self._closed = False

        # Create and bind UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(False)
        self.socket.bind(address)
        self.address = self.socket.getsockname()
        SYSLOG_ADDRESSES.add(self.address)
        context.log.debug(f"syslog server binding to {str(self.address)}")

        # Create selector for non-blocking I/O
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.socket, selectors.EVENT_READ, self._handle_read)

    def _handle_read(self):
        """Handle incoming UDP data."""
        try:
            data = self.socket.recv(self.chunk_size).strip()
            if data:
                decoded = data.decode("utf-8", errors="replace")
                try:
                    # This implicitly relies on the nginx syslog format specifically
                    log_record = decoded.split("amplify: ", 1)[1]
                    self.cache.append(log_record)
                except (IndexError, Exception):
                    context.log.error(f'error handling syslog message (address:{self.address}, message:"{decoded}")')
                    context.log.debug("additional info:", exc_info=True)
        except BlockingIOError:
            pass  # No data available
        except Exception:
            context.log.debug("error receiving syslog data:", exc_info=True)

    def poll(self, timeout=0.1):
        """Poll for incoming data.

        Args:
            timeout: How long to wait for events (seconds).

        Returns:
            Number of events processed.
        """
        if self._closed:
            return 0

        events = self.selector.select(timeout=timeout)
        for key, _ in events:
            callback = key.data
            callback()
        return len(events)

    def close(self):
        """Close the server and release resources."""
        if self._closed:
            return

        context.log.debug("syslog server closing")
        self._closed = True

        try:
            self.selector.unregister(self.socket)
        except (KeyError, ValueError):
            pass

        self.selector.close()
        self.socket.close()


class SyslogListener(AbstractManager):
    """Container to manage the SyslogServer listen/handle loop."""

    name = "syslog_listener"

    def __init__(self, cache, address, **kwargs):
        """Initialize the listener.

        Args:
            cache: Shared deque for storing messages.
            address: Tuple of (host, port) to bind to.
            **kwargs: Additional arguments passed to AbstractManager.
        """
        super().__init__(**kwargs)
        self.server = SyslogServer(cache, address)

    def start(self):
        """Start the listener loop."""
        current_thread().name = self.name
        context.setup_thread_id()

        self.running = True

        while self.running:
            self._wait(0.1)
            # Increment action ID every listen period
            context.inc_action_id()
            # Poll for events with timeout
            for _ in range(10):  # Process up to 10 events per cycle
                if not self.server.poll(timeout=self.interval / 10):
                    break

    def stop(self):
        """Stop the listener and close the server."""
        self.server.close()
        context.teardown_thread_id()
        super().stop()


class SyslogTail(Pipeline):
    """Pipeline wrapper for interacting with the UDP syslog listener."""

    def __init__(self, address, maxlen=10000, **kwargs):
        """Initialize the syslog tail.

        Args:
            address: Tuple of (host, port) to listen on.
            maxlen: Maximum number of messages to cache.
            **kwargs: Additional arguments passed to the listener.
        """
        super().__init__(name=f"syslog:{str(address)}")
        self.kwargs = kwargs
        self.maxlen = maxlen
        self.cache = deque(maxlen=self.maxlen)
        self.address = address
        self.listener = None
        self.listener_setup_attempts = 0
        self.thread = None

        # Try to start listener right away
        try:
            self._setup_listener(**self.kwargs)
        except AmplifyAddresssAlreadyInUse as e:
            context.log.warning(
                f'failed to start listener during syslog tail init due to "{e.__class__.__name__}", will try later (attempts: {self.listener_setup_attempts})'
            )
            context.log.debug("additional info:", exc_info=True)

        self.running = True

    def __iter__(self):
        """Iterate over cached messages."""
        if not self.listener and self.listener_setup_attempts < 3:
            try:
                self._setup_listener(**self.kwargs)
                context.log.info(
                    f'successfully started listener during "SyslogTail.__iter__()" after {self.listener_setup_attempts} failed attempt(s)'
                )
                self.listener_setup_attempts = 0
            except AmplifyAddresssAlreadyInUse as e:
                if self.listener_setup_attempts < 3:
                    context.log.warning(
                        f'failed to start listener during "SyslogTail.__iter__()" due to "{e.__class__.__name__}", '
                        f"will try again (attempts: {self.listener_setup_attempts})"
                    )
                    context.log.debug("additional info:", exc_info=True)
                else:
                    context.log.error(
                        f"failed to start listener {self.listener_setup_attempts} times, will not try again"
                    )
                    context.log.debug("additional info:", exc_info=True)

        current_cache = copy.deepcopy(self.cache)
        context.log.debug(f"syslog tail returned {len(current_cache)} lines captured from {self.name}")
        self.cache.clear()
        return iter(current_cache)

    def _setup_listener(self, **kwargs):
        """Set up the syslog listener."""
        if self.address in SYSLOG_ADDRESSES:
            self.listener_setup_attempts += 1
            raise AmplifyAddresssAlreadyInUse(
                message=f'cannot initialize "{self.name}" because address is already in use',
                payload=dict(address=self.address, used=list(SYSLOG_ADDRESSES)),
            )

        SYSLOG_ADDRESSES.add(self.address)
        self.listener = SyslogListener(cache=self.cache, address=self.address, **kwargs)
        self.thread = spawn(self.listener.start)

    def stop(self):
        """Stop the syslog tail and clean up resources."""
        if self.running:
            # Remove from used addresses
            addresses_to_remove = {self.address}
            if self.listener and self.listener.server:
                addresses_to_remove.add(self.listener.server.address)

            for address in addresses_to_remove:
                SYSLOG_ADDRESSES.discard(address)

            if self.listener:
                self.listener.stop()
            if self.thread:
                self.thread.kill()

            self.listener = None
            self.thread = None
            self.cache.clear()
            self.running = False
            context.log.debug("syslog tail stopped")

    def __del__(self):
        """Clean up on deletion."""
        try:
            self.stop()
        except Exception:
            pass  # Ignore errors during cleanup
