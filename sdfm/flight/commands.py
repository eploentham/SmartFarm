# sdfm/flight/commands.py

from __future__ import annotations

import threading
import time
from typing import Callable

from pymavlink import mavutil

from sdfm.core.result import (
    OperationResult,
    ResultCode,
)
from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.modes import (
    FlightMode,
    FlightModeError,
    get_mode_id,
    mode_matches,
)
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState


DEFAULT_ACK_TIMEOUT_SEC = 3.0
DEFAULT_STATE_TIMEOUT_SEC = 5.0
DEFAULT_VERIFY_INTERVAL_SEC = 0.05


class FlightCommands:
    """
    SDFM flight command layer.

    Standard command flow:

        COMMAND
           ↓
        COMMAND_ACK
           ↓
        VERIFY STATE
           ↓
        TIMEOUT
           ↓
        SUCCESS / FAILED

    Important:
    COMMAND_ACK = ACCEPTED does NOT mean that the requested
    vehicle state has actually been reached.

    At this stage only DISARMED-safe mode operations are implemented.
    ARM / TAKEOFF / LAND will be added later.
    """

    def __init__(
        self,
        pixhawk: PixhawkConnection,
        router: MavlinkRouter,
        telemetry: TelemetryState,
    ) -> None:

        self.pixhawk = pixhawk
        self.router = router
        self.telemetry = telemetry

        # Only one important flight command may wait for an ACK
        # at a time.
        self._command_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    def _check_command_environment(
        self,
    ) -> OperationResult | None:
        """
        Verify infrastructure required before sending a command.

        Returns None when environment is OK.
        """

        if not self.pixhawk.connected:
            return OperationResult.failed(
                ResultCode.PIXHAWK_LOST,
                "Pixhawk is not connected",
            )

        if not self.router.running:
            return OperationResult.failed(
                ResultCode.INTERNAL_ERROR,
                "MAVLink router is not running",
            )

        heartbeat_age = (
            self.telemetry.heartbeat_age()
        )

        if heartbeat_age is None:
            return OperationResult.failed(
                ResultCode.PIXHAWK_LOST,
                "No Pixhawk heartbeat available",
            )

        if heartbeat_age > 3.0:
            return OperationResult.failed(
                ResultCode.PIXHAWK_LOST,
                "Pixhawk heartbeat is stale",
                details={
                    "heartbeat_age_sec": heartbeat_age,
                },
            )

        return None

    def _wait_until(
        self,
        predicate: Callable[[], bool],
        timeout_sec: float,
        interval_sec: float = DEFAULT_VERIFY_INTERVAL_SEC,
    ) -> bool:
        """
        Wait until predicate becomes True or timeout expires.

        Uses monotonic time because flight timeout logic must not
        depend on wall-clock changes.
        """

        deadline = (
            time.monotonic()
            + timeout_sec
        )

        while time.monotonic() < deadline:

            if predicate():
                return True

            time.sleep(interval_sec)

        # One final check at timeout boundary.
        return predicate()

    # ------------------------------------------------------------------
    # COMMAND_ACK
    # ------------------------------------------------------------------

    @staticmethod
    def _ack_name(
        result: int,
    ) -> str:
        """
        Convert MAV_RESULT numeric value into readable text.
        """

        names = {
            mavutil.mavlink.MAV_RESULT_ACCEPTED:
                "ACCEPTED",

            mavutil.mavlink.MAV_RESULT_TEMPORARILY_REJECTED:
                "TEMPORARILY_REJECTED",

            mavutil.mavlink.MAV_RESULT_DENIED:
                "DENIED",

            mavutil.mavlink.MAV_RESULT_UNSUPPORTED:
                "UNSUPPORTED",

            mavutil.mavlink.MAV_RESULT_FAILED:
                "FAILED",

            mavutil.mavlink.MAV_RESULT_IN_PROGRESS:
                "IN_PROGRESS",
        }

        cancelled = getattr(
            mavutil.mavlink,
            "MAV_RESULT_CANCELLED",
            None,
        )

        if (
            cancelled is not None
            and result == cancelled
        ):
            return "CANCELLED"

        return names.get(
            result,
            f"UNKNOWN_{result}",
        )

    def _check_ack(
        self,
        ack,
        command_id: int,
    ) -> OperationResult | None:
        """
        Interpret COMMAND_ACK.

        Returns:
            None:
                ACK allows us to continue to state verification.

            OperationResult:
                Command failed at ACK stage.
        """

        if ack is None:
            return OperationResult.failed(
                ResultCode.ACK_TIMEOUT,
                "COMMAND_ACK timeout",
                details={
                    "command_id": command_id,
                },
            )

        ack_result = ack.result

        details = {
            "command_id": command_id,
            "ack_result": ack_result,
            "ack_result_name":
                self._ack_name(ack_result),
        }

        #
        # ACCEPTED:
        # command was accepted.
        #
        # IN_PROGRESS:
        # command processing has started.
        #
        # Neither proves that the target vehicle state
        # has actually been reached.
        #
        if ack_result in (
            mavutil.mavlink.MAV_RESULT_ACCEPTED,
            mavutil.mavlink.MAV_RESULT_IN_PROGRESS,
        ):
            return None

        if ack_result == mavutil.mavlink.MAV_RESULT_DENIED:
            return OperationResult.failed(
                ResultCode.COMMAND_DENIED,
                "Command denied by Pixhawk",
                details=details,
            )

        return OperationResult.failed(
            ResultCode.COMMAND_FAILED,
            (
                "Command rejected by Pixhawk: "
                f"{self._ack_name(ack_result)}"
            ),
            details=details,
        )

    # ------------------------------------------------------------------
    # Flight mode
    # ------------------------------------------------------------------

    def set_mode(
        self,
        mode: str | FlightMode,
        *,
        ack_timeout_sec: float = DEFAULT_ACK_TIMEOUT_SEC,
        state_timeout_sec: float = DEFAULT_STATE_TIMEOUT_SEC,
    ) -> OperationResult:
        """
        Change ArduPilot flight mode.

        Flow:

            check connection
                 ↓
            resolve mode
                 ↓
            SEND MAV_CMD_DO_SET_MODE
                 ↓
            wait COMMAND_ACK
                 ↓
            check ACK result
                 ↓
            VERIFY TelemetryState.flight_mode
                 ↓
            SUCCESS / MODE_CHANGE_FAILED

        This function does not ARM the vehicle.
        """

        with self._command_lock:

            # ----------------------------------------------------------
            # Environment
            # ----------------------------------------------------------

            environment_error = (
                self._check_command_environment()
            )

            if environment_error is not None:
                return environment_error

            # ----------------------------------------------------------
            # Resolve mode
            # ----------------------------------------------------------

            try:
                flight_mode = (
                    mode
                    if isinstance(mode, FlightMode)
                    else FlightMode(
                        mode.strip().upper()
                    )
                )

                mode_id = get_mode_id(
                    self.pixhawk.master,
                    flight_mode,
                )

            except (
                FlightModeError,
                ValueError,
                AttributeError,
            ) as exc:

                return OperationResult.failed(
                    ResultCode.MODE_CHANGE_FAILED,
                    str(exc),
                )

            current_mode = (
                self.telemetry.flight_mode
            )

            #
            # Avoid unnecessary command.
            #
            if mode_matches(
                current_mode,
                flight_mode,
            ):
                return OperationResult.ok(
                    message=(
                        f"Vehicle already in "
                        f"{flight_mode.value}"
                    ),
                    details={
                        "mode": flight_mode.value,
                        "mode_id": mode_id,
                        "command_sent": False,
                    },
                )

            command_id = (
                mavutil.mavlink.MAV_CMD_DO_SET_MODE
            )

            # ----------------------------------------------------------
            # ACK queue preparation
            #
            # FlightCommands serializes important commands with
            # _command_lock, so no other flight command should currently
            # be waiting for an ACK.
            # ----------------------------------------------------------

            self.router.clear_ack_queue()

            # ----------------------------------------------------------
            # COMMAND
            # ----------------------------------------------------------

            try:
                self.pixhawk.master.mav.command_long_send(
                    self.pixhawk.master.target_system,
                    self.pixhawk.master.target_component,
                    command_id,
                    0,

                    # param1:
                    # use ArduPilot custom mode.
                    mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,

                    # param2:
                    # ArduPilot mode number.
                    mode_id,

                    0,
                    0,
                    0,
                    0,
                    0,
                )

            except Exception as exc:
                return OperationResult.failed(
                    ResultCode.COMMAND_FAILED,
                    (
                        "Failed to send flight "
                        f"mode command: {exc}"
                    ),
                    details={
                        "mode": flight_mode.value,
                        "mode_id": mode_id,
                    },
                )

            # ----------------------------------------------------------
            # ACK
            # ----------------------------------------------------------

            ack = self.router.wait_command_ack(
                command_id=command_id,
                timeout_sec=ack_timeout_sec,
            )

            ack_error = self._check_ack(
                ack,
                command_id,
            )

            if ack_error is not None:

                ack_error.details.update(
                    {
                        "requested_mode":
                            flight_mode.value,

                        "mode_id":
                            mode_id,
                    }
                )

                return ack_error

            ack_result_name = (
                self._ack_name(
                    ack.result
                )
            )

            # ----------------------------------------------------------
            # VERIFY STATE
            # ----------------------------------------------------------

            verified = self._wait_until(
                lambda: mode_matches(
                    self.telemetry.flight_mode,
                    flight_mode,
                ),
                timeout_sec=state_timeout_sec,
            )

            if not verified:
                return OperationResult.failed(
                    ResultCode.MODE_CHANGE_FAILED,
                    (
                        "Flight mode ACK received "
                        "but requested mode was not reached"
                    ),
                    details={
                        "requested_mode":
                            flight_mode.value,

                        "actual_mode":
                            self.telemetry.flight_mode,

                        "mode_id":
                            mode_id,

                        "ack_result":
                            ack.result,

                        "ack_result_name":
                            ack_result_name,

                        "state_timeout_sec":
                            state_timeout_sec,
                    },
                )

            # ----------------------------------------------------------
            # SUCCESS
            # ----------------------------------------------------------

            return OperationResult.ok(
                message=(
                    "Flight mode changed to "
                    f"{flight_mode.value}"
                ),
                details={  "mode":                        flight_mode.value,
                    "mode_id":
                        mode_id,

                    "ack_result":
                        ack.result,

                    "ack_result_name":
                        ack_result_name,

                    "verified_mode":
                        self.telemetry.flight_mode,

                    "command_sent":
                        True,
                },
            )