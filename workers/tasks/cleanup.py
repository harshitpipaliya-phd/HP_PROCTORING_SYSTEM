"""
workers/tasks/cleanup.py
========================
Celery task for periodic cleanup of old data and stale sessions.
"""

from workers.celery_app import task


@task(name="cleanup_stale_sessions")
def cleanup_stale_sessions(max_age_hours: int = 48):
    """Remove sessions older than ``max_age_hours`` from the in-memory registry."""
    try:
        from core.session import _session_registry, _registry_lock, _current_session, _session_lock
        import time

        cutoff = time.time() - max_age_hours * 3600
        to_remove = []
        with _registry_lock:
            for sid, sess in list(_session_registry.items()):
                if not getattr(sess, "_active", False) and sess.start_time < cutoff:
                    to_remove.append(sid)
                    _session_registry.pop(sid, None)

        with _session_lock:
            if _current_session and _current_session.start_time < cutoff:
                _current_session = None

        return {"success": True, "removed": len(to_remove)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@task(name="cleanup_temp_files")
def cleanup_temp_files(max_age_hours: int = 24):
    """Remove old temp files from the OS temp directory."""
    import os
    import tempfile
    import time

    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    tmp_dir = tempfile.gettempdir()
    try:
        for fname in os.listdir(tmp_dir):
            fpath = os.path.join(tmp_dir, fname)
            try:
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
                    removed += 1
            except OSError:
                pass
    except Exception:
        pass
    return {"success": True, "removed": removed}


@task(name="cleanup_old_logs")
def cleanup_old_logs(days: int = 30):
    """Mark old behavior logs for deletion."""
    try:
        from database.client import _supabase, _db_available
        if not _db_available or _supabase is None:
            return {"success": False, "error": "DB unavailable"}

        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        _supabase.table("behavior_logs").delete().lt("created_at", cutoff).execute()
        return {"success": True, "cutoff_days": days}
    except Exception as e:
        return {"success": False, "error": str(e)}


@task(name="purge_dead_evidence")
def purge_dead_evidence(max_age_days: int = 90):
    """Remove evidence frames older than max_age_days from static/."""
    import os
    import time
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for base in ["static/screenshots", "static/reports"]:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for f in files:
                p = os.path.join(root, f)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                        removed += 1
                except OSError:
                    pass
    return {"success": True, "removed": removed}
