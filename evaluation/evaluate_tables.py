"""Reproducible local evaluation on attributed public files; no camera injection.

Run from project root: python evaluation/evaluate_tables.py [--rotations]
Optional --private <path> inputs stay local and are omitted from saved outputs.
"""
import argparse
import json
from pathlib import Path
import sys
import time
import cv2
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from broad_tables import GroundedTables
from vision import PersonDetector, overlap

parser = argparse.ArgumentParser()
parser.add_argument('--rotations', action='store_true')
parser.add_argument('--private', nargs='*', default=[])
parser.add_argument('--only', nargs='*', help='Evaluate only these public manifest IDs')
args = parser.parse_args()
manifest = json.loads((root/'evaluation/public-corpus.json').read_text(encoding='utf8'))
if args.only:
    manifest = [row for row in manifest if row['id'] in args.only]
detector = PersonDetector()
broad = GroundedTables()
out = root/'evaluation/results'
out.mkdir(exist_ok=True)
rows = []
for source in manifest + [{'id':f'private-{i+1}', 'path':path,'private':True} for i,path in enumerate(args.private)]:
    frame = cv2.imread(str(root/source['path']))
    if frame is None:
        raise ValueError('Unreadable evaluation input')
    for angle in ([0,90,180,270] if args.rotations else [0]):
        image = frame if not angle else cv2.rotate(frame,{90:cv2.ROTATE_90_CLOCKWISE,180:cv2.ROTATE_180,270:cv2.ROTATE_90_COUNTERCLOCKWISE}[angle])
        start = time.perf_counter()
        fast = detector.detect_scene(image)['tables']
        candidates = broad.detect(image)
        candidates += [item for item in fast if not any(overlap(item['box'],other['box'])>.40 for other in candidates)]
        row = {'id':source['id'],'rotation':angle,'seconds':round(time.perf_counter()-start,2),'candidates':candidates}
        print(json.dumps(row),flush=True)
        if source.get('private'):
            continue
        rows.append(row)
        rendered = image.copy()
        for item in candidates:
            x,y,x2,y2 = item['box']
            cv2.rectangle(rendered,(x,y),(x2,y2),(0,200,0),3)
            cv2.putText(rendered,f"{item['method']} score {item['confidence']}",(x,max(18,y-6)),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,180,0),1)
        cv2.imwrite(str(out/f"{source['id']}-{angle}.jpg"),rendered)
        destination = out/('detections-'+'-'.join(args.only)+'.json' if args.only else 'detections.json')
        destination.write_text(json.dumps(rows,indent=2),encoding='utf8')
