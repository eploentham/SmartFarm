# sdfm/health/system_check.py

from __future__ import annotations

import socket

from sdfm.health.checks import (
    check_battery,
    check_gps,
    check_heartbeat,
    check_pi5,
    connect_pixhawk,
    unknown_check,
)
from sdfm.health.report import HealthStatus, SystemCheckReport


VEHICLE_NAME = "DR01"


CRITICAL_CHECKS = {
    "Pi5",
    "Pixhawk",
    "Heartbeat",
    "Battery",
    "GPS",
}


def is_ready(report: SystemCheckReport) -> bool:
    """
    Temporary readiness policy for early SDFM development.

    Only checks currently implemented and verified are considered critical.

    This will later move to safety/policy.py and become mission-state aware.
    """

    for check in report.checks:
        if check.name not in CRITICAL_CHECKS:
            continue

        if check.status != HealthStatus.OK:
            return False

    return True


def run_system_check() -> SystemCheckReport:
    """
    Run SDFM system health checks.

    Read-only:
    - no ARM
    - no flight mode change
    - no TAKEOFF
    - no movement command
    """

    report = SystemCheckReport(
        vehicle=VEHICLE_NAME,
        host=socket.gethostname(),
    )

    # ----------------------------------------------------------
    # Raspberry Pi 5
    # ----------------------------------------------------------

    report.add(check_pi5())

    # ----------------------------------------------------------
    # Pixhawk + MAVLink
    # ----------------------------------------------------------

    master, pixhawk_result = connect_pixhawk()

    report.add(pixhawk_result)

    if master is None:
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

    else:
        try:
            report.add(
                check_heartbeat(master)
            )

            report.add(
                check_battery(master)
            )

            report.add(
                check_gps(master)
            )

        finally:
            try:
                master.close()
            except Exception:
                pass

    # ----------------------------------------------------------
    # Checks not implemented yet
    # ----------------------------------------------------------

    report.add(
        unknown_check("IMU")
    )

    report.add(
        unknown_check("Compass")
    )

    report.add(
        unknown_check("Optical Flow")
    )

    report.add(
        unknown_check("LiDAR Front")
    )

    report.add(
        unknown_check("LiDAR Up")
    )

    report.add(
        unknown_check("ELRS")
    )

    report.add(
        unknown_check("SiK")
    )

    report.add(
        unknown_check("RealSense")
    )

    report.add(
        unknown_check("Pi Camera")
    )

    report.add(
        unknown_check("PreArm")
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

    print_report(report)

    if is_ready(report):
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )