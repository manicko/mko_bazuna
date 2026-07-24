# CSS Issue: Root Cause Analysis Summary

## Problem Statement
Site renders with bare HTML, no CSS styles applied. The template references `{% static 'css/output.css' %}` but this file does not exist.

## Root Cause
**Tailwind CSS is not being built.** The `output.css` file is never generated, so `collectstatic` has nothing to serve and whitenoise returns 404.

## Evidence Chain

### 1. Template References (6 files)
All templates use: `<link rel="stylesheet" href="{% static 'css/output.css' %}">`

### 2. Static Directory Status
```
static/css/      - EXISTS but EMPTY
staticfiles/     - DOES NOT EXIST (created by collectstatic)
```

### 3. Source Files Present
```
src/theme/static/theme/css/input.css - EXISTS (90 bytes, has @tailwind directives)
```

### 4. Missing Configuration
```
tailwind.config.js - DOES NOT EXIST (required for Tailwind CLI)
```

### 5. Dockerfile Build Process (Broken)
```dockerfile
# Line 66-67 in docker/Dockerfile
RUN tailwindcss build && \
    uv run python src/backend/manage.py collectstatic --noinput
```
**Issue**: `tailwindcss build` runs without configuration and produces no output.

## Fix Requirements

### Immediate Actions
1. **Create tailwind.config.js** in project root with:
   - Input path: `src/theme/static/theme/css/input.css`
   - Output path: `src/theme/static/theme/css/output.css`

2. **Fix Dockerfile build command**:
   ```dockerfile
   RUN uv run python src/backend/manage.py tailwind build && \
       uv run python src/backend/manage.py collectstatic --noinput
   ```

### Expected Result
```
staticfiles/css/output.css - EXISTS (after collectstatic copies from theme/)
Site receives CSS and renders styled HTML
```

## Files Created
- research_tailwind_config.md
- research_docker_deployment.md
- research_static_files_structure.md
- research_template_static_usage.md