import os
import sys

# Ensure project root on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lep_backend.settings')

import django
from django.urls import get_resolver

django.setup()

resolver = get_resolver()

print('Listing API URL patterns:')

for pattern in resolver.url_patterns:
    try:
        print(repr(pattern))
    except Exception as e:
        print('Error printing pattern:', e)

# Also attempt to introspect router-generated routes if available
try:
    from rest_framework.routers import SimpleRouter
    print('\nAttempting to list all named routes via resolver.reverse_dict keys...')
    keys = sorted(k for k in resolver.reverse_dict.keys() if isinstance(k, str))
    for k in keys:
        print(k)
except Exception as e:
    print('Router introspect failed:', e)
