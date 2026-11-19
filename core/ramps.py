"""Construction and validation of the bias-voltage arrays."""

import numpy as np

from core.config import HVPSConfig, MAX_VOLTAGE


class ConfigError(ValueError):
    """Raised when the user-provided settings are invalid."""


def load_voltages_from_file(path):
    """Load a single-column .txt file of voltage values (absolute value is taken)."""
    values = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            values.append(abs(float(line)))
    if not values:
        raise ConfigError(f"Ramp file '{path}' contains no voltage values")
    return values


def build_voltages(cfg: HVPSConfig):
    """Return the list of voltage magnitudes (positive) for the configured ramp."""
    if cfg.ramp_type == "linear":
        _check_linlog(cfg)
        if cfg.v_end < cfg.v_start:
            raise ConfigError("Voltage end must be >= voltage start")
        voltages = list(np.linspace(cfg.v_start, cfg.v_end, cfg.n_steps))

    elif cfg.ramp_type == "logarithmic":
        _check_linlog(cfg)
        if cfg.v_start <= 0 or cfg.v_end <= 0:
            raise ConfigError("Logarithmic ramp requires positive start and end voltages")
        voltages = list(np.logspace(np.log10(cfg.v_start), np.log10(cfg.v_end), cfg.n_steps))

    elif cfg.ramp_type == "file":
        if not cfg.ramp_file:
            raise ConfigError("No ramp file selected")
        voltages = load_voltages_from_file(cfg.ramp_file)

    else:
        raise ConfigError(f"Unknown ramp type '{cfg.ramp_type}'")

    if not voltages:
        raise ConfigError("Voltage list is empty")

    for v in voltages:
        if v > MAX_VOLTAGE + 1e-9:
            raise ConfigError(f"Voltage {v:g} V exceeds the {MAX_VOLTAGE:g} V range of the HVPS")
    return voltages


def _check_linlog(cfg: HVPSConfig):
    if cfg.n_steps < 2:
        raise ConfigError("Number of steps must be at least 2")
    if cfg.ramp_rate <= 0:
        raise ConfigError("Ramping speed must be positive")
    if cfg.wait_time < 0:
        raise ConfigError("Wait time cannot be negative")
    if cfg.compliance <= 0:
        raise ConfigError("Current compliance must be positive")
