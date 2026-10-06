"""
Language preference middleware for Mko Bazuna.

The single authority for the active language. All three locale sources resolve
through ONE normalising sink: the ``?lang=X`` query parameter, the ``lang_pref``
cookie and the ``Accept-Language`` header each yield a ``LanguageLocale`` member,
and that member is what reaches ``translation.activate()`` and
``request.LANGUAGE_CODE``. There is no fourth path, and no branch passes a raw
``str`` to the sink.

Priority chain: ``?lang=X`` > ``lang_pref`` cookie > ``Accept-Language`` >
``settings.LANGUAGE_CODE``.

Normalisation guarantee: every source is normalised through
``LanguageLocale.from_code`` before activation, so non-canonical BCP-47 tags
(``en-US``, ``ru-RU``, ``de-DE``) resolve to a supported locale instead of
driving the site to the fallback. ``request.LANGUAGE_CODE`` is therefore always
a member of ``settings.LANGUAGES``, for every input, hostile ones included.

The ``Accept-Language`` header honours descending q-values via Django's
``parse_accept_lang_header`` and explicitly drops any member with ``q == 0``.

Django's ``LocaleMiddleware`` is intentionally NOT used (see
``config/settings/base.py``): it is dormant in this project (no
``i18n_patterns``, no ``set_language`` view, no compiled ``.mo`` files) and its
``process_request`` would re-derive the language from the default ``django_language``
cookie (which is never set here) plus ``Accept-Language``, clobbering the value
resolved above and ignoring both ``?lang=`` and the ``lang_pref`` cookie.

This middleware also replaces part of ``LocaleMiddleware``'s response contract:
it emits ``Vary: Accept-Language`` and ``Content-Language``. Those two headers
are this middleware's ONLY contribution to the ``Vary`` contract, and they do
not cover cookie-driven locale: a response whose language was resolved from the
``lang_pref`` cookie still advertises only ``Accept-Language``.

Cookie-driven locale is in fact already covered in the real stack, but
INCIDENTALLY, not by anything declared here: ``CsrfViewMiddleware`` adds
``Vary: Cookie`` on any response whose template called ``get_token()``, and the
full page templates do render ``{% csrf_token %}``. So a ``Vary``-honouring
cache already keys on the cookie today even though this middleware never says
so. The property is fragile: the two token-free HTMX fragments
(``ads/partials/ad_list.html`` and ``categories/partials/mega_submenu.html``)
render no CSRF token, so a fragment can lose ``Vary: Cookie`` without notice.
When a shared cache is introduced this must be made DELIBERATE rather than
inherited from a CSRF side effect — either by adding ``Vary: Cookie`` to the
cache contract explicitly or by ensuring every cached fragment is token-bearing
— but this middleware must not add a ``Vary`` header today (14-I18N-012): the
code is already correct, only the description was wrong.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils import translation
from django.utils.cache import patch_vary_headers
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation.trans_real import parse_accept_lang_header

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
        """Determine and set the language code for the current request.

        Every source resolves to a ``LanguageLocale`` member before reaching the
        single sink ``_set_language_code``, so no branch can activate a raw,
        unvalidated code. The cookie branch normalises the cookie value through
        ``LanguageLocale.from_code``; the fallback branch normalises
        ``settings.LANGUAGE_CODE`` the same way.
        """
        lang = request.GET.get("lang")
        if lang is not None:
            self._apply_lang_param(request, lang)
            return

        cookie_value = request.COOKIES.get(LANGUAGE_COOKIE_NAME)
        if cookie_value is not None:
            resolved = LanguageLocale.from_code(
                cookie_value, fallback=LanguageLocale.BOSNIAN
            )
            self._set_language_code(request, resolved)
            return

        accept_locale = self._parse_accept_language(request)
        if accept_locale is not None:
            self._set_language_code(request, accept_locale)
            return

        self._set_language_code(
            request,
            LanguageLocale.from_code(
                settings.LANGUAGE_CODE, fallback=LanguageLocale.BOSNIAN
            ),
        )

    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Persist the ``lang_pref`` cookie and emit language response headers.

        This ``set_cookie`` call is the AUTHORITATIVE ``lang_pref`` writer: it is
        the only server-side write, it runs on every request that carried
        ``?lang=``, and it is the writer under which the cookie's ``httponly``
        attribute can safely be set (Q5 option (a), 14-I18N-009). The language
        switcher no longer writes this cookie from JavaScript.

        The cookie value is stored on the request during ``process_request``
        and applied here where we have access to the response object. The cookie
        carries the project's own security policy rather than Django's defaults:
        ``secure`` and ``samesite`` are read from ``settings.SESSION_COOKIE_*``
        so ``prod.py``'s strictness and ``dev.py``/``test.py``'s relaxation keep
        applying, and ``httponly=True`` hides the preference from
        ``document.cookie``.

        The ``Vary: Accept-Language`` / ``Content-Language`` headers are this
        middleware's only ``Vary`` contribution and do not cover cookie-driven
        locale. ``Vary: Cookie`` reaches the real response incidentally, via
        ``CsrfViewMiddleware`` on token-bearing templates — see the module
        docstring for the fragility this leaves in the token-free HTMX
        fragments and for what must be made deliberate when a shared cache is
        introduced.
        """
        cookie_value = getattr(request, "_lang_cookie_value", None)
        if cookie_value is not None:
            response.set_cookie(
                LANGUAGE_COOKIE_NAME,
                cookie_value,
                max_age=LANGUAGE_COOKIE_MAX_AGE,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite=settings.SESSION_COOKIE_SAMESITE,
                httponly=True,
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
            self._set_language_code(
                request,
                LanguageLocale.from_code(
                    settings.LANGUAGE_CODE, fallback=LanguageLocale.BOSNIAN
                ),
            )
            return

        resolved = LanguageLocale.from_code(
            lang, fallback=LanguageLocale.BOSNIAN
        )
        resolved_code = resolved.value
        self._set_language_code(request, resolved)

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

    def _set_language_code(
        self, request: HttpRequest, locale: LanguageLocale
    ) -> None:
        """Activate the language for the current thread and sync the request.

        This is the single typed sink every locale source routes through: it
        accepts a ``LanguageLocale`` MEMBER (never a raw ``str``), activates it
        via ``translation.activate(locale.value)`` — which sets the thread-local
        active language read by ``{% get_current_language %}`` and Django's
        ``i18n`` context processor — and sets ``request.LANGUAGE_CODE`` to the
        resulting ``translation.get_language()`` so the two always agree and the
        request attribute is always a member of ``settings.LANGUAGES``.
        """
        translation.activate(locale.value)
        request.LANGUAGE_CODE = translation.get_language()

    def _parse_accept_language(self, request: HttpRequest) -> LanguageLocale | None:
        """Resolve the Accept-Language header to a configured locale.

        Parses each comma-separated member together with its ``q`` parameter via
        Django's ``parse_accept_lang_header``, which returns ``((tag, q), ...)``
        already sorted descending by ``q`` and lowercased. Any member with
        ``q == 0`` is skipped explicitly — the parser retains it, and a ``q=0``
        member means "not acceptable". The first tag that maps to a
        ``LanguageLocale`` member is returned; when a header is present but no
        tag is supported the resolution falls back to ``LanguageLocale.BOSNIAN``.

        Returns ``None`` only when the header is absent or empty, so that
        ``process_request`` falls back to ``settings.LANGUAGE_CODE``.
        """
        accept_language = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
        if not accept_language or not accept_language.strip():
            return None
        for tag, q in parse_accept_lang_header(accept_language):
            if q == 0:
                continue
            resolved = LanguageLocale.from_code(tag, fallback=LanguageLocale.BOSNIAN)
            if resolved.value == tag.split("-")[0].lower():
                return resolved
        return LanguageLocale.BOSNIAN
