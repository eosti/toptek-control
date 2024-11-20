"""Datastructures and control code for the Toptek controller"""

import logging
import os
import sys
import time
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

import serial

logger = logging.getLogger(__name__)


class ToptekException(Exception):
    """General K3NG exception class"""


class ToptekValueException(Exception):
    """Exception to catch value validation exceptions"""


class ToptekSwitches(IntEnum):
    """Enum for the Toptek button indices"""

    SSB_ON = 1
    TX_PA = 2
    SET_PWR = 3
    RX_LNA = 4
    SHOW_SWR = 5
    DA_EN = 6


@dataclass
class ToptekState:
    """Class to store and translate the state of the LEDs"""

    # pylint: disable=too-many-instance-attributes
    led_10: bool
    led_20: bool
    led_30: bool
    led_40: bool
    led_50: bool
    led_60: bool
    led_70: bool
    led_80: bool
    red_en: bool
    lna_on: bool
    tx_pa: bool
    ssb_on: bool
    da_swr: bool

    def get_power(self) -> int:
        """Parses LED state and returns the power level"""
        # pylint: disable=too-many-return-statements

        if self.red_en:
            raise ToptekException("Red LEDs are on, unable to get power")

        if self.led_80:
            return 80
        if self.led_70:
            return 70
        if self.led_60:
            return 60
        if self.led_50:
            return 50
        if self.led_40:
            return 40
        if self.led_30:
            return 30
        if self.led_20:
            return 20
        if self.led_10:
            return 10
        return 0

    def get_swr(self) -> float:
        """Parses LED state and returns the SWR level"""
        # pylint: disable=too-many-return-statements

        if self.led_80:
            return 1.9
        if self.led_70:
            return 1.8
        if self.led_60:
            return 1.7
        if self.led_50:
            return 1.6
        if self.led_40:
            return 1.5
        if self.led_30:
            return 1.4
        if self.led_20:
            return 1.3
        if self.led_10:
            return 1.2
        return 1

    def get_errors(self) -> list[str]:
        """Parses LED state and returns any errors"""
        if not self.red_en:
            raise ToptekException("No error apparent!")

        errors = []

        # In red LED mode, values are inverted
        if not self.led_10:
            errors.append("PA FAIL")
        if not self.led_20:
            errors.append("HIGH TEMP")
        if not self.led_30:
            errors.append("DC VOLTAGE")
        if not self.led_40:
            errors.append("OVERDRIVE")
        if not self.led_50:
            errors.append("HIGH SWR")

        return errors

    def any_on(self) -> bool:
        """Helper to check if any of the LEDs are on"""
        return (
            self.led_80
            or self.led_70
            or self.led_60
            or self.led_50
            or self.led_40
            or self.led_30
            or self.led_20
            or self.led_10
        )


@dataclass
class ToptekSwitchState:
    """Class to store the state of the switches"""

    sw_ssb_on: bool
    sw_tx_pa: bool
    sw_set_pwr: bool
    sw_rx_lna: bool
    sw_show_swr: bool
    sw_da_on: bool


