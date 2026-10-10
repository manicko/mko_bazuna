"""
Audit of Plan File P-003 — media_gate Rate Limit Causes Thumbnail Blankout on Sort

Output: code_context
Status: Read-only investigation of actual source code (no code changes).
"""

# =====================================================================
# CODE_CONTEXT — AUDIT FINDINGS
# =====================================================================

## 1. FULL CURRENT IMPLEMENTATION (evidence from actual source)

### 1a. RateLimitBudget.MEDIA_GATE — src/backend/apps/core/enums.py

  Member declaration (line 53):
      MEDIA_GATE = "media_gate"

  The member's .value is the STRING "media_gate" (a StrEnum), NOT a tuple.
  The request count and window period are NOT stored on the member itself;
  they live in two @property dicts:

      @property
      def requests(self) -> int:          # lines 55-64
          return {
              RateLimitBudget.SEARCH_PAGE: 30,
              RateLimitBudget.AUTOCOMPLETE: 30,
              RateLimitBudget.DEEP_LINK_RENDER: 60,
              RateLimitBudget.LOGIN_ISSUE: 10,
              RateLimitBudget.MEDIA_GATE: 60,     # ← line 63
          }[self]

      @property
      def period(self) -> int:             # lines 66-75
          return {
              RateLimitBudget.SEARCH_PAGE: 60,
              RateLimitBudget.AUTOCOMPLETE: 60,
              RateLimitBudget.DEEP_LINK_RENDER: 600,
              RateLimitBudget.LOGIN_ISSUE: 60,
              RateLimitBudget.MEDIA_GATE: 60,      # ← line 74
          }[self]

  Docstring (lines 45-46):
      "MEDIA_GATE: 60 requests / 60 s. Anonymous DB-backed media serving;
       protects the database from an over-budget client (09-API-005)."

  Related enum members (all confirmed in enum, NOT mentioned in plan):
      SEARCH_PAGE = "search_page"        → (30, 60)
      AUTOCOMPLETE = "autocomplete"      → (30, 60)  (shares value, own namespace)
      DEEP_LINK_RENDER = "deep_link_render" → (60, 600)
      LOGIN_ISSUE = "login_issue"         → (10, 60)

### 1b. media_gate view — src/backend/apps/ads/views/listings.py

  Module-level rate-limit constants (lines 51-64):

      # Lines 51-55: explanatory comment block
      #   "The budget (60 requests / 60 s per client IP) now lives in the shared
      #    RateLimitBudget.MEDIA_GATE table (08-SRCH-010); ..."
      #   "nginx's location /media/ carries browse_limit burst=40 in both sites"
      MEDIA_RATE_LIMIT_REQUESTS: int = RateLimitBudget.MEDIA_GATE.requests  # line 60
      MEDIA_RATE_LIMIT_PERIOD: int = RateLimitBudget.MEDIA_GATE.period      # line 62
      _MEDIA_RATE_LIMIT_KEY_PATTERN: Final[str] = "media_gate_rl:{ip}"    # line 64

  IMPORTANT DISCREPANCY #1: _MEDIA_RATE_LIMIT_KEY_PATTERN is declared in
  THIS FILE (listings.py:64), NOT in client_ip.py. See §3 for details.

  The view function (lines 151-255) — full flow:

      @vary_on_headers("Cookie")                          # line 151
      def media_gate(request: HttpRequest, image_key: str) -> HttpResponseBase:  # line 152
          # --- RATE LIMIT GUARD (runs FIRST) ---        # lines 181-191
          media_key = _MEDIA_RATE_LIMIT_KEY_PATTERN.format(ip=get_client_ip(request))
          if not bump_rate_limit_window(
              media_key, MEDIA_RATE_LIMIT_REQUESTS, MEDIA_RATE_LIMIT_PERIOD
          ):
              logger.warning("Media gate rate limit exceeded")     # line 190
              return rate_limited_response(json=False)             # line 191 → 429

          # --- NUL byte guard ---                        # lines 193-199
          if any(ord(ch) < 0x20 for ch in image_key):
              raise Http404("Image not found")

          # --- Path-traversal guard ---                  # lines 201-207
          try:
              assert_storage_key_contained(image_key)     #  apps/media/services/filesystem.py:173
          except ValueError:
              raise Http404("Image not found") from None

          # --- AdImage lookup (DB) ---                   # lines 209-220
          key_q = Q()
          for column in KEY_COLUMNS:                      # KEY_COLUMNS = ("image","thumb_...3","thumb_medium","thumb_large")
              key_q |= Q(**{column: image_key})
          if not AdImage.objects.filter(key_q).exists():
              raise Http404("Image not found")

          # --- STAFF branch ---                          # lines 222-231
          if request.user.is_staff:
              if settings.DEBUG:
                  response = _serve_image(image_key)
                  response["Cache-Control"] = "no-cache"
                  return response
              response = HttpResponse()
              response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
              response["Cache-Control"] = "no-store"
              return response

          # --- NON-STAFF authorization + serve ---       # lines 233-254
          # account_state_q: is_deleted=False, is_declined=False,
          #   is_banned=False, consent_revoked_at IS NULL, is_active=True
          if not AdImage.objects.filter(
              account_state_q("ad__user__"),
              key_q,
              ad__status=AdStatus.PUBLISHED,
          ).exists():
              return HttpResponseForbidden(_("Access denied"))     # line 245 → 403

          if settings.DEBUG:
              response = _serve_image(image_key)
              response["Cache-Control"] = "no-cache"
              return response

          response = HttpResponse()
          response["X-Accel-Redirect"] = f"/protected-media/{image_key}"
          response["Cache-Control"] = "no-store"
          return response

  Key constants/functions used:
      get_client_ip                # src/backend/apps/core/utils/client_ip.py:61
      bump_rate_limit_window       # src/backend/apps/core/utils/cache.py:60
      rate_limited_response        # src/backend/apps/core/utils/rate_limit_response.py:27
      assert_storage_key_contained # src/backend/apps/media/services/filesystem.py:173
      KEY_COLUMNS                  # src/backend/apps/media/storage_keys.py:33
      account_state_q              # src/backend/apps/users/services/account_state.py:81
      _serve_image                 # src/backend/apps/ads/views/listings.py:131

### 1c. bump_rate_limit_window — src/backend/apps/core/utils/cache.py

  Full function (lines 60-90):

      def bump_rate_limit_window(key: str, limit: int, period: int) -> bool:
          try:
              if cache.add(key, 1, timeout=period):   # line 80: first hit
                  return True                          # line 81
              current = cache.incr(key)               # line 82: subsequent hits
          except (ConnectionInterrupted, redis.RedisError):
              logger.warning("Cache write failed for %s; allowing request", key)
              return True                              # fail-open
          except ValueError:
              # Key expired between add/incr — treat as fresh start.
              cache.set(key, 1, timeout=period)       # line 88
              return True                              # line 89
          return current <= limit                      # line 90

  Behavior: True for counts 1..limit (60), False for count 61.
  TTL = period (60s). After expiry, cache.add resets the window.

### 1d. rate_limited_response — src/backend/apps/core/utils/rate_limit_response.py

  Full function with overloads (lines 19-41):

      @overload
      def rate_limited_response(*, json: Literal[True] = True) -> JsonResponse: ...

      @overload
      def rate_limited_response(*, json: Literal[False]) -> HttpResponse: ...

      def rate_limited_response(*, json: bool = True) -> HttpResponse:
          if json:
              return JsonResponse({"error": RATE_LIMIT_ERROR}, status=429)
          return HttpResponse(status=429)           # ← bare 429, empty body

  RATE_LIMIT_ERROR (line 16): "rate_limit"

  media_gate calls rate_limited_response(json=False) → HttpResponse(status=429)
  with NO body, NO Cache-Control, NO Retry-After.

