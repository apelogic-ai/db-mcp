"""Tests for gateway public API surface."""

import inspect

import db_mcp_data.gateway as gateway


def test_module_exposes_create():
    assert callable(gateway.create)


def test_module_exposes_execute():
    assert callable(gateway.execute)


def test_module_exposes_run():
    assert callable(gateway.run)


def test_module_exposes_introspect():
    assert callable(gateway.introspect)


def test_create_is_async():
    assert inspect.iscoroutinefunction(gateway.create)


def test_execute_is_async():
    assert inspect.iscoroutinefunction(gateway.execute)


def test_run_is_async():
    assert inspect.iscoroutinefunction(gateway.run)


def test_introspect_is_not_async():
    assert not inspect.iscoroutinefunction(gateway.introspect)