class Toptek:
    """Main class for controlling the Toptek controller"""

    # pylint: disable=too-many-public-methods

    FLASHY_POLL_DELAY = 0.05  # Time between checking state
    FLASHY_TOTAL_DELAY = 2  # Time until PA's bargraph mode turns off

    def __init__(self, port: str) -> None:
        # Ensure we have r/w
        self.port = Path(port)
        if not self.port.exists():
            raise FileNotFoundError(self.port)

        if not os.access(self.port, os.R_OK | os.W_OK):
            logger.critical(
                "Unable to acquire read/write permissions on %s.\n"
                + "Please change permissions, or run this script as superuser.",
                self.port,
            )
            sys.exit(1)

        self.ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(1)
        if self.readline() != "Toptek Switch Interface":
            raise ToptekException("Invalid welcome message")

    def write(self, cmd: str) -> None:
        """Write a command over Serial"""
        logger.debug("TX: %s", cmd)
        self.ser.write(cmd.encode("ascii"))
        time.sleep(0.05)
        ret = self.readline()
        if ret != f"{cmd}":
            raise ToptekException(f"Invalid response from Toptek: {ret}")

    def readline(self) -> str:
        """Read one line from Serial"""
        line = self.ser.readline()
        line_decoded = line.decode("utf-8").strip()
        logger.debug("RX: %s", line_decoded)
        return line_decoded

    def query(self, cmd: str) -> str:
        """Send command and get response"""
        self.write(cmd)
        return self.readline()

    def switch_on(self, switch: ToptekSwitches) -> None:
        """Depress a button"""
        self.write(f"S{int(switch)}")

    def switch_off(self, switch: ToptekSwitches) -> None:
        """Release a button"""
        self.write(f"U{int(switch)}")

    def press_manual(self, switch: ToptekSwitches, delay: float = 0.2):
        """Manually press a button with a defined press length

        Note: due to the Arduino being slow, the button may become un-pressed during the on time
            for one keyboard scan cycle, making it seem like the button was pressed twice.

        To avoid, use press()
        """
        self.switch_on(switch)
        time.sleep(delay)
        self.switch_off(switch)

    def press(self, switch: ToptekSwitches):
        """Automatically press a button with a one cycle press time"""
        self.write(f"P{int(switch)}")
        # So that the PA can process the button press
        time.sleep(0.1)

    def get_switch(self, switch: ToptekSwitches) -> bool:
        """Get current state of a single button"""
        return bool(self.query(f"R{int(switch)}"))

    def enable(self) -> None:
        """Enable remote key presses (enabled by default)
        When enabled, the facepanel buttons cannot be used.
        """
        ret = self.query("EN")
        if ret != "Remote keys enabled":
            raise ToptekException("Failed to enable remote keys")
        logger.info("Enabled remote control of PA")

    def disable(self) -> None:
        """Disable remote key presses, allowing the facepanel buttons to be used manually"""
        ret = self.query("DS")
        if ret != "Remote keys disabled":
            raise ToptekException("Failed to disable remote keys")
        logger.info("Disabled remote control of PA")

    def get_state(self) -> ToptekState:
        """Read the current state of the LEDs"""
        da_state = int(self.query("RS"))
        toptek_state = int(self.query("RA"), 16)

        return ToptekState(
            bool(toptek_state & 0b0000000000000001),
            bool(toptek_state & 0b0000000000000010),
            bool(toptek_state & 0b0000000000000100),
            bool(toptek_state & 0b0000000000001000),
            bool(toptek_state & 0b0000000000010000),
            bool(toptek_state & 0b0000000000100000),
            bool(toptek_state & 0b0000000001000000),
            bool(toptek_state & 0b0000000010000000),
            bool(toptek_state & 0b0000000100000000),
            bool(toptek_state & 0b0000001000000000),
            bool(toptek_state & 0b0000010000000000),
            bool(toptek_state & 0b0000100000000000),
            bool(da_state),
        )

    def get_switch_state(self) -> ToptekSwitchState:
        """Read the current state of all buttons"""
        da_sw = int(self.query("R6"))
        toptek_sw = int(self.query("RS"), 16)
        return ToptekSwitchState(
            bool(toptek_sw & 0b00010000),
            bool(toptek_sw & 0b00100000),
            bool(toptek_sw & 0b00000100),
            bool(toptek_sw & 0b00001000),
            bool(toptek_sw & 0b00000001),
            bool(da_sw),
        )

    def info(self) -> str:
        """Returns a verbose string with basic state information"""
        state = self.get_state()
        sw_state = self.get_switch_state()
        outstr = "Toptek State: "

        if state.tx_pa:
            outstr += "PA is ENABLED"
        else:
            outstr += "PA is DISABLED"

        if state.lna_on:
            outstr += ", LNA is ENABLED"
        else:
            outstr += ", LNA is DISABLED"

        if state.ssb_on:
            outstr += ", SSB is ENABLED"
        else:
            outstr += ", SSB is DISABLED"

        if sw_state.sw_da_on:
            outstr += ", DA is ON"
        else:
            outstr += ", DA is OFF"

        if state.da_swr:
            outstr += ", DA is showing HIGH SWR"

        if sw_state.sw_show_swr:
            outstr += ", SHOW SWR mode is ENABLED (not implemented)"
            return outstr

        if state.red_en:
            outstr += f", ERRORS: {self.get_errors()}"
            return outstr

        outstr += f", output power set at {self.get_tx_power()}W"

        outstr += f", current power: {state.get_power()}"

        return outstr

    def get_flashy_bargraph(self) -> ToptekState:
        """Helper for reading the LED bargraph while it's flashing
        Polls the LED state until a valid state is found, and then waits until the
            LEDs (should) stop blinking
        """
        state: ToptekState
        for i in range(int(self.FLASHY_TOTAL_DELAY / self.FLASHY_POLL_DELAY)):
            time.sleep(self.FLASHY_POLL_DELAY)
            state = self.get_state()
            if state.any_on() != 0:
                time.sleep(self.FLASHY_TOTAL_DELAY - i * self.FLASHY_POLL_DELAY)
                break

        return state

    #  ╭──────────────────────────────────────────────────────────╮
    #  │                      POWER HELPERS                       │
    #  ╰──────────────────────────────────────────────────────────╯

    def get_errors(self) -> list[str]:
        """Get all errors"""
        state = self.get_state()
        if state.red_en is False:
            return [""]

        return self.get_flashy_bargraph().get_errors()

    def get_tx_power(self) -> int:
        """Get the power that the PA is set to"""
        state = self.get_state()
        if not state.tx_pa:
            # Can't get the tx power when PA off
            return 0

        self.press(ToptekSwitches.SET_PWR)
        return self.get_flashy_bargraph().get_power()

    def set_tx_power(self, power: int) -> None:
        """Set the PA's power setting"""
        if power not in [20, 40, 60, 80]:
            raise ToptekValueException(
                f"Invalid set power (got {power}, needs to be 20, 40, 60, or 80)"
            )

        state = self.get_state()
        if not state.tx_pa:
            raise ToptekException("Cannot set power when PA off!")

        set_power = self.get_tx_power()
        if set_power < power:
            num_presses = int(abs(set_power - power) / 20)
        else:
            num_presses = int((80 - set_power) / 20) + int(power / 20)

        if num_presses == 0:
            return

        self.press(ToptekSwitches.SET_PWR)
        time.sleep(0.1)

        for _ in range(num_presses):
            time.sleep(0.2)
            self.press(ToptekSwitches.SET_PWR)

        # Timeout so we don't accidentally increment the power
        time.sleep(2)
        actual_set = self.get_tx_power()
        if actual_set != power:
            raise ToptekException(
                f"Power not set correctly (got {actual_set}, wanted {power})"
            )

    def get_cur_power(self) -> int:
        """Get the power that the PA is currently outputting"""
        state = self.get_state()
        if not state.tx_pa:
            raise ToptekException("Amplifier is not on!")
        if state.red_en:
            raise ToptekException("Amplifier in error or in check SWR mode")
        logger.info("Current power is %sW", state.get_power())
        return state.get_power()

    #  ╭──────────────────────────────────────────────────────────╮
    #  │                      SWITCH HELPERS                      │
    #  ╰──────────────────────────────────────────────────────────╯

    def pa_on(self, pa_delay=0.5) -> None:
        """Turns the PA on"""
        state = self.get_state()
        if not state.tx_pa:
            logger.info("Turning PA on")
            self.press(ToptekSwitches.TX_PA)
            # sometimes the PA needs some extra time
            time.sleep(pa_delay)

            state = self.get_state()
            if not state.tx_pa:
                raise ToptekException("PA not turned on")
        else:
            logger.info("PA already on")

    def pa_off(self) -> None:
        """Turns the PA off"""
        state = self.get_state()
        if state.tx_pa:
            logger.info("Turning PA off")
            self.press(ToptekSwitches.TX_PA)

            state = self.get_state()
            if state.tx_pa:
                raise ToptekException("PA not turned off")
        else:
            logger.info("PA already off")

    def lna_on(self, lna_delay=0.5) -> None:
        """Turns the LNA on"""
        state = self.get_state()
        if not state.lna_on:
            logger.info("Turning LNA on")
            self.press(ToptekSwitches.RX_LNA)
            # sometimes the LNA needs some extra time
            time.sleep(lna_delay)

            state = self.get_state()
            if not state.lna_on:
                raise ToptekException("LNA not turned on")
        else:
            logger.info("LNA already on")

    def lna_off(self) -> None:
        """Turns the LNA off"""
        state = self.get_state()
        if state.lna_on:
            logger.info("Turning LNA off")
            self.press(ToptekSwitches.RX_LNA)

            state = self.get_state()
            if state.lna_on:
                raise ToptekException("LNA not turned off")
        else:
            logger.info("LNA already off")

    def ssb_on(self, ssb_delay=0.5) -> None:
        """Turns SSB mode on. Only can be set when the PA is on"""
        state = self.get_state()
        if not state.tx_pa:
            logger.warning("Cannot turn on SSB when PA not on")
            return

        if not state.ssb_on:
            logger.info("Turning SSB on")
            self.press(ToptekSwitches.SSB_ON)
            # sometimes the SSB needs some extra time
            time.sleep(ssb_delay)

            state = self.get_state()
            if not state.ssb_on:
                raise ToptekException("SSB not turned on")

        else:
            logger.info("SSB already on")

    def ssb_off(self) -> None:
        """Turns the SSB mode off. Can only be unset when the PA is off"""
        state = self.get_state()
        if not state.tx_pa:
            logger.warning("Cannot turn off SSB when PA not on")
            return

        if state.ssb_on:
            logger.info("Turning SSB off")
            self.press(ToptekSwitches.SSB_ON)

            state = self.get_state()
            if state.ssb_on:
                raise ToptekException("SSB not turned off")
        else:
            logger.info("SSB already off")

    def da_on(self) -> None:
        """Turns the DA on"""
        state = self.get_switch_state()
        if not state.sw_da_on:
            logger.info("Turning DA on")
            self.switch_on(ToptekSwitches.DA_EN)

            state = self.get_switch_state()
            if not state.sw_da_on:
                raise ToptekException("DA not turned on")
        else:
            logger.info("DA already on")

    def da_off(self) -> None:
        """Turns the DA off"""
        state = self.get_switch_state()
        if state.sw_da_on:
            logger.info("Turning DA off")
            self.switch_off(ToptekSwitches.DA_EN)

            state = self.get_switch_state()
            if state.sw_da_on:
                raise ToptekException("DA not turned off")
        else:
            logger.info("DA already off")

    def da_on_fast(self) -> None:
        """Turns the DA on quickly, without state checks"""
        self.switch_on(ToptekSwitches.DA_EN)

    def da_off_fast(self) -> None:
        """Turns the DA off quickly, without state checks"""
        self.switch_off(ToptekSwitches.DA_EN)