### 1e. _MEDIA_RATE_LIMIT_KEY_PATTERN + get_client_ip

  _MEDIA_RATE_LIMIT_KEY_PATTERN: "media_gate_rl:{ip}"
    Location: src/backend/apps/ads/views/listings.py:64  (NOT client_ip.py)

  get_client_ip — src/backend/apps/core/utils/client_ip.py (full function lines 61-95):
      def get_client_ip(request: HttpRequest) -> str:
          peer = _parse(request.META.get("REMOTE_ADDR"))     # line 78
          if peer is None:                                     # line 79
              return _UNKNOWN                                   # "unknown"
          if not _is_trusted_peer(peer):                      # line 82
              return str(peer)                              # line 83
          real_ip = _parse(request.META.get("HTTP_X_REAL_IP"))  # line 85
          if real_ip is not None:                              # line 86
              return str(real_ip)                            # line 87
          forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")  # line 89
          for hop in reversed(forwarded.split(",")):            # line 90
              candidate = _parse(hop)                          # line 91
              if candidate is not None and not candidate.is_private:
                  return str(candidate)                        # line 93
          return str(peer)                                    # line 95

  _is_trusted_peer (lines 48-58): returns True for loopback or private peers,
  or if peer is in settings.TRUSTED_PROXY_NETWORKS.

  Helper functions in client_ip.py: _parse (lines 38-45), _is_trusted_peer (48-58),
  _UNKNOWN = "unknown" (line 35).

  DISCREPANCY: client_ip.py does NOT contain _MEDIA_RATE_LIMIT_KEY_PATTERN.
  Each rate-limiter module declares its OWN key pattern:
    - listings.py:64       → _MEDIA_RATE_LIMIT_KEY_PATTERN = "media_gate_rl:{ip}"
    - contact_rate_limit.py:24 → _RATE_LIMIT_KEY_PATTERN = "telegram_dl_rl:{ip}"
    - login_rate_limit.py:27  → _RATE_LIMIT_KEY_PATTERN = "login_rl:{ip}"
    - search/services/rate_limit.py:29 → _RATE_LIMIT_KEY_PATTERN = "{namespace}_rl:{ip}"

### 1f. URL routing — src/backend/apps/ads/urls.py

  Line 25:  path("media/<path:image_key>", media_gate, name="media_gate"),

  Root URLconf — src/backend/config/urls.py:
  - Line 60:  path("", include("apps.ads.urls"))  — includes ads URLs
  - NO static() call anywhere (confirmed by grep across entire repo)
  - NO django.views.static.serve usage anywhere (confirmed by grep)

  Full media route flow: client → (nginx in prod) → Django → config/urls.py:60
    → apps/ads/urls.py:25 → media_gate view

### 1g. Template rendering — ad_list.html + filter_form.html

  ad_list.html (src/backend/templates/ads/partials/ad_list.html):
  - Lines 116-168: {% for ad in page_obj %} ... {% endfor %} renders ONE <img>
    per ad card.
  - Lines 125-131: the <img> tag:
      <img src="{{ ad.images.first.thumbnail_small_url|default:ad.images.first.image_url }}"
           alt="{{ ad|get_title:LANGUAGE_CODE }}"
           class="w-full h-48 object-contain bg-white rounded-t-lg"
           loading="lazy"
           width="240"
           height="180">
  - Per-page count = ListingsQuery.PER_PAGE = 24
    (src/backend/apps/ads/services/listings_query.py:92 and :173)
  - Confirmed: home.html snapshot at repo root has exactly 24 <img src="/media/...">
    tags (grep: 24 matches in home.html).

  filter_form.html (src/backend/templates/ads/partials/filter_form.html):
  - Lines 4-9: the form with HTMX attributes:
      <form method="get"
            hx-get="{{ request.path }}"
            hx-target="#ad-list"
            hx-swap="innerHTML"
            hx-push-url="true"
            class="mb-6 ...">
  - Lines 112-132: the sort <select>:
      <div class="ml-auto">
          <label for="sort">{% trans "Sort" %}</label>
          <select name="sort" id="sort" ... onchange="this.form.requestSubmit()">
              <option value="date_desc">Newest first</option>
              <option value="date_asc">Oldest first</option>
              <option value="price_asc">Price: low to high</option>
              <option value="price_desc">Price: high to low</option>
          </select>
      </div>

  Sort = onchange → this.form.requestSubmit() → HTMX GET → server renders
  ads/partials/ad_list.html (HX-Request) → Swaps #ad-list innerHTML →
  browser parses 24 new <img> tags → 24 new /media/ fetches.

  listings view template selection (listings.py:318-322):
      return render(
          request,
          "ads/partials/ad_list.html" if request.headers.get("HX-Request") else "ads/list.html",
          context,
      )


