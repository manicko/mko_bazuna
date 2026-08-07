"""
Language preference middleware for Mko Bazuna.

Detects and sets the user language preference before Django's LocaleMiddleware
runs. Priority order: ?lang=X query parameter > lang_pref cookie >
Accept-Language header > default to ru.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils.deprecation import MiddlewareMixin

from apps.core.enums import LanguageLocale

logger = logging.getLogger(__name__)

LANGUAGE_COOKIE_NAME = "lang_pref"
LANGUAGE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


class LanguagePreMiddleware(MiddlewareMixin):
    """Detect and set user language preference before LocaleMiddleware.

    Reads the language preference from the following sources in priority
    order:
        1. ``?lang=X`` query parameter
        2. ``lang_pref`` cookie
        3. ``Accept-Language`` HTTP header
        4. Default to Russian (``ru``)

    When the ``?lang=X`` parameter is present the detected language is also
    persisted in the ``lang_pref`` cookie and, for authenticated users, in the
    session.
    """

    def process_request(self, request: Any) -> None:
        """Determine and set the language code for the current request."""
        lang = request.GET.get("lang")
        if lang is not None:
            self._apply_lang_param(request, lang)
            return

        lang = request.COOKIES.get(LANGUAGE_COOKIE_NAME)
        if lang is not None:
            self._set_language_code(request, lang)
            return

        lang = self._parse_accept_language(request)
        if lang is not None:
            self._set_language_code(request, lang)
            return

        self._set_language_code(request, LanguageLocale.RUSSIAN.value)

    def process_response(self, request: Any, response: Any) -> Any:
        """Persist the lang_pref cookie on the response if set by ?lang=.

        The cookie value is stored on the request during process_request
        and applied here where we have access to the response object.
        """
        cookie_value = getattr(request, "_lang_cookie_value", None)
        if cookie_value is not None:
            response.set_cookie(
                LANGUAGE_COOKIE_NAME,
                cookie_value,
                max_age=LANGUAGE_COOKIE_MAX_AGE,
            )
        return response

    def _apply_lang_param(self, request: Any, lang: str) -> None:
        """Apply language from the ``?lang=X`` query parameter.

        Validates the value, stores cookie intent on the request, updates
        ``request.LANGUAGE_CODE``, and persists to session for authenticated users.
        """
        if not self._is_valid_language(lang):
            logger.warning("Ignoring invalid lang parameter: %s", lang)
            self._set_language_code(request, LanguageLocale.RUSSIAN.value)
            return

        self._set_language_code(request, lang)

        # Store cookie value to be persisted in process_response.
        request._lang_cookie_value = lang

        # Persist preference in session for authenticated users.
        if (
            hasattr(request, "session")
            and hasattr(request, "user")
            and request.user.is_authenticated
        ):
            request.session["django_language"] = lang

    def _set_language_code(self, request: Any, lang: str) -> None:
        """Set ``request.LANGUAGE_CODE`` to the given language code."""
        request.LANGUAGE_CODE = lang

    def _parse_accept_language(self, request: Any) -> str | None:
        """Extract the primary language tag from the Accept-Language header.

        Returns the first language tag (e.g. ``"en"`` from ``"en-US,en;q=0.9"``)
        if it is a supported locale, otherwise ``None``.
        """
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
        if not accept_language:
            return None
        lang = accept_language.split(",")[0].split("-")[0]
        if self._is_valid_language(lang):
            return lang
        return None

    @staticmethod
    def _is_valid_language(lang: str) -> bool:
        """Return ``True`` if *lang* is a supported ``LanguageLocale`` value."""
        return lang in LanguageLocale.values()