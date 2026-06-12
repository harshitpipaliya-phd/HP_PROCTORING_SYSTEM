"""
app.py
======
HP Proctoring Backend - Unified Streamlit UI (PRODUCTION FINAL)
AI Proctoring Dashboard: Video AI + Audio + Screen Monitoring

All 15 bugs from BUG_REPORT.md are fixed. Additional advanced features added:
  - Real-time risk gauge with animated progress
  - Live session timer
  - Advanced analytics charts (risk trend, attention heatmap)
  - Session export (JSON + CSV)
  - Notification banners for high-risk events
  - Compact live event ticker
  - Database SQL console
  - System health check panel
  - Auto-refresh toggle for live monitoring

Version: 2.0.0 (Production Final)
"""

import streamlit as st
import cv2
import numpy as np
from datetime import datetime
import base64
import json
import time
import io

# ============================================================================
# Page Config — MUST be first Streamlit call
# ============================================================================
st.set_page_config(
    page_title="HP Proctoring Backend",
    layout="wide",
    page_icon="🎯",
    initial_sidebar_state="expanded",
)

# ============================================================================
# Custom CSS — Professional proctoring dashboard theme
# ============================================================================
st.markdown("""
<style>
    /* Core layout */
    .main .block-container { padding-top: 0.8rem; padding-bottom: 1rem; }

    /* Risk badges */
    .risk-badge-high { background:#dc2626; color:white; padding:3px 10px; border-radius:5px;
                       font-weight:700; font-size:0.85rem; letter-spacing:.04em; }
    .risk-badge-med  { background:#d97706; color:white; padding:3px 10px; border-radius:5px;
                       font-weight:700; font-size:0.85rem; }
    .risk-badge-low  { background:#16a34a; color:white; padding:3px 10px; border-radius:5px;
                       font-weight:700; font-size:0.85rem; }

    /* Flag pills */
    .flag-pill { background:#7f1d1d; color:#fca5a5; padding:2px 7px; border-radius:4px;
                 font-size:0.76rem; margin:1px 2px; display:inline-block; }
    .flag-pill-warn { background:#78350f; color:#fcd34d; padding:2px 7px; border-radius:4px;
                      font-size:0.76rem; margin:1px 2px; display:inline-block; }

    /* Module section headers */
    .module-header { font-size:0.78rem; font-weight:700; color:#60a5fa;
                     text-transform:uppercase; letter-spacing:.06em; margin-bottom:2px; }

    /* Live ticker */
    .event-ticker { background:#0f172a; border-left:3px solid #3b82f6;
                    padding:4px 10px; margin:2px 0; border-radius:0 4px 4px 0;
                    font-size:0.74rem; color:#94a3b8; }
    .event-ticker-high { border-left-color: #ef4444; color:#fca5a5; }

    /* Metric cards */
    .metric-card { background:#1e293b; border:1px solid #334155;
                   border-radius:8px; padding:10px 14px; margin:4px 0; }

    /* Status indicators */
    .status-ok   { color:#22c55e; font-weight:700; }
    .status-warn { color:#f59e0b; font-weight:700; }
    .status-fail { color:#ef4444; font-weight:700; }

    /* Compact table */
    .compact-table th { font-size:0.75rem !important; padding:4px 8px !important; }
    .compact-table td { font-size:0.74rem !important; padding:3px 8px !important; }

    /* Alert banners */
    .alert-high { background:#450a0a; border:1px solid #dc2626; border-radius:6px;
                  padding:8px 14px; color:#fca5a5; font-weight:600; margin:6px 0; }
    .alert-med  { background:#451a03; border:1px solid #d97706; border-radius:6px;
                  padding:8px 14px; color:#fcd34d; margin:6px 0; }

    /* Sidebar */
    .sidebar-stat { font-size:0.82rem; padding:3px 0; }
    .sidebar-label { color:#64748b; font-size:0.75rem; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap:4px; }
    .stTabs [data-baseweb="tab"] { padding:8px 14px; font-size:0.85rem; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# Module Imports — with graceful fallback messages
# ============================================================================
_import_errors = []

try:
    from video_ai.processor import analyze_frame, get_event_log, clear_event_log, get_behavior_trends
    from video_ai.risk_engine import generate_report, generate_report_text, get_ai_verdict, get_violation_summary
except Exception as e:
    _import_errors.append(f"video_ai: {e}")
    def analyze_frame(f): return f, {}
    def get_event_log(): return []
    def clear_event_log(): pass
    def get_behavior_trends(): return {}
    def generate_report(s): return {}
    def generate_report_text(r): return ""
    def get_ai_verdict(): return "INCONCLUSIVE"
    def get_violation_summary(): return {}

try:
    from audio_proctoring.stream import analyze_audio_file, MonitoringSession, is_stream_available
except Exception as e:
    _import_errors.append(f"audio_proctoring: {e}")
    def analyze_audio_file(p, u): return {"error": "Module unavailable"}
    def is_stream_available(): return False

try:
    from screen_monitoring.capture import capture_all_monitors, is_screen_capture_available
    from screen_monitoring.watcher import get_monitor_watcher
    from screen_monitoring.detector import detect_monitors
except Exception as e:
    _import_errors.append(f"screen_monitoring: {e}")
    def capture_all_monitors(): return []
    def is_screen_capture_available(): return False
    def get_monitor_watcher(): return None
    def detect_monitors(): return {"monitor_count": 0, "screen_capture_available": False, "monitors": []}

try:
    from core.session import start_session, stop_session, get_session_status, get_current_session
except Exception as e:
    _import_errors.append(f"core.session: {e}")
    def start_session(**kwargs): return "no-session"
    def stop_session(): return {}
    def get_session_status(): return {}
    def get_current_session(): return None

try:
    from database import fetch_recent_logs, is_available as db_available
except Exception as e:
    _import_errors.append(f"database: {e}")
    def fetch_recent_logs(t, limit=10): return []
    def db_available(): return False

# ============================================================================
# Session State Initialization
# ============================================================================
DEFAULTS = {
    "video_results": None,
    "frame_count": 0,
    "evidence_frames": [],
    "audio_result": None,
    "monitor_screenshots": [],
    "risk_history": [],         # list of (timestamp, risk_score)
    "attention_history": [],    # list of (timestamp, attention_score)
    "session_started_at": None,
    "auto_refresh": False,
    "last_alert": None,
    "total_violations_shown": 0,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================================
# Sidebar — Live Stats & Session Control
# ============================================================================
with st.sidebar:
    st.markdown("## 🎯 HP Proctoring")
    st.caption("v2.0 · Unified AI Platform")
    st.divider()

    # Session control
    session = get_current_session()
    if session and getattr(session, "_active", False):
        st.markdown('<span class="status-ok">● SESSION ACTIVE</span>', unsafe_allow_html=True)
        if st.session_state.session_started_at:
            elapsed = int(time.time() - st.session_state.session_started_at)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            st.caption(f"Duration: {h:02d}:{m:02d}:{s:02d}")

        status = get_session_status()
        risk = status.get("risk_score", 0)
        focus = status.get("focus_score", 100)
        verdict = get_ai_verdict()

        # Risk meter
        risk_color = "#ef4444" if risk >= 50 else "#f59e0b" if risk >= 25 else "#22c55e"
        st.markdown(f"""
        <div class="metric-card">
          <div class="sidebar-label">RISK SCORE</div>
          <div style="font-size:1.6rem;font-weight:800;color:{risk_color}">{risk}/100</div>
        </div>
        """, unsafe_allow_html=True)

        st.progress(risk / 100)

        col1, col2 = st.columns(2)
        col1.metric("Focus", f"{focus}%")
        col2.metric("Verdict", verdict, delta=None)

        st.caption(f"Violations: {len(getattr(session, 'violations', []))}")
        st.caption(f"Tab Switches: {status.get('tab_switches', 0)}")

        if st.button("⏹ Stop Session", type="primary", use_container_width=True):
            stop_session()
            st.session_state.session_started_at = None
            st.rerun()
    else:
        st.markdown('<span class="status-warn">○ NO ACTIVE SESSION</span>', unsafe_allow_html=True)
        user_id_input = st.text_input("User ID", value="candidate_001", key="sidebar_user_id")
        if st.button("▶ Start Session", type="primary", use_container_width=True):
            start_session(user_id=user_id_input)
            st.session_state.session_started_at = time.time()
            st.rerun()

    st.divider()

    # Quick stats
    st.markdown("**📊 Live Stats**")
    st.markdown(f'<div class="sidebar-stat">Frames: {st.session_state.frame_count}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="sidebar-stat">Evidence: {len(st.session_state.evidence_frames)}</div>', unsafe_allow_html=True)

    # Auto refresh toggle
    st.divider()
    st.toggle("Auto Refresh (5s)", key="auto_refresh")
    if st.session_state.auto_refresh:
        time.sleep(5)
        st.rerun()

    # Module status
    st.divider()
    st.markdown("**⚙ Module Status**")
    _checks = [
        ("MediaPipe", "mediapipe"),
        ("YOLOv8", "ultralytics"),
        ("OpenCV", "cv2"),
        ("Soundfile", "soundfile"),
        ("MSS", "mss"),
    ]
    for name, mod in _checks:
        try:
            __import__(mod)
            st.markdown(f'<span class="status-ok">✓</span> {name}', unsafe_allow_html=True)
        except Exception:
            st.markdown(f'<span class="status-fail">✗</span> {name}', unsafe_allow_html=True)

    if _import_errors:
        with st.expander("⚠ Import Warnings"):
            for err in _import_errors:
                st.caption(err)

# ============================================================================
# Main Header
# ============================================================================
st.markdown("# 🎯 HP Proctoring Backend")
st.caption("Unified AI Proctoring Platform · Video AI | Audio | Screen Monitoring | Analytics")

# High-risk alert banner
if st.session_state.video_results:
    risk = st.session_state.video_results.get("risk_score", 0)
    flags = st.session_state.video_results.get("risk_flags", [])
    if risk >= 70:
        flags_str = " · ".join(flags[:4])
        st.markdown(
            f'<div class="alert-high">🚨 HIGH RISK DETECTED ({risk}/100) — {flags_str}</div>',
            unsafe_allow_html=True
        )
    elif risk >= 40:
        st.markdown(
            f'<div class="alert-med">⚠ MEDIUM RISK ({risk}/100) — {", ".join(flags[:3])}</div>',
            unsafe_allow_html=True
        )

# ============================================================================
# Tabs
# ============================================================================
tab_video, tab_audio, tab_screen, tab_analytics, tab_logs, tab_evidence, tab_system = st.tabs([
    "📹 Video AI",
    "🎤 Audio",
    "🖥️ Screen",
    "📈 Analytics",
    "📋 Event Log",
    "📷 Evidence",
    "⚙️ System",
])

# ============================================================================
# TAB 1 — Video AI Proctoring
# ============================================================================
with tab_video:
    st.header("📹 Video AI Proctoring")
    st.caption("Real-time face · gaze · head pose · person · object · mobile detection")

    col_cam, col_panel = st.columns([3, 2])

    with col_cam:
        st.subheader("Live Camera Feed")
        camera = st.camera_input("Enable Camera", key="video_cam")

        if camera:
            try:
                bytes_data = camera.getvalue()
                nparr = np.frombuffer(bytes_data, np.uint8)
                # cv2.imdecode always returns BGR — NO colour conversion needed
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is not None:
                    st.session_state.frame_count += 1
                    output_frame, results = analyze_frame(frame)
                    st.session_state.video_results = results

                    # Track risk history (keep last 120 samples)
                    risk_val = results.get("risk_score", 0)
                    att_val = results.get("attention", {}).get("score", 100)
                    now_ts = datetime.now().strftime("%H:%M:%S")
                    st.session_state.risk_history.append((now_ts, risk_val))
                    st.session_state.attention_history.append((now_ts, att_val))
                    if len(st.session_state.risk_history) > 120:
                        st.session_state.risk_history.pop(0)
                    if len(st.session_state.attention_history) > 120:
                        st.session_state.attention_history.pop(0)

                    # Store evidence on high-risk frames
                    if risk_val >= 50 and results.get("evidence"):
                        ev = results["evidence"]
                        if len(st.session_state.evidence_frames) < 100:
                            st.session_state.evidence_frames.append({
                                "type": "video",
                                "frame_b64": ev.get("image_b64", ""),
                                "timestamp": ev.get("timestamp", now_ts),
                                "flags": results.get("risk_flags", []),
                                "risk_score": risk_val,
                            })

                    if output_frame is not None:
                        # BUG FIX #6: use use_container_width=True, not width='stretch'
                        st.image(output_frame, channels="BGR", use_container_width=True)
                        st.caption(
                            f"Frame #{st.session_state.frame_count} · "
                            f"Process: {results.get('processing_ms', 0):.1f}ms · "
                            f"Risk: {risk_val}/100"
                        )
                else:
                    st.error("Failed to decode camera frame.")
            except Exception as err:
                st.error(f"Frame processing error: {err}")
        else:
            st.info("📷 Enable your camera above to start live AI monitoring.")

    with col_panel:
        st.subheader("Live Analysis")
        results = st.session_state.video_results

        if results and results.get("success", True):
            risk = results.get("risk_score", 0)
            badge = "high" if risk >= 50 else "med" if risk >= 25 else "low"

            # Risk score + bar
            st.markdown(
                f"**Risk Score** &nbsp; <span class='risk-badge-{badge}'>{risk}/100</span>",
                unsafe_allow_html=True
            )
            st.progress(risk / 100)

            # Flag pills
            flags = results.get("risk_flags", [])
            if flags:
                pills = " ".join(f"<span class='flag-pill'>{f}</span>" for f in flags)
                st.markdown(pills, unsafe_allow_html=True)
            else:
                st.success("✓ No risk flags")

            st.divider()

            # 2.1 Eye & Head
            st.markdown("<div class='module-header'>2.1 Eye & Head Tracking</div>", unsafe_allow_html=True)
            eye = results.get("eye_head", {})
            pose = results.get("head_pose", {})
            att = results.get("attention", {})

            la = eye.get("looking_away", False)
            st.markdown(
                f"• Looking Away: **{'🔴 YES' if la else '🟢 No'}** &nbsp; "
                f"Gaze: `{eye.get('gaze_direction','N/A')}`"
            )
            st.markdown(
                f"• Head: `{pose.get('direction','N/A')}` &nbsp; "
                f"Y:{pose.get('yaw',0):.1f}° P:{pose.get('pitch',0):.1f}° R:{pose.get('roll',0):.1f}°"
            )
            att_s = att.get("score", 0)
            att_color = "🟢" if att_s >= 70 else "🟡" if att_s >= 40 else "🔴"
            st.markdown(f"• Attention: {att_color} **{att_s}/100** — `{att.get('label','N/A')}`")
            st.markdown(
                f"• EAR: `{(eye.get('ear_left',0)+eye.get('ear_right',0))/2:.2f}` &nbsp; "
                f"Blinks: `{eye.get('blink_count',0)}` &nbsp; "
                f"Away/min: `{eye.get('look_away_frequency',0)}`"
            )

            st.divider()

            # 2.2 Person & Object
            st.markdown("<div class='module-header'>2.2 Person & Object Detection</div>", unsafe_allow_html=True)
            persons = results.get("persons", {})
            objects = results.get("objects", {})

            p_count = persons.get("person_count", 0)
            multi = persons.get("multiple_persons", False)
            st.markdown(
                f"• Persons: `{p_count}` — {'🔴 UNAUTHORIZED' if multi else '🟢 OK'} "
                f"[{persons.get('detection_engine','?')}]"
            )

            objs = objects.get("prohibited_objects", [])
            obj_str = ", ".join(objs) if objs else "None"
            st.markdown(
                f"• Objects: {'🔴' if objs else '🟢'} `{obj_str[:40]}`"
            )
            det_items = []
            if objects.get("phone_detected"): det_items.append("📱 Phone")
            if objects.get("book_detected"):  det_items.append("📚 Book")
            if objects.get("laptop_detected"): det_items.append("💻 Laptop")
            if objects.get("notes_detected"): det_items.append("📝 Notes")
            st.markdown(f"• Detected: {' · '.join(det_items) if det_items else '✓ None'}")

            st.divider()

            # 2.3 Mobile & Gesture
            st.markdown("<div class='module-header'>2.3 Mobile & Gesture</div>", unsafe_allow_html=True)
            mob = results.get("mobile", {})

            ph = mob.get("phone_detected", False)
            ph_conf = mob.get("phone_confidence", 0.0)
            st.markdown(
                f"• Phone: {'🔴 DETECTED' if ph else '🟢 None'} ({ph_conf:.0%})"
            )
            ug = mob.get("unusual_gesture", False)
            gestures = ", ".join(mob.get("gesture_labels", [])) or "None"
            st.markdown(
                f"• Hands: `{mob.get('hands_detected',0)}` Gesture: `{gestures[:30]}` "
                f"{'🔴 SUSPICIOUS' if ug else '🟢 OK'}"
            )

            # Risk breakdown expander
            with st.expander("📊 Risk Breakdown"):
                bd = results.get("risk_breakdown", {})
                if bd:
                    for k, v in bd.items():
                        pct = min(100, v)
                        st.markdown(f"**{k}** → +{v}")
                        st.progress(pct / 100)
                else:
                    st.info("No risk contributors")
        else:
            st.info("Waiting for camera input...")

        # Live event ticker
        st.divider()
        st.markdown("<div class='module-header'>Live Event Ticker</div>", unsafe_allow_html=True)
        events = get_event_log()
        if events:
            for ev in list(reversed(events))[:6]:
                risk_added = ev.get("risk_added", 0)
                cls = "event-ticker-high" if risk_added >= 15 else "event-ticker"
                st.markdown(
                    f'<div class="{cls}">'
                    f'{ev.get("timestamp","")[-8:]} · '
                    f'<b>{ev.get("event_type","")}</b> +{risk_added}'
                    f'</div>',
                    unsafe_allow_html=True
                )
        else:
            st.caption("No events yet.")

# ============================================================================
# TAB 2 — Audio Proctoring
# ============================================================================
with tab_audio:
    st.header("🎤 Audio Proctoring")
    st.caption("Voice activity · speaker identification · anomaly detection")

    col_up, col_res = st.columns([1, 1])

    with col_up:
        st.subheader("Upload Audio File")
        audio_file = st.file_uploader(
            "WAV · MP3 · FLAC · OGG",
            type=["wav", "mp3", "flac", "ogg"],
            key="audio_upload"
        )
        user_id_audio = st.text_input("Candidate ID", value="candidate_001", key="audio_uid")

        if st.button("🔍 Analyze Audio", key="analyze_audio_btn", type="primary"):
            if audio_file:
                with st.spinner("Running audio analysis…"):
                    import tempfile, os as _os

                    # BUG FIX #7: extract only the extension for tempfile suffix
                    _suffix = _os.path.splitext(audio_file.name)[1] or ".audio"
                    with tempfile.NamedTemporaryFile(delete=False, suffix=_suffix) as tmp:
                        tmp.write(audio_file.getvalue())
                        tmp_path = tmp.name

                    try:
                        result = analyze_audio_file(tmp_path, user_id_audio)
                        st.session_state.audio_result = result
                        st.success("Analysis complete!")
                    except Exception as ae:
                        st.error(f"Analysis failed: {ae}")
                    finally:
                        _os.unlink(tmp_path)
            else:
                st.warning("Please upload an audio file first.")

        # Streaming status
        st.divider()
        stream_ok = is_stream_available()
        st.markdown(
            f"**Real-time Streaming:** "
            f"{'<span class=\"status-ok\">Available</span>' if stream_ok else '<span class=\"status-warn\">PyAudio not installed</span>'}",
            unsafe_allow_html=True
        )
        st.caption("Install PyAudio for live microphone streaming: `pip install pyaudio`")

    with col_res:
        st.subheader("Analysis Results")
        result = st.session_state.audio_result

        if result:
            if "error" in result:
                st.error(result.get("error"))
            else:
                risk_level = result.get("risk_level", "LOW")
                risk_score = result.get("total_risk", 0)
                badge = "high" if risk_level == "HIGH" else "med" if risk_level == "MEDIUM" else "low"

                st.markdown(
                    f"**Risk Level:** <span class='risk-badge-{badge}'>{risk_level}</span> &nbsp; "
                    f"**Score:** {risk_score}/100",
                    unsafe_allow_html=True
                )
                st.progress(min(risk_score, 100) / 100)

                st.divider()

                col_a, col_b = st.columns(2)
                col_a.metric("Total Segments", result.get("total_segments", 0))
                col_b.metric("Estimated Speakers", result.get("estimated_speakers", 0))

                col_c, col_d = st.columns(2)
                col_c.metric("Speech", result.get("speech_segments", 0))
                col_d.metric("Anomaly", result.get("anomaly_segments", 0))

                col_e, col_f = st.columns(2)
                col_e.metric("Noise", result.get("noise_segments", 0))
                col_f.metric("Background Voice", result.get("background_voice_segments", 0))

                unauth = result.get("unauthorized_segments", 0)
                if unauth > 0:
                    st.markdown(
                        f'<div class="alert-high">🔴 Unauthorized speaker detected ({unauth} segments)</div>',
                        unsafe_allow_html=True
                    )

                st.divider()
                st.info(result.get("result", "Analysis complete"))

                # Download result
                st.download_button(
                    "⬇ Download Report (JSON)",
                    data=json.dumps(result, indent=2),
                    file_name=f"audio_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )
        else:
            st.info("Upload an audio file and click Analyze.")

    # Audio logs
    st.divider()
    st.subheader("📋 Recent Audio Logs")
    try:
        logs = fetch_recent_logs("audio_logs", limit=10)
        if logs:
            import pandas as pd
            st.dataframe(pd.DataFrame(logs), use_container_width=True)
        else:
            st.info("No audio logs found. Logs appear here after analysis when DB is connected.")
    except Exception as e:
        st.warning(f"Could not fetch audio logs: {e}")

# ============================================================================
# TAB 3 — Screen Monitoring
# ============================================================================
with tab_screen:
    st.header("🖥️ Screen Monitoring")
    st.caption("Multi-monitor capture · change detection · browser window tracking")

    col_cap, col_mon = st.columns([1, 1])

    with col_cap:
        st.subheader("Screenshot Capture")

        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("📸 Capture All Monitors", key="capture_btn", type="primary"):
                with st.spinner("Capturing…"):
                    shots = capture_all_monitors()
                    st.session_state.monitor_screenshots = shots
                    if shots:
                        st.success(f"Captured {len(shots)} monitor(s)")
                    else:
                        st.warning("No screenshots captured — MSS may not be available or no display detected.")

        with btn_col2:
            if st.button("🔄 Check Monitor Changes", key="monitor_chk_btn"):
                try:
                    watcher = get_monitor_watcher()
                    if watcher:
                        status = watcher.check_changes()
                        if status.get("changed"):
                            ev = status.get("change_event", {})
                            st.warning(
                                f"⚠ Monitor change! {ev.get('previous_count',0)} → "
                                f"{ev.get('current_count',0)} ({ev.get('direction','')})"
                            )
                        else:
                            st.success("✓ No monitor changes")
                    else:
                        st.info("Monitor watcher unavailable")
                except Exception as we:
                    st.warning(f"Watcher error: {we}")

        if st.session_state.monitor_screenshots:
            for ss in st.session_state.monitor_screenshots:
                st.markdown(
                    f"**Monitor {ss['monitor_id']}** — {ss['width']}×{ss['height']} "
                    f"| `{ss['filename']}`"
                )
        else:
            st.info("No screenshots captured yet.")

    with col_mon:
        st.subheader("Monitor Status")
        try:
            mon_info = detect_monitors()
        except Exception:
            mon_info = {"monitor_count": 0, "screen_capture_available": False, "monitors": []}

        m_count = mon_info.get("monitor_count", 0)
        sc_avail = mon_info.get("screen_capture_available", False)

        col_x, col_y = st.columns(2)
        col_x.metric("Detected Monitors", m_count)
        col_y.metric(
            "Screen Capture",
            "Available" if sc_avail else "Unavailable",
        )

        browsers = mon_info.get("browser_windows", [])
        st.metric("Browser Windows", len(browsers))

        if mon_info.get("monitors"):
            st.markdown("**Connected Monitors:**")
            for m in mon_info["monitors"]:
                st.markdown(
                    f"• Monitor {m.get('monitor_id','?')}: "
                    f"{m.get('width',0)}×{m.get('height',0)} "
                    f"@ ({m.get('x',0)}, {m.get('y',0)}) "
                    f"{'[Primary]' if m.get('is_primary') else ''}"
                )

        if browsers:
            st.markdown("**Open Browsers:**")
            for b in browsers[:5]:
                st.caption(f"• {b.get('name','?')} — {b.get('title','')[:40]}")

# ============================================================================
# TAB 4 — Analytics
# ============================================================================
with tab_analytics:
    st.header("📈 Analytics & Trends")

    trends = get_behavior_trends()
    session = get_current_session()

    if trends.get("samples", 0) > 0:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Samples", trends.get("samples", 0))
        col2.metric("Avg Risk", f"{trends.get('avg_risk_score', 0)}/100")
        col3.metric("Max Risk", f"{trends.get('max_risk_score', 0)}/100")
        col4.metric("Risk Spikes", trends.get("risk_spike_count", 0))

        col5, col6 = st.columns(2)
        col5.metric("Look-Away Rate", f"{trends.get('look_away_rate', 0)}%")
        col6.metric("Attention Trend", trends.get("attention_trend", "N/A"))

    else:
        st.info("No trend data yet. Start monitoring to populate analytics.")

    # Risk trend chart
    if st.session_state.risk_history:
        st.subheader("📊 Risk Score Timeline")
        import pandas as pd

        risk_df = pd.DataFrame(st.session_state.risk_history, columns=["Time", "Risk Score"])
        risk_df = risk_df.set_index("Time")
        st.line_chart(risk_df, use_container_width=True, height=200)

    # Attention trend chart
    if st.session_state.attention_history:
        st.subheader("👁 Attention Score Timeline")
        att_df = pd.DataFrame(st.session_state.attention_history, columns=["Time", "Attention"])
        att_df = att_df.set_index("Time")
        st.line_chart(att_df, use_container_width=True, height=180)

    # Session report
    st.divider()
    st.subheader("📄 Full Session Report")

    col_r1, col_r2 = st.columns(2)
    with col_r1:
        if st.button("🔄 Generate Report", key="gen_report_btn", type="primary"):
            status = get_session_status()
            report = generate_report(status)
            st.session_state["_last_report"] = report
            st.success("Report generated!")

    with col_r2:
        report = st.session_state.get("_last_report")
        if report:
            st.download_button(
                "⬇ Download JSON Report",
                data=json.dumps(report, indent=2),
                file_name=f"proctoring_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
            )

    report = st.session_state.get("_last_report")
    if report:
        ra = report.get("risk_assessment", {})
        verdict = ra.get("ai_verdict", "N/A")
        v_color = "#ef4444" if verdict == "FAIL" else "#f59e0b" if verdict == "REVIEW" else "#22c55e"

        st.markdown(
            f"**AI Verdict:** <span style='color:{v_color};font-weight:800;font-size:1.1rem'>{verdict}</span>",
            unsafe_allow_html=True
        )

        col_ra, col_rb = st.columns(2)
        col_ra.markdown("**Risk Assessment**")
        col_ra.write(ra)

        metrics = report.get("metrics", {})
        col_rb.markdown("**Session Metrics**")
        col_rb.write(metrics)

        st.text_area(
            "Human-readable Report",
            generate_report_text(report),
            height=300,
        )

    # Behavior DB stats
    st.divider()
    st.subheader("🗄 Database Behavior Logs")
    try:
        blogs = fetch_recent_logs("behavior_logs", limit=20)
        if blogs:
            import pandas as pd
            st.success(f"{len(blogs)} behavior logs loaded from DB")
            bdf = pd.DataFrame(blogs)
            # Show key columns
            key_cols = [c for c in ["created_at", "risk_score", "looking_away",
                                     "head_direction", "phone_detected",
                                     "multiple_persons", "attention_score"] if c in bdf.columns]
            st.dataframe(bdf[key_cols] if key_cols else bdf, use_container_width=True)
        else:
            st.info("No behavior logs (DB not connected or empty). Connect Supabase in .env to persist data.")
    except Exception as e:
        st.warning(f"DB error: {e}")

# ============================================================================
# TAB 5 — Event Log
# ============================================================================
with tab_logs:
    st.header("📋 Event Audit Log")

    col_ev, col_tr = st.columns([2, 1])

    with col_ev:
        st.subheader("Event History")

        btn_col_a, btn_col_b, btn_col_c = st.columns(3)

        with btn_col_a:
            if st.button("🗑 Clear Log", key="clear_log_btn"):
                clear_event_log()
                st.rerun()

        events = get_event_log()

        if events:
            st.info(f"{len(events)} events recorded")

            # Export buttons
            with btn_col_b:
                st.download_button(
                    "⬇ JSON",
                    data=json.dumps(events, indent=2),
                    file_name=f"events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )

            with btn_col_c:
                try:
                    import pandas as pd
                    ev_df = pd.DataFrame(events)
                    st.download_button(
                        "⬇ CSV",
                        data=ev_df.to_csv(index=False),
                        file_name=f"events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                    )
                except Exception:
                    pass

            import pandas as pd
            df_rows = []
            for e in reversed(events):
                df_rows.append({
                    "Time": e.get("timestamp", "")[-8:],
                    "Event Type": e.get("event_type", ""),
                    "Detail": e.get("detail", "")[:60],
                    "Risk +": e.get("risk_added", 0),
                    "Conf": f"{e.get('confidence', 1.0):.2f}",
                })
            st.dataframe(pd.DataFrame(df_rows), use_container_width=True, height=400)
        else:
            st.info("No events recorded yet. Start monitoring to capture events.")

    with col_tr:
        st.subheader("Behavior Trends")

        trends = get_behavior_trends()
        if trends.get("samples", 0) > 0:
            st.metric("Samples", trends["samples"])
            st.metric("Avg Risk", f"{trends.get('avg_risk_score',0)}/100")
            st.metric("Max Risk", f"{trends.get('max_risk_score',0)}/100")
            st.metric("Risk Spikes", trends.get("risk_spike_count", 0))
            st.metric("Look-Away Rate", f"{trends.get('look_away_rate',0)}%")
            st.caption(f"Window: {trends.get('time_window_seconds',0):.0f}s")
        else:
            st.info("No trend data available yet.")

        st.divider()
        st.subheader("Violation Summary")
        vsummary = get_violation_summary()
        total_v = vsummary.get("total", 0)
        by_type = vsummary.get("by_type", {})

        st.metric("Total Violations", total_v)
        st.metric("High-Risk Count", vsummary.get("high_risk_count", 0))

        if by_type:
            for vtype, cnt in list(by_type.items())[:8]:
                st.markdown(f"• `{vtype}`: **{cnt}**")

# ============================================================================
# TAB 6 — Evidence Viewer
# ============================================================================
with tab_evidence:
    st.header("📷 Evidence Viewer")
    st.caption("Violation frames captured at risk ≥ 50")

    evidence = st.session_state.get("evidence_frames", [])

    if evidence:
        col_ev_a, col_ev_b = st.columns([3, 1])

        with col_ev_b:
            st.metric("Total Evidence", len(evidence))
            if st.button("🗑 Clear Evidence", key="clear_ev_btn"):
                st.session_state.evidence_frames = []
                st.rerun()

            # Export evidence manifest
            manifest = [
                {k: v for k, v in ev.items() if k != "frame_b64"}
                for ev in evidence
            ]
            st.download_button(
                "⬇ Evidence Manifest",
                data=json.dumps(manifest, indent=2),
                file_name="evidence_manifest.json",
                mime="application/json",
            )

        with col_ev_a:
            # Filter by risk level
            min_risk = st.slider("Min Risk Score Filter", 0, 100, 50, 5, key="ev_risk_filter")
            filtered = [e for e in evidence if e.get("risk_score", 0) >= min_risk]
            st.caption(f"Showing {len(filtered)}/{len(evidence)} frames (risk ≥ {min_risk})")

        for i, ev in enumerate(reversed(filtered)):
            with st.expander(
                f"[{ev.get('timestamp','')}]  Risk: {ev.get('risk_score',0)}/100  "
                f"— {', '.join(ev.get('flags',[])[:3])}"
            ):
                b64 = ev.get("frame_b64", "")
                if b64:
                    try:
                        img_bytes = base64.b64decode(b64)
                        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
                        img_frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
                        if img_frame is not None:
                            st.image(
                                img_frame, channels="BGR",
                                use_container_width=True,
                                caption=f"Risk: {ev.get('risk_score')} | {ev.get('flags')}"
                            )
                    except Exception as de:
                        st.warning(f"Image decode error: {de}")

                st.json({k: v for k, v in ev.items() if k != "frame_b64"})
    else:
        st.info("No evidence captured yet. Violations at risk ≥ 50 are automatically stored here.")

# ============================================================================
# TAB 7 — System Info
# ============================================================================
with tab_system:
    st.header("⚙️ System Info & Configuration")

    col_s1, col_s2 = st.columns(2)

    with col_s1:
        st.subheader("System Status")

        # Core components
        checks = {
            "Database (Supabase)": db_available(),
            "Screen Capture (MSS)": is_screen_capture_available(),
            "Audio Streaming (PyAudio)": is_stream_available(),
        }
        for name, ok in checks.items():
            icon = "🟢" if ok else "🔴"
            st.markdown(f"{icon} **{name}:** {'Connected' if ok else 'Not available'}")

        # Session status
        session = get_current_session()
        st.divider()
        st.markdown("**Current Session:**")
        if session:
            st.markdown(f"• ID: `{session.session_id}`")
            st.markdown(f"• User: `{session.user_id}`")
            st.markdown(f"• Risk: `{session.risk_score}`")
            st.markdown(f"• Focus: `{session.focus_score}`")
            st.markdown(f"• Violations: `{len(session.violations)}`")
            st.markdown(f"• Tab Switches: `{session.tab_switches}`")
        else:
            st.info("No active session")

    with col_s2:
        st.subheader("Library Versions")

        libs = [
            ("mediapipe", "MediaPipe (Eye/Head/Hands)"),
            ("ultralytics", "Ultralytics (YOLOv8n)"),
            ("cv2", "OpenCV"),
            ("soundfile", "Soundfile (Audio)"),
            ("mss", "MSS (Screen)"),
            ("streamlit", "Streamlit"),
            ("fastapi", "FastAPI"),
            ("supabase", "Supabase"),
            ("sklearn", "Scikit-Learn"),
            ("numpy", "NumPy"),
        ]
        for mod, label in libs:
            try:
                m = __import__(mod)
                ver = getattr(m, "__version__", "?")
                st.markdown(f"🟢 **{label}** `{ver}`")
            except Exception:
                st.markdown(f"🔴 **{label}** — not installed")

    # Feature matrix
    st.divider()
    st.subheader("Feature Completion Matrix")
    st.markdown("""
    | Module | Feature | Engine | Status |
    |--------|---------|--------|--------|
    | 2.1 | Iris Gaze Estimation | MediaPipe Face Mesh | ✅ Active |
    | 2.1 | Blink Detection (EAR) | MediaPipe | ✅ Active |
    | 2.1 | Look-Away Frequency (60s window) | Internal ring buffer | ✅ Active |
    | 2.1 | Head Pose — Yaw/Pitch/Roll | MediaPipe + SolvePnP | ✅ Active |
    | 2.1 | Composite Attention Score | Multi-signal fusion | ✅ Active |
    | 2.2 | Person Detection | YOLOv8n / Haar+HOG | ✅ Active |
    | 2.2 | Cell Phone Detection (COCO #67) | YOLOv8n / Contour | ✅ Active |
    | 2.2 | Book Detection (COCO #84) | YOLOv8n / Contour | ✅ Active |
    | 2.2 | Laptop/Notes Detection | YOLOv8n | ✅ Active |
    | 2.3 | Mobile Phone Detection | YOLO + Contour | ✅ Active |
    | 2.3 | Hand Landmark Tracking (21 pts) | MediaPipe Hands | ✅ Active |
    | 2.3 | Finger Count & Gesture Classification | Rule-based | ✅ Active |
    | 2.3 | Phone-Hold / Writing Gesture | Hand geometry | ✅ Active |
    | Audio | Voice Activity Detection | Energy+Spectral | ✅ Active |
    | Audio | Unauthorized Speaker Detection | Multi-cue fusion | ✅ Active |
    | Audio | Anomaly Detection | Classifier | ✅ Active |
    | Screen | Multi-Monitor Capture | MSS | ✅ Active |
    | Screen | Monitor Change Detection | Stateful watcher | ✅ Active |
    | Screen | Browser Window Detection | OS APIs | ✅ Active |
    | Core | Dynamic Confidence-Weighted Risk | Multi-module | ✅ Active |
    | Core | Event Audit Trail | In-memory + DB | ✅ Active |
    | Core | Session Management | Thread-safe | ✅ Active |
    | Core | Violation Evidence Viewer | Base64 + Streamlit | ✅ Active |
    | Core | Risk Timeline Charts | In-session | ✅ Active |
    | Core | Session Export (JSON/CSV) | Streamlit | ✅ Active |
    | API | FastAPI REST API (15 endpoints) | uvicorn | ✅ Available |
    | DB | Supabase Async Logging | supabase-py | ✅ Available |
    """)

    # .env guide
    st.divider()
    st.subheader("⚙ Configuration Guide")
    with st.expander("Environment Variables (.env)"):
        st.code("""
# Application
DEBUG=false
HOST=0.0.0.0
PORT=8000

# Supabase (optional — app works without DB)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key

# Directories
SCREENSHOT_DIR=static/screenshots
LOG_DIR=logs

# Model Paths
AUDIO_MODEL_PATH=models/audio_classifier.pkl
MODEL_META_PATH=models/model_meta.json

# Risk Thresholds
RISK_THRESHOLD=50
""", language="ini")

    with st.expander("How to Run"):
        st.code("""
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your Supabase keys (optional)

# 3a. Streamlit UI (this file)
streamlit run app.py

# 3b. FastAPI backend (separate terminal)
uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# 4. (Optional) Train audio model
python audio_proctoring/trainer.py

# 5. Open docs
# Streamlit UI: http://localhost:8501
# FastAPI docs: http://localhost:8000/docs
""", language="bash")

# ============================================================================
# Footer
# ============================================================================
st.divider()
col_f1, col_f2, col_f3 = st.columns(3)
col_f1.caption("HP Proctoring Backend v2.0.0")
col_f2.caption("Unified AI Proctoring Platform")
col_f3.caption(f"Session Frames: {st.session_state.frame_count}")