## 2. PLAN-vs-CODE VERIFICATION (confirm/contradict every claim)

  ┌─────────────────────────────────────────────────────────────────┬──────────┐
  │ Plan Claim                                                        │ Verdict  │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ RateLimitBudget.MEDIA_GATE = (60 requests, 60 seconds)            │ CONFIRM  │
  │   enums.py:53 MEDIA_GATE="media_gate"; .requests→60 (line 63);    │          │
  │   .period→60 (line 74). Value is a string, not a tuple.           │          │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ media_gate rate-limit guard runs BEFORE DB lookup / disk access   │ CONFIRM  │
  │   listings.py:186-191 (guard) precede lines 198-199 (NUL),        │          │
  │   204-207 (traversal), 219 (AdImage.exists() DB query),           │          │
  │   247+ (serving). Over-budget client never reaches DB or disk.    │          │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ Cache-Control: no-cache (DEBUG) / no-store (prod)                 │ CONFIRM  │
  │   DEBUG path: no-cache at listings.py:226 (staff) and :249 (non-   │          │
  │   staff). Prod path: no-store at :230 (staff) and :254 (non-staff)│          │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ No ETag / Last-Modified set                                       │ CONFIRM  │
  │   USE_ETAGS not set anywhere → Django default False. No           │          │
  │   ConditionalGetMiddleware/EtagMiddleware in MIDDLEWARE list.    │          │
  │   _serve_image returns FileResponse with no Last-Modified.         │          │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ 429 returns empty body (HttpResponse(status=429))                  │ CONFIRM  │
  │   rate_limited_response(json=False) → HttpResponse(status=429).   │          │
  │   Content-Length: 0. No Cache-Control or Retry-After on 429.      │          │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ URL route: path("media/<path:image_key>", media_gate, ...)        │ CONFIRM  │
  │   apps/urls.py:25. No static() or django.views.static.serve.      │          │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ 24 thumbnails per listing page                                    │ CONFIRM  │
  │   ListingsQuery.PER_PAGE=24 (listings_query.py:92,173). Template   │          │
  │   renders 1 <img> per ad in page_obj loop. home.html has 24 <img>.│          │
  ├─────────────────────────────────────────────────────────────────┼──────────┤
  │ HTMX sort triggers re-render of #ad-list                           │ CONFIRM  │
  │   filter_form.html:4-9 <form hx-get hx-target="#ad-list">;       │          │
  │   sort <select onchange="this.form.requestSubmit()"> line 117.    │          │
  └─────────────────────────────────────────────────────────────────┴──────────┘

  CONFIRMED test assertions (plan lists them; all verified):
  - test_rate_limit_budget.py:82
    assert (RateLimitBudget.MEDIA_GATE.requests, RateLimitBudget.MEDIA_GATE.period)==(60,60)
  - test_rate_limit_budget.py:67-74
    test_media_gate_limiter_matches_its_budget
  - test_media_security.py:923-938 test_burst_over_budget_is_refused
  - test_media_security.py:940-956 test_over_budget_is_refused_before_the_db_lookup
  - test_media_security.py:994-996 test_period_constant_is_the_documented_window
  - test_media_security.py:718-852 TestMediaGateCacheControl (class spans 718-852)


## 3. RELEVANT ARCHITECTURE, DEPENDENCIES, CONSTRAINTS

