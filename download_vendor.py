import os
import urllib.request

vendor_dir = os.path.join(os.path.dirname(__file__), 'frontend', 'static', 'vendor')
os.makedirs(vendor_dir, exist_ok=True)

urls = {
    'three.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js',
    'marked.min.js': 'https://cdn.jsdelivr.net/npm/marked/marked.min.js',
    'purify.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.3/purify.min.js',
    'highlight.min.js': 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js'
}

for name, url in urls.items():
    print(f'Downloading {name}...')
    urllib.request.urlretrieve(url, os.path.join(vendor_dir, name))

print('Done!')
