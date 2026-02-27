"""
Tests for Pipeline - Breakable message flow dispatcher.

This test suite covers:
1. Pipeline break behavior (when next() is not called)
2. next() continuation logic
3. Priority-based handler chain
4. Pattern matching with on_re()
5. Error handling
6. Concurrent dispatch (thread safety)
"""

import pytest

import lumia
from lumia.core.box import Box
from lumia.core.pipeline import RegistrationError
from lumia.core.utils import UtilsError


class TestPipelineBreak:
    """Test Pipeline break behavior."""

    def test_pipeline_breaks_without_next(self):
        """Pipeline should break if handler doesn't call next()."""
        execution_order = []

        @lumia.pipe.on('test.break', priv=30)
        def handler1(content: Box):
            execution_order.append('handler1')
            # Don't call next() - chain should break here

        @lumia.pipe.on('test.break', priv=20)
        def handler2(content: Box):
            execution_order.append('handler2')

        @lumia.pipe.on('test.break', priv=10)
        def handler3(content: Box):
            execution_order.append('handler3')

        # Start pipeline
        lumia.pipe.start('test.break', Box.any('data'))

        # Only handler1 should execute
        assert execution_order == ['handler1']

    def test_pipeline_continues_with_next(self):
        """Pipeline should continue if handler calls next()."""
        execution_order = []

        @lumia.pipe.on('test.continue', priv=30)
        def handler1(content: Box):
            execution_order.append('handler1')
            lumia.utils.next()  # Continue to next handler

        @lumia.pipe.on('test.continue', priv=20)
        def handler2(content: Box):
            execution_order.append('handler2')
            lumia.utils.next()  # Continue to next handler

        @lumia.pipe.on('test.continue', priv=10)
        def handler3(content: Box):
            execution_order.append('handler3')
            # Last handler doesn't need to call next()

        # Start pipeline
        lumia.pipe.start('test.continue', Box.any('data'))

        # All handlers should execute
        assert execution_order == ['handler1', 'handler2', 'handler3']

    def test_pipeline_breaks_at_middle_handler(self):
        """Pipeline should break at the handler that doesn't call next()."""
        execution_order = []

        @lumia.pipe.on('test.middle.break', priv=30)
        def handler1(content: Box):
            execution_order.append('handler1')
            lumia.utils.next()

        @lumia.pipe.on('test.middle.break', priv=20)
        def handler2(content: Box):
            execution_order.append('handler2')
            # Don't call next() - chain breaks here

        @lumia.pipe.on('test.middle.break', priv=10)
        def handler3(content: Box):
            execution_order.append('handler3')

        # Start pipeline
        lumia.pipe.start('test.middle.break', Box.any('data'))

        # Only handler1 and handler2 should execute
        assert execution_order == ['handler1', 'handler2']


class TestPipelineExecution:
    """Test Pipeline execution order and priority."""

    def test_pipeline_execution_order(self):
        """Handlers should execute in priority order (higher priv first)."""
        execution_order = []

        @lumia.pipe.on('test.order', priv=10)
        def handler1(content: Box):
            execution_order.append('handler1')
            lumia.utils.next()

        @lumia.pipe.on('test.order', priv=30)
        def handler2(content: Box):
            execution_order.append('handler2')
            lumia.utils.next()

        @lumia.pipe.on('test.order', priv=20)
        def handler3(content: Box):
            execution_order.append('handler3')
            lumia.utils.next()

        # Start pipeline
        lumia.pipe.start('test.order', Box.any('data'))

        # Should execute in priority order: 30, 20, 10
        assert execution_order == ['handler2', 'handler3', 'handler1']

    def test_pipeline_same_priority_uses_registration_order(self):
        """Handlers with same priority should execute in registration order."""
        execution_order = []

        @lumia.pipe.on('test.tiebreak', priv=10)
        def handler1(content: Box):
            execution_order.append('handler1')
            lumia.utils.next()

        @lumia.pipe.on('test.tiebreak', priv=10)
        def handler2(content: Box):
            execution_order.append('handler2')
            lumia.utils.next()

        @lumia.pipe.on('test.tiebreak', priv=10)
        def handler3(content: Box):
            execution_order.append('handler3')

        # Start pipeline
        lumia.pipe.start('test.tiebreak', Box.any('data'))

        # Should execute in registration order
        assert execution_order == ['handler1', 'handler2', 'handler3']

    def test_pipeline_no_handlers(self):
        """Pipeline with no handlers should not raise error."""
        # Should not raise any exception
        lumia.pipe.start('test.no.handlers', Box.any('data'))

    def test_pipeline_conditional_flow(self):
        """Pipeline can implement conditional flow with next()."""
        execution_log = []

        @lumia.pipe.on('test.conditional', priv=100)
        def filter_handler(content: Box):
            data = content.into()
            execution_log.append(('filter', data))
            if data.get('should_process'):
                lumia.utils.next()
            # Otherwise, break chain

        @lumia.pipe.on('test.conditional', priv=50)
        def process_handler(content: Box):
            execution_log.append(('process', content.into()))
            lumia.utils.next()

        # Test with should_process=True
        lumia.pipe.start('test.conditional', Box.any({'should_process': True, 'value': 1}))
        assert len(execution_log) == 2
        assert execution_log[0][0] == 'filter'
        assert execution_log[1][0] == 'process'

        # Reset log
        execution_log.clear()

        # Test with should_process=False
        lumia.pipe.start('test.conditional', Box.any({'should_process': False, 'value': 2}))
        assert len(execution_log) == 1
        assert execution_log[0][0] == 'filter'


