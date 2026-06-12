"""
api/services/report_builder.py
================================
Post-session report assembly service.

Builds the full structured report, generates the ReportLab PDF,
and optionally uploads to Cloudinary.

Audit fixes addressed:
  - PDF via ReportLab (not wkhtmltopdf)
  - Signed Cloudinary URLs generated on-demand (not stored)
  - behavior_flags mapped to HP competency model
"""

import io
import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional


class ReportBuilder:
    """
    Assembles the final session report from a ProctoringSession.
    Pure: takes session state, returns report dict + optional PDF bytes.
    """

    def build(self, session_state: Dict[str, Any]) -> Dict[str, Any]:
        """Build a full report dict from session state."""
        from video_ai.risk_engine import generate_report
        return generate_report(session_state)

    def build_pdf(self, report: Dict[str, Any]) -> Optional[bytes]:
        """Generate a ReportLab PDF from a report dict."""
        from video_ai.risk_engine import generate_report_pdf
        return generate_report_pdf(report)

    def build_hp_payload(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Build HP-compatible competency payload from report."""
        from video_ai.risk_engine import build_hp_webhook_payload
        return build_hp_webhook_payload(report)

    def save_pdf(self, report: Dict[str, Any], directory: str = "static/reports") -> Optional[str]:
        """
        Save PDF to disk and return its path.
        Returns None if PDF generation fails.
        """
        pdf_bytes = self.build_pdf(report)
        if not pdf_bytes:
            return None
        os.makedirs(directory, exist_ok=True)
        sid = report.get("session_id", "session")
        ts = int(time.time())
        path = os.path.join(directory, f"report_{sid}_{ts}.pdf")
        with open(path, "wb") as f:
            f.write(pdf_bytes)
        return path

    def upload_pdf(self, pdf_path: str, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Upload PDF to Cloudinary.
        Returns signed URL info (generated on-demand, never stored).
        """
        from api.services.media_storage import MediaStorageService
        storage = MediaStorageService()
        result = storage.upload_report(pdf_path, session_id)
        return result

    def deliver_hp_webhook(self, report: Dict[str, Any], webhook_url: str) -> bool:
        """
        POST the HP payload to the org's webhook URL.
        Returns True on HTTP 2xx.
        """
        if not webhook_url:
            return False
        try:
            import httpx
            payload = self.build_hp_payload(report)
            secret = os.getenv("HP_WEBHOOK_SECRET", "")
            headers = {"Content-Type": "application/json"}
            if secret:
                import hmac
                import hashlib
                body = json.dumps(payload).encode()
                sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
                headers["X-HP-Signature"] = sig
            resp = httpx.post(webhook_url, json=payload, headers=headers, timeout=10)
            return resp.is_success
        except Exception as e:
            print(f"[report_builder] HP webhook delivery failed: {e}")
            return False

    def full_pipeline(
        self,
        session_state: Dict[str, Any],
        upload_cloudinary: bool = False,
        deliver_webhook: bool = False,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full post-session report pipeline:
          1. Build report
          2. Generate PDF
          3. Optionally upload to Cloudinary
          4. Optionally deliver to HP webhook
          Returns result dict.
        """
        report = self.build(session_state)
        pdf_path = self.save_pdf(report)
        result = {
            "success": True,
            "report": report,
            "pdf_path": pdf_path,
            "cloudinary": None,
            "webhook_delivered": False,
        }

        if upload_cloudinary and pdf_path:
            sid = session_state.get("session_id", "unknown")
            result["cloudinary"] = self.upload_pdf(pdf_path, sid)

        if deliver_webhook and webhook_url:
            result["webhook_delivered"] = self.deliver_hp_webhook(report, webhook_url)

        return result