### Cache backend config

  Dev (config/settings/dev.py:58-63):
      CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
  → Single-process, in-memory. Rate-limit counter is process-global.

  Test (config/settings/test.py:92-97):
      CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
  → Same LocMemCache pattern (no Redis needed for tests).

  Base/prod (config/settings/base.py:620-638):
      REDIS_URL = env("REDIS_URL", default="")
      CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache",
                             "LOCATION": REDIS_URL, ...}}
  → Redis shared across gunicorn workers + bot process. prod.py:355-360
     fails-fast if REDIS_URL is empty.

  Key implication (dev): LocMemCache is shared across all requests in the
  single dev-server process, so the 60/60s counter persists across browser
  sorts AND curl probes from the same IP (127.0.0.1). This is exactly what
  the curl reproduction demonstrates.

### USE_ETAGS

  NOT set in any settings module (grep across src/backend: zero matches).
  Django default: USE_ETAGS = False. No ConditionalGetMiddleware or
  EtagMiddleware in MIDDLEWARE (base.py:332-348). → No automatic ETag
  or Last-Modified generation on any response, including media_gate.

### media_gate full flow (request lifetime)

  1. HTTP request enters Django
  2. Middleware chain runs (base.py:332-348):
     - SecurityMiddleware, WhiteNoise, SessionMiddleware, CommonMiddleware,
       DbLockTimeoutMiddleware, CsrfViewMiddleware, AuthenticationMiddleware,
       LanguagePreMiddleware, CityResolutionMiddleware, PreferredCityMiddleware,
       JSExecutionMiddleware, MessageMiddleware, XFrameOptionsMiddleware,
       PrometheusBeforeMiddleware/AfterMiddleware
  3. LanguagePreMiddleware.process_response (language.py:159) calls
     patch_vary_headers(response, ("Accept-Language",)) on EVERY response,
     adding "Vary: Accept-Language" — explains the curl-observed header.
  4. URL routing: config/urls.py:60 → apps/urls.py:25 → media_gate
  5. @vary_on_headers("Cookie") decorator adds "Vary: Cookie"
     (lists both, so final Vary: Cookie, Accept-Language)
  6. media_gate body (listings.py:186-255):
     a. Rate-limit guard (cache.add/incr) → 429 if over budget
     b. NUL-byte check → 404
     c. Path-traversal guard (assert_storage_key_contained) → 404
     d. AdImage.objects.filter(key_q).exists() → 404 if no match
     e. Staff check → serve with Cache-Control
     f. Non-staff account_state_q authorization → 403 if not eligible
     g. DEBUG: _serve_image (FileResponse) + Cache-Control: no-cache
        prod: HttpResponse + X-Accel-Redirect + Cache-Control: no-store

### nginx (proxy half of the defense)

  docker/nginx/nginx.conf:112 and docker/nginx/nginx.dev.conf:107:
      location /media/ {
          limit_req zone=browse_limit burst=40 nodelver;
          proxy_pass http://web:8000;
          ...
      }
  Rate zone: browse_limit at nginx.conf:26 / nginx.dev.conf:29:
      limit_req_zone $binary_remote_addr zone=browse_limit:10m rate=20r/s;
  → 20 r/s with burst=40. In dev WITHOUT nginx (runserver directly), only the
    application-level MEDIA_GATE limiter (60/60s) applies. This is why the
    curl reproduction on 127.0.0.1:8000 hits the 60/61 boundary: no nginx
    proxy is in front of runserver.

### django.views.static.serve / static() for media — NOT USED

  Grep across entire repo (src/backend): zero matches for
  "from django.conf.urls.static import", "from django.urls import.*static",
  or "static(settings.MEDIA". The root URLconf (config/urls.py) does not
  call static() for media. Every /media/ request hits media_gate.


## 4. DISCREPANCIES IN THE PLAN / NEW RELEVANT CODE

### DISCREPANCY #1: _MEDIA_RATE_LIMIT_KEY_PATTERN location (HIGH severity)

  PLAN CLAIM: researcher_2 localization table (line 159) and P-003 §3
  list "_MEDIA_RATE_LIMIT_KEY_PATTERN ... in src/backend/apps/core/utils/client_ip.py".

  ACTUAL: _MEDIA_RATE_LIMIT_KEY_PATTERN is declared at
  src/backend/apps/ads/views/listings.py:64.
  client_ip.py (95 lines) contains only: _UNKNOWN (line 35), _parse (lines
  38-45), _is_trusted_peer (lines 48-58), get_client_ip (lines 61-95).
  It does NOT contain _MEDIA_RATE_LIMIT_KEY_PATTERN.

  Impact: Any remediation referencing "client_ip.py" for the key pattern
  would edit the wrong file. The pattern lives with the view that uses it,
  consistent with the per-module pattern used by all four rate-limiters
  (contact_rate_limit.py, login_rate_limit.py, search rate_limit.py,
  listings.py each declare their own _RATE_LIMIT_KEY_PATTERN).

