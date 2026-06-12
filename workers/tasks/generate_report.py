"""
workers/tasks/generate_report.py
=================================
Celery task for async PDF report generation.
"""

from workers.celery_app import task


@task(name="generate_report")
def generate_report_task(session_state: dict, upload_cloudinary: bool = False):
    try:
        from video_ai.risk_engine import generate_report, save_report_pdf
        from api.services.media_storage import MediaStorageService

        report = generate_report(session_state)
        pdf_path = save_report_pdf(report)

        result = {
            "success": True,
            "report": report,
            "pdf_path": pdf_path,
        }

        if upload_cloudinary and pdf_path:
            storage = MediaStorageService()
            upload = storage.upload_report(pdf_path, session_state.get("session_id", "unknown"))
            result["cloudinary"] = upload

        return result
    except Exception as exc:
        return {"success": False, "error": str(exc)}
