"""Private operational status and non-destructive retention previews."""
import json
from pathlib import Path
import time

ISSUES={'engine_offline','router_offline','public_offline','camera_blocked','camera_unavailable','capture_unknown','database_missing','database_unrecognized','unexpected_service'}

def read_status(path, fields):
    try:
        path=Path(path)
        if path.stat().st_size>65536:return None
        value=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value,dict):return None
        return {key:value[key] for key in fields if key in value and isinstance(value[key],(str,int,float,bool,type(None)))}
    except (OSError,ValueError,TypeError):return None

def retention_preview(store,now=None):
    now=time.time() if now is None else now
    with store.db() as db:
        def count(sql,args=()):return db.execute(sql,args).fetchone()[0]
        candidates={
            'completed_visits':count('SELECT count(*) FROM visits WHERE cleaned IS NOT NULL AND cleaned<?',(now-90*86400,)),
            'closed_queue':count("SELECT count(*) FROM queue WHERE status NOT IN ('waiting','called') AND joined<?",(now-30*86400,)),
            'past_reservations':count("SELECT count(*) FROM reservations WHERE status!='booked' AND end<?",(now-90*86400,)),
            'old_events':count('SELECT count(*) FROM events WHERE at<?',(now-90*86400,)),
            'expired_sessions':count('SELECT count(*) FROM sessions WHERE expires<=?',(now,)),
        }
    return {'mode':'preview_only','delete_enabled':False,'candidates':candidates,
            'proposed_days':{'completed_visits':90,'closed_queue':30,'past_reservations':90,'old_events':90},
            'camera_recording':'Frames are processed in memory; the application does not continuously record video.',
            'review':'Preview only. The owner must choose a retention policy before deletion is enabled.'}

def operations_status(store,directory):
    directory=Path(directory)
    monitor=read_status(directory/'monitor-status.json',{'at','state','last_recovery_at','recovery_ok','installation'})
    if monitor is not None:
        try:
            raw=json.loads((directory/'monitor-status.json').read_text(encoding='utf-8-sig'))
            monitor['issues']=[issue for issue in raw.get('issues',[]) if issue in ISSUES]
        except (OSError,ValueError,TypeError):monitor['issues']=[]
    backup=read_status(directory/'backup-status.json',{'at','ok','integrity','cloud_state','last_restore_verified_at','archive_sha256','error_type'})
    with store.db() as db:
        staff=[dict(row) for row in db.execute('SELECT name,role FROM users ORDER BY name')]
        mapped=db.execute('SELECT count(*) FROM tables WHERE camera IS NOT NULL AND vision=1').fetchone()[0]
    return {'monitor':monitor,'backup':backup,'retention':retention_preview(store),'staff':staff,'mapped_tables':mapped}