class TestPipelineErrorHandling:
    """Test Pipeline error handling."""

    def test_pipeline_handler_error_breaks_chain(self):
        """Pipeline handler error should break the chain."""
        execution_order = []

        @lumia.pipe.on('test.error', priv=30)
        def handler1(content: Box):
            execution_order.append('handler1')
            lumia.utils.next()

        @lumia.pipe.on('test.error', priv=20)
        def handler2(content: Box):
            execution_order.append('handler2')
            raise ValueError("Handler error")

        @lumia.pipe.on('test.error', priv=10)
        def handler3(content: Box):
            execution_order.append('handler3')

        # Start pipeline (handler2 will fail)
        with pytest.warns(RuntimeWarning, match="Pipeline handler failed"):
            lumia.pipe.start('test.error', Box.any('data'))

        # Only handler1 and handler2 should execute (chain breaks on error)
        assert execution_order == ['handler1', 'handler2']

    def test_next_outside_pipeline_raises_error(self):
        """Calling next() outside pipeline context should raise error."""
        with pytest.raises(UtilsError, match="next\\(\\) called outside of pipeline context"):
            lumia.utils.next()


class TestPipelinePatternMatching:
    """Test Pipeline pattern matching with on_re()."""

    def test_pipeline_pattern_matching(self):
        """Pattern-based handlers should match glob patterns."""
        execution_log = []

        @lumia.pipe.on_re('msg.*.process', priv=10)
        def handler(src: str, content: Box):
            execution_log.append((src, content.into()))
            lumia.utils.next()

        # Should match
        lumia.pipe.start('msg.qq.process', Box.any('data1'))
        lumia.pipe.start('msg.telegram.process', Box.any('data2'))

        # Should not match
        lumia.pipe.start('msg.process', Box.any('data3'))
        lumia.pipe.start('msg.qq.telegram.process', Box.any('data4'))

        # Verify matches
        assert len(execution_log) == 2
        assert execution_log[0] == ('msg.qq.process', 'data1')
        assert execution_log[1] == ('msg.telegram.process', 'data2')

    def test_pipeline_pattern_requires_src_parameter(self):
        """Pattern-based handlers must have 'src' as first parameter."""
        with pytest.raises(RegistrationError, match="must have 'src' as first parameter"):
            @lumia.pipe.on_re('test.pattern.*', priv=10)
            def bad_handler(content: Box):  # Missing 'src' parameter
                pass

    def test_pipeline_exact_and_pattern_both_match(self):
        """Both exact and pattern handlers should execute."""
        execution_log = []

        @lumia.pipe.on('test.exact', priv=20)
        def exact_handler(content: Box):
            execution_log.append('exact')
            lumia.utils.next()

        @lumia.pipe.on_re('test.*', priv=10)
        def pattern_handler(src: str, content: Box):
            execution_log.append('pattern')
            lumia.utils.next()

        lumia.pipe.start('test.exact', Box.any('data'))

        # Both should execute (exact has higher priority)
        assert execution_log == ['exact', 'pattern']


class TestPipelineConcurrent:
    """Test concurrent pipeline dispatch (thread safety)."""

    def test_concurrent_pipeline_dispatch(self):
        """Multiple threads dispatching pipelines should not interfere."""
        import threading

        execution_counts = {'count': 0, 'lock': threading.Lock()}

        @lumia.pipe.on('test.concurrent', priv=10)
        def handler(content: Box):
            with execution_counts['lock']:
                execution_counts['count'] += 1
            lumia.utils.next()

        # Dispatch from multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(
                target=lambda idx=i: lumia.pipe.start('test.concurrent', Box.any(f'data-{idx}'))
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All dispatches should have executed
        assert execution_counts['count'] == 10

    def test_concurrent_pipeline_with_breaks(self):
        """Concurrent pipeline execution with conditional breaks should be thread-safe."""
        import threading

        execution_counts = {'filter': 0, 'process': 0, 'lock': threading.Lock()}

        @lumia.pipe.on('test.concurrent.break', priv=100)
        def filter_handler(content: Box):
            with execution_counts['lock']:
                execution_counts['filter'] += 1
            if content.into() % 2 == 0:
                lumia.utils.next()
            # Odd numbers break chain

        @lumia.pipe.on('test.concurrent.break', priv=50)
        def process_handler(content: Box):
            with execution_counts['lock']:
                execution_counts['process'] += 1

        # Dispatch from multiple threads (5 even, 5 odd)
        threads = []
        for i in range(10):
            thread = threading.Thread(
                target=lambda idx=i: lumia.pipe.start('test.concurrent.break', Box.any(idx))
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All filters should execute, only even numbers should reach process
        assert execution_counts['filter'] == 10
        assert execution_counts['process'] == 5

    def test_concurrent_pattern_matching(self):
        """Concurrent pattern-based dispatch should be thread-safe."""
        import threading

        execution_counts = {'count': 0, 'lock': threading.Lock()}

        @lumia.pipe.on_re('test.concurrent.pattern.*', priv=10)
        def handler(src: str, content: Box):
            with execution_counts['lock']:
                execution_counts['count'] += 1
            lumia.utils.next()

        # Dispatch from multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(
                target=lambda idx=i: lumia.pipe.start(f'test.concurrent.pattern.{idx}', Box.any(f'data-{idx}'))
            )
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # All dispatches should have executed
        assert execution_counts['count'] == 10

