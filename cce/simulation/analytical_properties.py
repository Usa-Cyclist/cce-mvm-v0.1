#!/usr/bin/env python3
"""Closed-form properties of the CCE-MVM v0.1 synthetic equations.

These functions describe the equations implemented by the CCE reference
simulation.  They do not estimate human behaviour and are not clinical or
legal decision tools.
"""

from __future__ import annotations


def _validate_learning_rate(learning_rate: float) -> None:
    if not 0.0 <= learning_rate <= 1.0:
        raise ValueError("learning_rate must be in [0, 1]")


def _validate_steps(steps: int) -> None:
    if steps < 0:
        raise ValueError("steps must be non-negative")


def ema_closed_form(
    *,
    initial_model: float,
    constant_observation: float,
    learning_rate: float,
    steps: int,
) -> float:
    """Return M_n for M_(t+1)=(1-lambda)M_t+lambda*O and constant O."""

    _validate_learning_rate(learning_rate)
    _validate_steps(steps)
    retention = (1.0 - learning_rate) ** steps
    return constant_observation + retention * (
        initial_model - constant_observation
    )


def permanent_change_error(
    *,
    initial_model: float,
    new_reference: float,
    learning_rate: float,
    steps: int,
) -> float:
    """Absolute lag after a permanent noiseless change in the reference."""

    model = ema_closed_form(
        initial_model=initial_model,
        constant_observation=new_reference,
        learning_rate=learning_rate,
        steps=steps,
    )
    return abs(model - new_reference)


def temporary_shock_peak(
    *,
    stable_reference: float,
    shock_observation: float,
    learning_rate: float,
    shock_steps: int,
) -> float:
    """Model value after L shock observations, starting at the reference."""

    return ema_closed_form(
        initial_model=stable_reference,
        constant_observation=shock_observation,
        learning_rate=learning_rate,
        steps=shock_steps,
    )


def post_shock_model(
    *,
    stable_reference: float,
    shock_observation: float,
    learning_rate: float,
    shock_steps: int,
    recovery_steps: int,
) -> float:
    """Model value after a temporary shock and a noiseless recovery period."""

    peak = temporary_shock_peak(
        stable_reference=stable_reference,
        shock_observation=shock_observation,
        learning_rate=learning_rate,
        shock_steps=shock_steps,
    )
    return ema_closed_form(
        initial_model=peak,
        constant_observation=stable_reference,
        learning_rate=learning_rate,
        steps=recovery_steps,
    )


def synthetic_response_effect(
    *, baseline: float, proposal: float, coupling: float
) -> float:
    """Normalized response shift implied by Y=(1-a)B+aQ before clipping."""

    if not 0.0 <= coupling <= 1.0:
        raise ValueError("coupling must be in [0, 1]")
    if not -1.0 <= baseline <= 1.0 or not -1.0 <= proposal <= 1.0:
        raise ValueError("baseline and proposal must be in [-1, 1]")
    return coupling * abs(proposal - baseline) / 2.0

