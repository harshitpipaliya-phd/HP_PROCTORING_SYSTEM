"""
api/schemas/
============

Pydantic request and response schemas for the HP Proctoring API.
"""

from api.schemas.session import (
StartRequest,
StartRequestV2,
StopRequest,
SessionStatusResponse,
)

from api.schemas.detection import (
VideoDetectRequest,
TabSwitchRequest,
AudioDetectRequest,
RiskWeightsRequest,
RiskWeightsLoadRequest,
AutoScreenshotRequest,
)

from api.schemas.candidate import (
CandidateEnrollRequest,
CandidateResponse,
)

from api.schemas.admin import (
OrganizationRequest,
ExamRequest,
OrganizationResponse,
ExamResponse,
SessionFlagRequest,
SessionFlagResponse,
UserCreateRequest,
UserResponse,
CandidateUpdateRequest,
)

from api.schemas.event import (
BrowserEventRequest,
FaceAbsentEventRequest,
WindowBlurEventRequest,
FullscreenExitEventRequest,
EventRecordedResponse,
EventListResponse,
EventSummary,
)

from api.schemas.report import (
ReportResponse,
ReportSummary,
ReportListResponse,
HPWebhookPayloadResponse,
GenerateReportRequest,
ReportFilterRequest,
)

**all** = [
# Session
"StartRequest",
"StartRequestV2",
"StopRequest",
"SessionStatusResponse",

```
# Detection
"VideoDetectRequest",
"TabSwitchRequest",
"AudioDetectRequest",
"RiskWeightsRequest",
"RiskWeightsLoadRequest",
"AutoScreenshotRequest",

# Candidate
"CandidateEnrollRequest",
"CandidateResponse",

# Admin
"OrganizationRequest",
"ExamRequest",
"OrganizationResponse",
"ExamResponse",
"SessionFlagRequest",
"SessionFlagResponse",
"UserCreateRequest",
"UserResponse",
"CandidateUpdateRequest",

# Events
"BrowserEventRequest",
"FaceAbsentEventRequest",
"WindowBlurEventRequest",
"FullscreenExitEventRequest",
"EventRecordedResponse",
"EventListResponse",
"EventSummary",

# Reports
"ReportResponse",
"ReportSummary",
"ReportListResponse",
"HPWebhookPayloadResponse",
"GenerateReportRequest",
"ReportFilterRequest",
```

]
