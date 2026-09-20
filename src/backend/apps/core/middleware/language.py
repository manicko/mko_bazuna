"""
Language preference middleware for Mko Bazuna.

The single authority for the active language. Resolves the user language per
priority ``?lang=X`` > ``lang_pref`` cookie > ``Accept-Language`` > ``settings.LANGUAGE_CODE``,
activates the Django translation for the request thread, and keeps
``request.LANGUAGE_CODE`` in sync with the thread-local active language.

Django's ``LocaleMiddleware`` is intentionally NOT used (see
``config/settings/base.py``): it is dormant in this project (no
``i18n_patterns``, no ``set_language`` view, no compiled ``.mo`` files) and its
``process_request`` would re-derive the language from the default ``django_language``
cookie (which is never set here) plus ``Accept-Language``, clobbering the value
resolved above and ignoring both ``?lang=`` and the ``lang_pref`` cookie.

This middleware also replaces ``LocaleMiddleware``'s response contract:
``Vary: Accept-Language`` and ``Content-Language`` headers, keeping the
behaviour forward-compatible with any future reverse proxy / page cache.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin

from apps.core.enums import LanguageLocale

logger = logging.getLogger(__name__)

LANGUAGE_COOKIE_NAME = "lang_pref"
LANGUAGE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # 1 year


class LanguagePreMiddleware(MiddlewareMixin):
    """Detect, activate and persist the user's language preference.

    This middleware is the single authority for the active language: Django's
    ``LocaleMiddleware`` is intentionally removed from the stack (it is dormant
    here and would clobber the resolved language — see the module docstring).

    Reads the language preference from the following sources in priority
    order:
        1. ``?lang=X`` query parameter
        2. ``lang_pref`` cookie
        3. ``Accept-Language`` HTTP header
        4. Default to ``settings.LANGUAGE_CODE`` (Russian in production,
           English in tests)

    When the ``?lang=X`` parameter is present the detected language is also
    persisted in the ``lang_pref`` cookie and, for authenticated users, in the
    session.
    """

    def process_request(self, request: HttpRequest) -> None:
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

        self._set_language_code(request, settings.LANGUAGE_CODE)

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Persist the ``lang_pref`` cookie and emit language response headers.

        The cookie value is stored on the request during ``process_request``
        and applied here where we have access to the response object. The
        ``Vary``/``Content-Language`` headers replicate the contract that
        Django's ``LocaleMiddleware.process_response`` provided, so the
        behaviour is preserved for any future reverse proxy / page cache.
        """
        cookie_value = getattr(request, "_lang_cookie_value", None)
        if cookie_value is not None:
            response.set_cookie(
                LANGUAGE_COOKIE_NAME,
                cookie_value,
                max_age=LANGUAGE_COOKIE_MAX_AGE,
            )
        patch_vary_headers(response, ("Accept-Language",))
        response.headers.setdefault("Content-Language", translation.get_language())
        return response

    def _apply_lang_param(self, request: HttpRequest, lang: str) -> None:
        """Apply language from the ``?lang=X`` query parameter.

        Normalizes language variants (e.g. ``en-US`` → ``en``) via
        ``LanguageLocale.from_code`` and falls back to BOSNIAN for unsupported
        codes, per spec (i18n-spec.md:63-64). The preference is persisted in
        the cookie and session only when the code is explicitly supported —
        a fallback resolution does not write ``lang_pref``.
        """
        if not lang:
            self._set_language_code(request, settings.LANGUAGE_CODE)
            return

        resolved = LanguageLocale.from_code(
            lang, fallback=LanguageLocale.BOSNIAN
        )
        resolved_code = resolved.value
        self._set_language_code(request, resolved_code)

        # Persist preference only for explicitly supported codes (including
        # normalized variants like en-US → en). Unsupported fallback does not
        # persist — the user did not explicitly request the fallback language.
        base = lang.split("-")[0].lower()
        if base in LanguageLocale.values():
            request._lang_cookie_value = resolved_code
            if (
                hasattr(request, "session")
                and hasattr(request, "user")
                and request.user.is_authenticated
            ):
                request.session["django_language"] = resolved_code
        else:
            logger.warning("Ignoring invalid lang parameter: %s", lang)


    def _set_language_code(self, request: HttpRequest, lang: str) -> None:
        """Activate the language for the current thread and sync the request.

        ``translation.activate(lang)`` sets the thread-local active language
        (read by ``{% get_current_language %}`` and Django's ``i18n`` context
        processor), and ``request.LANGUAGE_CODE`` is set to the resulting
        ``translation.get_language()`` so the two are always in agreement.
        """
        translation.activate(lang)
        request.LANGUAGE_CODE = translation.get_language()

    def _parse_accept_language(self, request: HttpRequest) -> str | None:
        """Extract the primary language tag from the Accept-Language header.

        Returns the resolved language code (normalized via
        ``LanguageLocale.from_code``) if a supported locale is found,
        falling back to BOSNIAN for unsupported codes. Returns ``None``
        only when no Accept-Language header is present, so that
        ``process_request`` falls back to ``settings.LANGUAGE_CODE``.
        """
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
        if not accept_language:
            return None
        first_tag = accept_language.split(",")[0]
        resolved = LanguageLocale.from_code(
            first_tag, fallback=LanguageLocale.BOSNIAN
        )
        return resolved.value
