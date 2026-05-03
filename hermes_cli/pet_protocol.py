"""Compatibility re-export for the update-safe Hermes Pet protocol package.

New code should import from ``hermes_pet.protocol`` directly. This shim stays
silent to preserve the project's warning-free test output.
"""

from hermes_pet.protocol import *  # noqa: F401,F403
