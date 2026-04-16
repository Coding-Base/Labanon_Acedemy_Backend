import os, sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE','lep_backend.settings')
import django
from django.urls import get_resolver

django.setup()
resolver = get_resolver()

print('--- URL Patterns ---')
for p in resolver.url_patterns:
    print(repr(p))

print('\n--- Reverse Keys Containing diploma ---')
keys = [k for k in resolver.reverse_dict.keys() if isinstance(k, str) and 'diploma' in k]
for k in sorted(keys):
    print(k)
