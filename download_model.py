import urllib.request
import zipfile
import os
import shutil

print('Downloading...')
urllib.request.urlretrieve('https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip', 'vosk.zip')

print('Extracting...')
with zipfile.ZipFile('vosk.zip', 'r') as zip_ref:
    zip_ref.extractall('model_temp')

print('Moving...')
shutil.copytree('model_temp/vosk-model-small-en-us-0.15', 'model', dirs_exist_ok=True)

print('Cleaning up...')
shutil.rmtree('model_temp')
os.remove('vosk.zip')
print('Done!')
