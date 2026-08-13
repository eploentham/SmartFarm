# sdfm/flight/modes.py

from __future__ import annotations

from enum import Enum

from pymavlink import mavutil


class FlightMode(str, Enum):
    """
    Flight modes used by DR01 / SDFM.

    Keep this list intentionally small.
    Only modes SDFM actually uses should be added here.
    """

    STABILIZE = "STABILIZE"
    ALT_HOLD = "ALT_HOLD"
    LOITER = "LOITER"
    GUIDED = "GUIDED"
    RTL = "RTL"
    LAND = "LAND"


class FlightModeError(RuntimeError):
    """
    Raised when a requested flight mode is unavailable
    or cannot be resolved.
    """


def normalize_mode(
    mode: str | FlightMode,
) -> FlightMode:
    """
    Convert string or FlightMode into FlightMode enum.

    Examples:
        normalize_mode("guided")
        normalize_mode("GUIDED")
        normalize_mode(FlightMode.GUIDED)
    """

    if isinstance(mode, FlightMode):
        return mode

    try:
        return FlightMode(
            mode.strip().upper()
        )

    except (ValueError, AttributeError) as exc:
        raise FlightModeError(
            f"UNSUPPORTED_FLIGHT_MODE: {mode}"
        ) from exc


def get_mode_mapping(
    master,
) -> dict[str, int]:
    """
    Return mode name -> mode id mapping from pymavlink.

    Example:
        {
            "STABILIZE": 0,
            "GUIDED": 4,
            "LOITER": 5,
            ...
        }
    """

    mapping = master.mode_mapping()

    if not mapping:
        raise FlightModeError(
            "FLIGHT_MODE_MAPPING_UNAVAILABLE"
        )

    return {
        str(name).upper(): int(mode_id)
        for name, mode_id in mapping.items()
    }


def get_mode_id(
    master,
    mode: str | FlightMode,
) -> int:
    """
    Resolve SDFM FlightMode to ArduPilot custom mode id.
    """

    flight_mode = normalize_mode(
        mode
    )

    mapping = get_mode_mapping(
        master
    )

    try:
        return mapping[
            flight_mode.value
        ]

    except KeyError as exc:
        raise FlightModeError(
            f"FLIGHT_MODE_NOT_AVAILABLE: "
            f"{flight_mode.value}"
        ) from exc


def mode_matches(
    current_mode: str | None,
    expected_mode: str | FlightMode,
) -> bool:
    """
    Compare current telemetry mode with expected mode.

    Returns False if telemetry mode is unavailable.
    """

    if current_mode is None:
        return False

    expected = normalize_mode(
        expected_mode
    )

    return (
        current_mode.strip().upper()
        == expected.value
    )


def mode_from_heartbeat(
    heartbeat,
) -> str | None:
    """
    Extract human-readable mode from MAVLink HEARTBEAT.

    This is useful for diagnostics.
    Production telemetry normally gets mode through TelemetryState.
    """

    if heartbeat is None:
        return None

    try:
        mode = mavutil.mode_string_v10(
            heartbeat
        )

    except Exception:
        return None

    if not mode:
        return None

    return str(mode).upper()