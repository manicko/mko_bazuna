"""Bootstrap settings for one-shot services.

This module exists for the dev bootstrap one-shot services — migrate,
load_cities, load_catalog, create_admin and seed — which serve no HTTP traffic
and do not need real secrets. It must never serve requests.

It inherits from ``prod`` on purpose, and the arrow is a deliberate dependency
inversion: bootstrap is *weaker* than production, yet this module star-imports
the stronger module. The benefit is that every setting added to ``prod.py``
(every guard, prod's structured LOGGING, the Sentry init, the transport pins,
the static-files ``STORAGES`` backend (owned by ``base.py``) and
``ALLOWED_HOSTS``) is picked up here automatically instead of silently going
stale in a copied block. Do not replace the star-import with a copy of prod's
configuration.

The ``DJANGO_ONESHOT`` bypass reaches this module only because the deployment
descriptor (Compose ``environment:``) resolves
``DJANGO_SETTINGS_MODULE=config.settings.oneshot`` for these services. It can
never be selected by a ``.env`` file: ``read_env(overwrite=False)`` cannot move
an already-set process onto this module, and ``prod.py`` ignores
``DJANGO_ONESHOT`` for any ``*.prod`` settings module.

Name-mangling caveat: base.py's missing-``.env`` hint classifies a process by a
``.prod`` module-name suffix, so a missing ``.env`` here prints the ``.env.dev``
hint. That is correct for this module's only shipped use (a dev one-shot); a
production one-shot pointed at this dev-only module would print the wrong hint,
but that is a misconfiguration, is error text only, and exits 1 either way.

Residual risk: ``DJANGO_BUILD=1`` written into ``.env.prod`` would still bypass
every guard. The Docker image builder stage genuinely needs it and cannot be
distinguished by a settings module, and ``Makefile``'s ``restore-test`` target
is the same channel. The mitigation is the commented ``ALLOWED_ENV_VARS``
sub-group plus the ``.env.prod.example`` absence assertion — not a code change.
"""

from .prod import *  # noqa: F403, F401

# Re-pinned: base.py reads DEBUG from the .env file, which is not present
# in every bootstrap invocation. A bootstrap process must never run with
# DEBUG enabled.
DEBUG = False
