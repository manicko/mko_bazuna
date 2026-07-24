# Research Report: Template Static Tag Usage and Fix Requirements

## 1. Current Template Static Tag Analysis

### Templates Requiring CSS
All six templates uniformly use the same pattern:

```html
<!-- Common pattern in all templates -->
{% load static %}
...
<link rel="stylesheet" href="{% static 'css/output.css' %}">
```

### Template List with Static References

| Template | Line | Static Reference |
|----------|------|------------------|
| ads/list.html | 10 | `{% static 'css/output.css' %}` |
| ads/dashboard.html | 10 | `{% static 'css/output.css' %}` |
| ads/detail.html | 11 | `{% static 'css/output.css' %}` |
| ads/edit.html | 10 | `{% static 'css/output.css' %}` |
| admin/moderation/review.html | 10 | `{% static 'css/output.css' %}` |
| users/login_issue.html | 10 | `{% static 'css/output.css' %}` |

### Other Static References

**Images**: No static image references found - all images use database URLs
**JavaScript**: Only CDN reference (`htmx.org`) - no local JS files
**Media**: Database-driven, served via MEDIA_URL

## 2. Whitenoise Manifest Behavior

### With CompressedManifestStaticFilesStorage
When a file `output.css` exists in STATIC_ROOT:
1. Whitenoise creates `output.abc123.css` (hashed version)
2. Creates `output.css` as redirect to hashed version
3. Creates `staticfiles/manifest.json` for tracking

### Current Behavior (No CSS)
1. Request to `/static/css/output.css` returns 404
2. Whitenoise cannot serve non-existent files
3. Browser receives no CSS styles

## 3. Required Fixes

### Option A: Minimal Fix (Recommended)
```bash
# 1. Create tailwind.config.js in project root
# 2. Use django-tailwind management command in Dockerfile
# 3. Ensure output.css is generated in src/theme/static/theme/css/
```

### Dockerfile Change Required
```dockerfile
# REPLACE (current, broken):
RUN tailwindcss build && \
    uv run python src/backend/manage.py collectstatic --noinput

# WITH (correct):
RUN uv run python src/backend/manage.py tailwind build && \
    uv run python src/backend/manage.py collectstatic --noinput
```

### Required Files
1. **tailwind.config.js** - Tailwind configuration
2. **src/theme/static/theme/css/output.css** - Compiled CSS (generated)

### Verify After Fix
```
/static/css/output.css → exists (served by whitenoise)
/styles work on site
```

## 4. Static File Finding Summary

| Check | Result |
|-------|--------|
| Template references output.css | ✅ YES (6 files) |
| output.css exists in static/ | ❌ NO |
| input.css exists (source) | ✅ YES |
| tailwind.config.js exists | ❌ NO |
| Docker build generates output.css | ❌ NO |

## 5. Verification Commands

After fix, verify with:
```bash
# In container:
ls -la /app/staticfiles/css/output.css  # Should exist

# Or locally after collectstatic:
uv run python src/backend/manage.py collectstatic --noinput
ls -la staticfiles/css/output.css
```

## Root Cause Summary
The template static tag `{% static 'css/output.css' %}` references a file that **never gets created** because:
1. No tailwind.config.js exists for Tailwind CLI
2. Dockerfile uses direct `tailwindcss build` without proper configuration
3. Django management command `tailwind build` is never called
4. Result: no output.css, no CSS on site