"""Tests for RTL-SDR discovery via sysfs (device_detector.py).

Discovery must read the USB descriptors the kernel cached at plug-in time and
never open the dongle, because a second opener disturbs Kismet's rtl_433.
"""

import subprocess

import pytest

from device_detector import DeviceDetector


def add_usb_device(root, name, **attrs):
    """Create a fake /sys/bus/usb/devices/<name>/ entry with attribute files."""
    entry = root / name
    entry.mkdir()
    for key, value in attrs.items():
        (entry / key).write_text(f"{value}\n")
    return entry


@pytest.fixture
def detector(tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *args, **kwargs: pytest.fail("SDR discovery must not run a subprocess"),
    )
    det = DeviceDetector()
    det.sysfs_usb = str(tmp_path)
    return det, tmp_path


def test_finds_rtlsdr_dongle_from_sysfs_attributes(detector):
    det, root = detector
    add_usb_device(root, "usb1", idVendor="1d6b", idProduct="0002",
                   manufacturer="Linux", product="xHCI Host Controller", busnum=1, devnum=1)
    add_usb_device(root, "1-1.2", idVendor="046d", idProduct="c52b",
                   manufacturer="Logitech", product="USB Receiver", busnum=1, devnum=3)
    add_usb_device(root, "1-1.3", idVendor="0bda", idProduct="2838", manufacturer="Realtek",
                   product="RTL2838UHIDIR", serial="00000001", busnum=1, devnum=4)
    (root / "1-1.3:1.0").mkdir()  # interface entry, has no idVendor

    devices = det.detect_sdr_devices()

    assert [d["device"] for d in devices] == ["rtl433-0"]
    dev = devices[0]
    assert dev["device_id"] == "0"
    assert dev["name"] == "Realtek RTL2838UHIDIR"
    assert dev["manufacturer"] == "Realtek"
    assert dev["model"] == "RTL2838UHIDIR"
    assert dev["serial"] == "00000001"
    assert dev["type"] == "RTL-SDR"
    assert dev["status"] == "available"
    assert dev["default_frequency"] == "433920000"


def test_numbers_dongles_by_bus_then_device_number(detector):
    det, root = detector
    add_usb_device(root, "1-1.1", idVendor="0bda", idProduct="2838", manufacturer="Realtek",
                   product="B", serial="BBB", busnum=1, devnum=7)
    add_usb_device(root, "1-1.4", idVendor="0bda", idProduct="2832", manufacturer="Realtek",
                   product="A", serial="AAA", busnum=1, devnum=3)

    devices = det.detect_sdr_devices()

    assert [(d["device"], d["serial"]) for d in devices] == [("rtl433-0", "AAA"), ("rtl433-1", "BBB")]


def test_missing_serial_falls_back_to_device_index(detector):
    det, root = detector
    add_usb_device(root, "1-1.3", idVendor="0bda", idProduct="2838", manufacturer="Realtek",
                   product="RTL2838UHIDIR", busnum=1, devnum=4)

    devices = det.detect_sdr_devices()

    assert devices[0]["serial"] == "0"


def test_missing_sysfs_tree_yields_no_devices_and_no_subprocess(detector):
    det, root = detector
    det.sysfs_usb = str(root / "does-not-exist")

    assert det.detect_sdr_devices() == []