### DISCREPANCY #2: media_gate line range (LOW severity)

  PLAN CLAIM: researcher_2 localization table (line 157) cites
  "media_gate view | listings.py | 131–147".

  ACTUAL: The @vary_on_headers decorator is at listings.py:151; the def is
  at line 152; the function body spans lines 152-255 (ends at line 255 with
  the final `return response`). The plan's "131-147" does not correspond to
  the current file. The researcher's own prose (line 149) correctly notes
  "Lines 186–191 (rate-limit guard) precede lines 198–255 (path-traversal,
  DB lookup, DEBUG/serving branch)", so the function IS known to extend to
  255. The table entry 131-147 is stale or refers to an earlier version.

  Correct line range: decorator at 151, def at 152, body 152-255.

### DISCREPANCY #3: Simplified media_gate code snippet (MEDIUM severity)

  The plan (P-003 lines 73-78) and researcher_1 (lines 131-148) both show a
  simplified media_gate body:
      # ... path-traversal guard, AdImage lookup, X-Accel-Redirect / DEBUG serve ...

  ACTUAL: The full function (lines 152-255) has FOUR serving branches, not
  two:
    - Staff + DEBUG  (lines 223-227):  _serve_image + Cache-Control: no-cache
    - Staff + prod   (lines 228-231):  HttpResponse + X-Accel + no-store
    - Non-staff auth check (lines 240-244): account_state_q filter
    - Non-staff + DEBUG  (lines 247-250):  _serve_image + Cache-Control: no-cache
    - Non-staff + prod   (lines 252-254):  HttpResponse + X-Accel + no-store

  Plus the NUL-byte guard (lines 198-199) and the KEY_COLUMNS loop (lines
  215-217) that are not mentioned in the plan's snippet.

  Impact: Remediation that assumes a 2-branch structure may miss the
  account_state_q authorization check (line 240-244) or the staff bypass
  (line 223), both of which affect how changes to the serving path must be
  structured.

### DISCREPANCY #4: bump_rate_limit_window snippet omits ValueError handling (LOW)

  PLAN (P-003 lines 102-108) and researcher_1 (lines 180-191) show a
  simplified version that omits the ValueError except block:

      except ValueError:
          cache.set(key, 1, timeout=period)  # key expired between add/incr
          return True

  This is present in the actual code (cache.py:86-89). It is not a
  behavioral discrepancy — the snippet just elides it — but the plan's
  "return current <= limit  # True for 1–60, False for 61" glosses the
  reset-on-expiry path that explains the "reappear after 60s" behavior.

### DISCREPANCY #5: 429 response has no Retry-After header (NEW RISK, not in plan)

  The plan correctly notes the 429 body is empty (HttpResponse(status=429)).
  However, NEITHER the plan nor the researcher reports note that the 429
  response omits the HTTP "Retry-After" header, which RFC 9110 §15.4.5 and
  RFC 6585 §4 recommend for 429 responses. This prevents the browser from
  knowing how long to wait before retrying. The codebase DOES set Retry-After
  elsewhere (db_lock_timeout.py:68 for 503), so there is a precedent; it is
  simply not applied to rate-limit 429s.

  rate_limited_response (rate_limit_response.py:40-41) returns
  HttpResponse(status=429) with no headers beyond what vary_on_headers and
  LanguagePreMiddleware add.

### NEW RELEVANT CODE NOT MENTIONED IN PLAN

