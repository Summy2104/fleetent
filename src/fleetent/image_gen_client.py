"""Re-export shim: image-gen client moved to fleetent.tools.image_gen_client
(restructure-tools-package). No logic here — remove once all imports migrate.
"""

from fleetent.tools.image_gen_client import *  # noqa: F401,F403
from fleetent.tools.image_gen_client import ImageGenError, generate  # noqa: F401
