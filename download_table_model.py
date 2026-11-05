"""One-time public weight download; runtime always uses local_files_only."""
import os
from pathlib import Path
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
from huggingface_hub import snapshot_download

if __name__ == '__main__':
    snapshot_download('IDEA-Research/grounding-dino-tiny',
                      revision='a2bb814dd30d776dcf7e30523b00659f4f141c71',
                      local_dir=Path(__file__).resolve().parent / 'models/grounding-dino-tiny',
                      allow_patterns=['*.json','*.txt','*.safetensors'])