#### 4a. listings view has its OWN rate limit (listings.py:268-271) — NOT in plan

      # Rate limit (CR-10)
      if not request.headers.get("HX-Request") and not check_deep_link_render_rate_limit(request):
          logger.warning("Deep-link render rate limit exceeded (listings)")
          return rate_limited_response(json=False)

  This uses DEEP_LINK_RENDER budget (60 req / 600s) via
  contact_rate_link.py:27. Critically, the guard ONLY applies when
  NOT an HTMX request (`not request.headers.get("HX-Request")`). HTMX sorts
  carry `HX-Request: true` and therefore BYPASS this guard entirely. So:
    - Full page load (GET /): subject to DEEP_LINK_RENDER (60/600s) rate limit
    - HTMX sort (GET /?sort=... with HX-Request): NOT subject to any
      listings-view rate limit; only the 24 media_gate calls count

  This means the plan's diagnosis is correct that ONLY MEDIA_GATE is
  exhausted during sorts — but the plan does not mention that the listings
  view also carries a (bypassed) rate limit, which is relevant context for
  understanding why the sort path specifically hits only MEDIA_GATE.

#### 4b. Other rate-limiters in the ecosystem (not in plan's cross-reference)

  Four additional rate-limit modules share bump_rate_limit_window:
  - src/backend/apps/core/services/contact_rate_limit.py
      DEEP_LINK_RENDER (60/600s) — key: "telegram_dl_rl:{ip}"
      Used by: ad_detail (listings.py:81), listings (listings.py:269)
  - src/backend/apps/users/services/login_rate_limit.py
      LOGIN_ISSUE (10/60s) — key: "login_rl:{ip}"
  - src/backend/apps/search/services/rate_limit.py
      AUTOCOMPLETE (30/60s) — key: "{namespace}_rl:{ip}"
      Also SEARCH_PAGE uses rate_limit.py but with check_search_rate_limit
      (separate function, SEARCH_PAGE budget 30/60s)

  These are declared in RateLimitBudget docstring (enums.py:37-46) but
  the plan does not list them as the broader ecosystem. None of them
  interact with media_gate (independent key namespaces).

#### 4c. home.html static snapshot (not in plan)

  A file at the repo ROOT (C:\py_dev\mko_bazuna\home.html, 4396+ lines)
  contains exactly 24 <img src="/media/seed/...-small.jpg"> tags
  (grep confirmed 24 matches). This is a captured page snapshot used as a
  reference fixture, NOT a Django template. The live template is
  templates/ads/partials/ad_list.html. The plan/researcher correctly
  analyzed the live template; the home.html snapshot simply corroborates
  the 24-image-per-page count independently.

#### 4d. Vary header source (not in plan)

  The curl-observed "Vary: Cookie, Accept-Language" on both 200 and 429
  responses comes from TWO sources:
  1. @vary_on_headers("Cookie") decorator on media_gate (listings.py:151)
  2. LanguagePreMiddleware.process_response (language.py:159):
     patch_vary_headers(response, ("Accept-Language",))
  This is applied to EVERY response, including the 429. The plan mentions
  Vary: Cookie from the decorator but does not explain the Accept-Language
  half (which comes from the language middleware, not the view).

#### 4e. DbLockTimeoutMiddleware in MIDDLEWARE (not in plan)

  base.py:338: "apps.core.middleware.db_lock_timeout.DbLockTimeoutMiddleware"
  This middleware converts lock-timeout OperationalError into a 503 with
  Retry-After header (db_lock_timeout.py:68). It is in the middleware stack
  but does not affect media_gate (which does not hold DB locks). Mentioned
  here only because it is the ONLY place in the codebase that sets
  Retry-After, and media_gate's 429 does not follow that precedent.

### CONFIRMED: Plan correctly identifies the seed-write race as separate (P-001)

  The plan correctly distinguishes this from the prior audit (.ai/audit/problems.md)
  which blamed _preprocess_one's non-atomic write (apps/seed/generators/images.py).
  _preprocess_one runs only during `docker compose run --rm seed` — confirmed at
  src/backend/apps/seed/generators/images.py (the atomic write fix was applied
  per problems.md "Fix Applied", commit a0e19c52/Oct 3). The seed writer is NOT
  on the browser-sort code path. The plan's separation of concerns is correct.
