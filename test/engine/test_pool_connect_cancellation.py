# Copyright 2026 the SQLAlchemy authors and contributors
#
# SPDX-License-Identifier: MIT

"""Connect-event cleanup must not suppress async task cancellation."""

import asyncio

import pytest

from sqlalchemy import event
from sqlalchemy.pool import NullPool
from sqlalchemy.testing import fixtures
from sqlalchemy.util import await_only
from sqlalchemy.util import greenlet_spawn


class PoolConnectCancellationTest(fixtures.TestBase):
    def test_cancel_during_async_cleanup_propagates(self):
        async def scenario():
            closing = asyncio.Event()
            record_holder = []

            class Connection:
                def close(self):
                    async def close_async():
                        closing.set()
                        await asyncio.Event().wait()

                    await_only(close_async())

            pool = NullPool(creator=Connection)

            @event.listens_for(pool, "connect")
            def fail_connect(connection, record):
                record_holder.append(record)
                raise RuntimeError("connect event failed")

            task = asyncio.create_task(greenlet_spawn(pool.connect))
            await asyncio.wait_for(closing.wait(), timeout=5)
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=5)
            assert task.cancelled()
            assert len(record_holder) == 1
            assert record_holder[0].dbapi_connection is None

        asyncio.run(scenario())

    def test_sync_cleanup_error_does_not_hide_connect_error(self):
        records = []

        class Connection:
            def close(self):
                raise ValueError("cleanup failed")

        pool = NullPool(creator=Connection)

        @event.listens_for(pool, "connect")
        def fail_connect(connection, record):
            records.append(record)
            raise RuntimeError("connect event failed")

        with pytest.raises(RuntimeError, match="connect event failed"):
            pool.connect()

        assert len(records) == 1
        assert records[0].dbapi_connection is None

    def test_successful_async_cleanup_preserves_original_event_error(self):
        async def scenario():
            records = []
            was_closed = []

            class Connection:
                def close(self):
                    async def close_async():
                        was_closed.append(True)

                    await_only(close_async())

            pool = NullPool(creator=Connection)

            @event.listens_for(pool, "connect")
            def fail_connect(connection, record):
                records.append(record)
                raise RuntimeError("connect event failed")

            with pytest.raises(RuntimeError, match="connect event failed"):
                await greenlet_spawn(pool.connect)

            assert was_closed == [True]
            assert len(records) == 1
            assert records[0].dbapi_connection is None

        asyncio.run(scenario())
