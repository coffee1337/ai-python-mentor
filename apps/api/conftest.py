"""Guards that keep one test from changing global logging state for the rest.

A suite that silently disables a logger makes unrelated tests fail far from the
cause; this hook fails at the test that did it instead of letting the failure land
on whoever logs next.
"""
import logging

WATCHED = ("mentor.request", "ai.usage", "runner.client")


def pytest_runtest_teardown(item, nextitem):
    problems = []
    for name in WATCHED:
        if logging.getLogger(name).disabled:
            problems.append(f"{item.nodeid} left logger {name!r} disabled")
    if logging.root.manager.disable:
        problems.append(f"{item.nodeid} disabled logging globally (level {logging.root.manager.disable})")
    if problems:
        raise AssertionError("; ".join(problems))
