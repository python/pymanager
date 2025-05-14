import pytest

from manage import logging


def test_wrap_and_indent():
    r = list(logging.wrap_and_indent("12345678 12345 123 1 123456 1234567890",
                                     width=8))
    assert r == [
        "12345678",
        "12345",
        "123 1",
        "123456",
        "1234567890",
    ]

    r = list(logging.wrap_and_indent("12345678 12345 123 1 123456 1234567890",
                                     indent=4, width=8))
    assert r == [
        "    12345678",
        "    12345",
        "    123",
        "    1",
        "    123456",
        "    1234567890",
    ]

    r = list(logging.wrap_and_indent("12345678 12345 123 1 123456 1234567890",
                                     indent=4, width=8, hang="AB"))
    assert r == [
        "AB  12345678",
        "    12345",
        "    123",
        "    1",
        "    123456",
        "    1234567890",
    ]

    r = list(logging.wrap_and_indent("12345678 12345 123 1 123456 1234567890",
                                     indent=4, width=8, hang="ABC"))
    assert r == [
        "ABC 12345678",
        "    12345",
        "    123",
        "    1",
        "    123456",
        "    1234567890",
    ]

    r = list(logging.wrap_and_indent("12345678 12345 123 1 123456 1234567890",
                                     indent=3, width=8, hang="ABCD"))
    assert r == [
        "ABC",
        "   12345678",
        "   12345",
        "   123 1",
        "   123456",
        "   1234567890",
    ]
