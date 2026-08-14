# sdfm/health/system_check.py

from __future__ import annotations

import socket

from sdfm.flight.mavlink_router import MavlinkRouter
from sdfm.flight.pixhawk import PixhawkConnection
from sdfm.flight.telemetry import TelemetryState

from sdfm.health.checks import (
    check_battery,
    check_compass,
    check_elrs,
    check_gps,
    check_heartbeat,
    check_imu,
    check_pi5,
    check_realsense,
    unknown_check,
    check_prearm,
)
from sdfm.health.report import (
    HealthResult,
    HealthStatus,
    SystemCheckReport,
)


VEHICLE_NAME = "DR01"


CRITICAL_CHECKS = {
    "Pi5",
    "Pixhawk",
    "Heartbeat",
    "Battery",
    "GPS",
    "IMU",
    "Compass",
    "ELRS",
    "PreArm",
}


def is_ready(
    report: SystemCheckReport,
) -> bool:
    """
    Temporary development readiness policy.

    This is NOT final flight readiness.
    """

    for check in report.checks:

        if check.name not in CRITICAL_CHECKS:
            continue

        if check.status != HealthStatus.OK:
            return False

    return True


def check_pixhawk_connection(
    pixhawk: PixhawkConnection,
) -> HealthResult:

    try:
        pixhawk.connect()

        return HealthResult(
            name="Pixhawk",
            status=HealthStatus.OK,
            message="MAVLink connection established",
            details={
                "device": pixhawk.device,
                "system_id": pixhawk.system_id,
                "component_id": pixhawk.component_id,
            },
        )

    except Exception as exc:

        return HealthResult(
            name="Pixhawk",
            status=HealthStatus.FAILED,
            message=f"PIXHAWK_CONNECTION_FAILED: {exc}",
        )


def run_system_check() -> SystemCheckReport:

    report = SystemCheckReport(
        vehicle=VEHICLE_NAME,
        host=socket.gethostname(),
    )

    # ----------------------------------------------------------
    # Pi5
    # ----------------------------------------------------------

    report.add(
        check_pi5()
    )

    # ----------------------------------------------------------
    # RealSense
    #
    # Directly connected to Pi5.
    # Does not depend on Pixhawk.
    # ----------------------------------------------------------

    report.add(
        check_realsense()
    )

    # ----------------------------------------------------------
    # Pixhawk stack
    # ----------------------------------------------------------

    pixhawk = PixhawkConnection()

    pixhawk_result = check_pixhawk_connection(
        pixhawk
    )

    report.add(
        pixhawk_result
    )

    if pixhawk_result.status != HealthStatus.OK:

        report.add(
            unknown_check(
                "Heartbeat",
                "PIXHAWK_UNAVAILABLE",
            )
        )

        report.add(
            unknown_check(
                "Battery",
                "PIXHAWK_UNAVAILABLE",
            )
        )

        report.add(
            unknown_check(
                "GPS",
                "PIXHAWK_UNAVAILABLE",
            )
        )

        report.add(
            unknown_check(
                "IMU",
                "PIXHAWK_UNAVAILABLE",
            )
        )

        report.add(
            unknown_check(
                "Compass",
                "PIXHAWK_UNAVAILABLE",
            )
        )

        report.add(
            unknown_check(
                "ELRS",
                "PIXHAWK_UNAVAILABLE",
            )
        )

        return _finish_report(
            report
        )

    telemetry = TelemetryState()

    router = MavlinkRouter(
        pixhawk=pixhawk,
        telemetry=telemetry,
    )

    try:

        router.start()

        # ------------------------------------------------------
        # Important:
        #
        # Legacy checks below still expect pymavlink master.
        #
        # We keep these temporarily until telemetry-based
        # versions are implemented.
        # ------------------------------------------------------

        master = pixhawk.master

        report.add(
            check_heartbeat(master)
        )

        report.add(
            check_battery(master)
        )

        report.add(
            check_gps(master)
        )

        # ------------------------------------------------------
        # New production checks using PixhawkConnection +
        # MavlinkRouter.
        # ------------------------------------------------------

        report.add(
            check_imu(
                pixhawk,
                router,
            )
        )

        report.add(
            check_compass(
                pixhawk,
                router,
            )
        )

        report.add(
            check_elrs(
                pixhawk,
                router,
            )
        )

        report.add(
            check_prearm(
                pixhawk,
                router,
            )
        )

    finally:

        try:
            router.stop()
        except Exception:
            pass

        try:
            pixhawk.close()
        except Exception:
            pass

    return _finish_report(
        report
    )


def _finish_report(
    report: SystemCheckReport,
) -> SystemCheckReport:

    # ----------------------------------------------------------
    # Hardware not connected / not implemented yet
    # ----------------------------------------------------------

    report.add(
        unknown_check(
            "Optical Flow",
            "SENSOR_NOT_CONNECTED",
        )
    )

    report.add(
        unknown_check(
            "LiDAR Front",
            "SENSOR_NOT_CONNECTED",
        )
    )

    report.add(
        unknown_check(
            "LiDAR Up",
            "SENSOR_NOT_CONNECTED",
        )
    )

    report.add(
        unknown_check(
            "SiK",
        )
    )

    report.add(
        unknown_check(
            "Pi Camera",
            "SENSOR_NOT_CONNECTED",
        )
    )

    report.add(
        unknown_check(
            "Pi Camera",
            "SENSOR_NOT_CONNECTED",
        )
    )

    return report


def print_report(
    report: SystemCheckReport,
) -> None:

    print()
    print("=" * 60)
    print(" SDFM SYSTEM CHECK")
    print("=" * 60)

    print(
        f" Vehicle : {report.vehicle}"
    )

    print(
        f" Host    : {report.host}"
    )

    print("-" * 60)

    for check in report.checks:

        print(
            f" {check.name:<16}"
            f"{check.status.value:<12}"
            f"{check.message}"
        )

        if check.details:

            for key, value in check.details.items():

                print(
                    f"     {key:<18}: {value}"
                )

    print("-" * 60)

    if is_ready(report):

        print(
            " SYSTEM STATUS : READY"
        )

    else:

        print(
            " SYSTEM STATUS : NOT READY"
        )

    print("=" * 60)
    print()


def main() -> int:

    report = run_system_check()

    print_report(
        report
    )

    if is_ready(report):
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )