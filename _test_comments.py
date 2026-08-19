"""Test multi-line template comment behavior."""
from django.conf import settings
settings.configure(
    DEBUG=True,
    TEMPLATES=[{
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
    }],
)
import django
django.setup()

from django.template import Template, Context

# Test 1: Multi-line {# #} comment (should leak - no DOTALL)
t1 = Template('Hello {# this is\na multi-line\ncomment #} World')
print("Test 1 (multi-line {# #}):")
print(repr(t1.render(Context({}))))

# Test 2: Multi-line {% comment %} block (should strip)
t2 = Template('Hello {% comment %} this is\na multi-line\ncomment {% endcomment %} World')
print("\nTest 2 (multi-line {% comment %}):")
print(repr(t2.render(Context({}))))

# Test 3: Named multi-line {% comment %}
t3 = Template('Hello {% comment doc %} this is\na multi-line\ncomment {% endcomment %} World')
print("\nTest 3 (named multi-line {% comment %}):")
print(repr(t3.render(Context({})))[:120] + "...")
