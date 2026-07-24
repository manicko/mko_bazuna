# Research Report: Static Files Structure and Whitenoise Configuration

## 1. STATICFILES_DIRS and STATIC_ROOT Configuration

### From settings/base.py (lines 152-156)
```python
# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
# STATIC_ROOT lives at /app/staticfiles so it matches the path copied out of the
# builder stage in docker/Dockerfile and served by whitenoise at runtime.
STATIC_ROOT = BASE_DIR.parent / "staticfiles"
STATICFILES_DIRS = [BASE_DIR.parent / "static"]
```

### Production Settings (prod.py line 25)
```python
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"
```

## 2. Directory Structure Analysis

### Existing Files
```
src/theme/static/theme/
└── css/
    └── input.css (90 bytes - contains @tailwind directives)

static/ (project root)
├── css/ (EMPTY)
├── img/ (EMPTY)
└── js/ (EMPTY)

staticfiles/ (project root)
└── DOES NOT EXIST - created during Docker build
```

### Missing Files
- **static/css/output.css** - NOT FOUND (empty directory)
- **staticfiles/css/output.css** - NOT FOUND (staticfiles doesn't exist)
- **tailwind.config.js** - NOT FOUND (no Tailwind configuration)

## 3. Whitenoise Configuration

### Settings (base.py lines 174-181)
```python
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

### Middleware (base.py line 94)
```python
MIDDLEWARE = [
    ...
    "whitenoise.middleware.WhiteNoiseMiddleware",
    ...
]
```

### How It Works
1. **CompressedManifestStaticFilesStorage**:
   - Compresses CSS/JS files (gzip, brotli)
   - Generates manifest.json with hash names for cache busting
   - Serves files with proper Content-Type headers
   
2. **WhiteNoiseMiddleware**:
   - Intercepts requests to /static/ URLs
   - Serves files from STATIC_ROOT without nginx
   - Adds compression and caching headers

## 4. Template Static Tag Usage Analysis

### All Templates Using CSS
```
/src/backend/templates/ads/list.html (line 10)
    <link rel="stylesheet" href="{% static 'css/output.css' %}">

/src/backend/templates/ads/dashboard.html (line 10)
    <link rel="stylesheet" href="{% static 'css/output.css' %}">

/src/backend/templates/ads/detail.html (line 11)
    <link rel="stylesheet" href="{% static 'css/output.css' %}">

/src/backend/templates/ads/edit.html (line 10)
    <link rel="stylesheet" href="{% static 'css/output.css' %}">

/src/backend/templates/admin/moderation/review.html (line 10)
    <link rel="stylesheet" href="{% static 'css/output.css' %}">

/src/backend/templates/users/login_issue.html (line 10)
    <link rel="stylesheet" href="{% static 'css/output.css' %}">
```

### Template Loading
```html
{% load static %}  <!-- All templates include this -->
```

## 5. Static File Search Results

| Path | Status |
|------|--------|
| static/css/output.css | EMPTY DIRECTORY |
| staticfiles/css/output.css | DIRECTORY DOES NOT EXIST |
| src/theme/static/theme/css/input.css | EXISTS (90 bytes) |
| tailwind.config.js | DOES NOT EXIST |

## 6. Expected vs Actual Build Flow

### Expected (Working)
```
1. tailwind build → src/theme/static/theme/css/output.css
2. collectstatic → staticfiles/css/output.css (copied from theme/)
3. whitenoise serves → /static/css/output.css
4. Template {% static %} → /static/css/output.css (or hashed version)
```

### Actual (Broken)
```
1. tailwindcss build FAILS (no config) → NO OUTPUT
2. collectstatic → staticfiles/ stays empty
3. whitenoise finds nothing → 404 for CSS
4. Template {% static %} → /static/css/output.css → FILE NOT FOUND
```

## Key Finding
The **{% static 'css/output.css' %} template tag will never find output.css** because:
1. Tailwind build produces no output file
2. collectstatic has nothing to copy
3. The static directory tree is completely empty