# PortfolioESG → GCP Migration Guide

**Status**: 🔄 Planning  
**Last Updated**: 2026-05-23  
**Owner**: @gabrielcampos  

---

## 📋 Executive Summary

Migrate **PortfolioESG** from **local-only execution** to Google Cloud Platform (GCP), utilizing:
- **Firebase Hosting** for frontend (currently hosted locally via http.server)
- **Cloud Run** for Python analysis engines (replaces manual `./engines/run_all.sh` execution)
- **Cloud Scheduler** for daily automated analysis (replaces manual daily trigger)
- **Google Cloud Storage (GCS)** for data/reports (replaces local `data/` and `html/data/` directories)
- **Firestore** (optional) for real-time data syncing

### Current State
🔴 **Local execution**: You manually run `./engines/run_all.sh` daily  
🔴 **Local frontend**: HTML files served via `python -m http.server` on localhost  
🔴 **No automation**: Manual pipeline execution, no scheduled runs  

### Goals
✅ **Automate daily execution**: Cloud Scheduler triggers Cloud Run every day at 9 AM  
✅ **Keep GitHub as source of truth**: All code stays in GitHub, deployment is automatic  
✅ **Develop locally**: Continue using IDE, deploy to GCP on push to `main`  
✅ **Always-on frontend**: Firebase Hosting serves portfolio dashboard globally (not just localhost)  
✅ **Zero manual intervention**: No more daily `run_all.sh` execution

---

## 🏗️ Target Architecture

```
CURRENT STATE (Local):
  Your Computer → run_all.sh (manual) → html/data/ → http://localhost:8000

FUTURE STATE (GCP Cloud):
┌─────────────────────────────────────────────────────────┐
│                     GitHub Repository                    │
│  (Source of truth: engines/, html/, parameters/)        │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   Cloud Build    GitHub Actions  Local Dev (for testing)
        │              │              │
        └──────────────┴──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   Artifact Registry         │
        │  (Docker image storage)     │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │      Cloud Scheduler        │
        │   (Daily 9:00 AM UTC)       │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │       Cloud Run             │
        │  (Python: run_all.sh via    │
        │   A1, A2, A3, A4, B, C, D)  │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  Google Cloud Storage       │
        │  (html/data/ contents)      │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   Firebase Hosting          │
        │  (Frontend HTML/JS/CSS)     │
        │ + Reads from GCS JSON data  │
        └─────────────────────────────┘
```

---

## 📝 Implementation Phases

### Phase 1: GCP Project Setup & Infrastructure
**Status**: ⏳ Pending  
**Estimated Effort**: 2-3 hours  

#### 1.1 Create GCP Project
- [ ] Navigate to [Google Cloud Console](https://console.cloud.google.com/)
- [ ] Create new project: `portfolioesg` (or similar)
- [ ] Note the Project ID (used in Cloud Run, GCS bucket names, etc.)

#### 1.2 Enable Required APIs
- [ ] Cloud Run API
- [ ] Cloud Scheduler API
- [ ] Cloud Storage API
- [ ] Artifact Registry API
- [ ] Firebase Management API
- [ ] Secret Manager API (for storing API keys)

#### 1.3 Create Service Accounts
- [ ] **Cloud Run service account**: For running analysis engines
  - [ ] Grant: `roles/storage.admin` (read/write to GCS)
  - [ ] Grant: `roles/secretmanager.secretAccessor` (read API keys from Secret Manager)
- [ ] **Cloud Build service account**: For deploying frontend
  - [ ] Grant: `roles/firebase.admin` (deploy to Firebase Hosting)
  - [ ] Grant: `roles/storage.admin` (read from GCS, write to GCS)

#### 1.4 Configure Local Environment
- [ ] Install Google Cloud SDK: `gcloud init`
- [ ] Authenticate: `gcloud auth login`
- [ ] Set default project: `gcloud config set project PROJECT_ID`
- [ ] Verify: `gcloud projects describe PROJECT_ID`

#### 1.5 Create GCS Bucket
```bash
gsutil mb gs://portfolioesg-data-YYYYMMDD
gsutil versioning set on gs://portfolioesg-data-YYYYMMDD
```
- [ ] Bucket name: `portfolioesg-data-{timestamp}`
- [ ] Location: `us-central1` (or closest region)
- [ ] Storage class: Standard
- [ ] Versioning: Enabled (for data recovery)

#### 1.6 Create Secrets in Secret Manager
- [ ] Store sensitive config (API keys, credentials) in Secret Manager
- [ ] Example: `yahoo-finance-key`, `gcp-service-account-json`

---

### Phase 2: Backend Containerization
**Status**: ⏳ Pending  
**Estimated Effort**: 3-4 hours  

#### 2.1 Create Dockerfile
- [ ] Create `Dockerfile` in project root
- [ ] Base image: `python:3.11-slim`
- [ ] Copy `engines/`, `shared_tools/`, `parameters/` directories
- [ ] Install dependencies from `requirements.txt`
- [ ] Set entrypoint to run main analysis script

**Key Considerations**:
- Image size should be <500MB (faster cold starts)
- Use multi-stage builds to optimize layers
- Cache pip dependencies efficiently

#### 2.2 Create Docker Entrypoint Script
- [ ] Create `entrypoint.sh` (runs inside container)
- [ ] Download latest code from GCS (or clone from GitHub)
- [ ] Run analysis engines (A1, A2, A3, A4 in sequence)
- [ ] Upload results to GCS
- [ ] Exit with status code

#### 2.3 Create .dockerignore
- [ ] Exclude `data/`, `backups/`, `.git/`, `__pycache__/`
- [ ] Keep image lean and deployment-ready

#### 2.4 Test Docker Image Locally
- [ ] Build: `docker build -t portfolioesg:latest .`
- [ ] Run: `docker run --rm portfolioesg:latest`
- [ ] Verify all engines execute without errors
- [ ] Check output files are created correctly

**Mock Testing**:
- [ ] Create mock GCS credentials for local testing
- [ ] Test file I/O (read from GCS, write to GCS)

---

### Phase 3: Cloud Run Deployment
**Status**: ⏳ Pending  
**Estimated Effort**: 2 hours  

#### 3.1 Push Image to Artifact Registry
```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
docker tag portfolioesg:latest us-central1-docker.pkg.dev/PROJECT_ID/docker-repo/portfolioesg:latest
docker push us-central1-docker.pkg.dev/PROJECT_ID/docker-repo/portfolioesg:latest
```
- [ ] Create Artifact Registry repository
- [ ] Configure Docker auth
- [ ] Push image

#### 3.2 Deploy to Cloud Run
- [ ] Create Cloud Run service: `portfolioesg-engine`
- [ ] Select image from Artifact Registry
- [ ] Set memory: 2GB (adjust based on analysis size)
- [ ] Set timeout: 30 minutes (analysis may take 10-20 min)
- [ ] Set service account: Cloud Run service account (from Phase 1.3)
- [ ] Set environment variables:
  - `GCS_BUCKET`: `gs://portfolioesg-data-{timestamp}`
  - `ANALYSIS_MODE`: `FULL` (or `QUICK` for testing)

#### 3.3 Test Cloud Run Deployment
```bash
# Get service URL
gcloud run services list
# Test invocation
curl -X POST https://portfolioesg-engine-XXXXX.run.app/analyze \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```
- [ ] Invoke Cloud Run service manually
- [ ] Check logs: `gcloud run services logs read portfolioesg-engine`
- [ ] Verify output in GCS bucket

---

### Phase 4: Scheduling & Automation
**Status**: ⏳ Pending  
**Estimated Effort**: 1.5 hours  

#### 4.1 Configure Cloud Scheduler
- [ ] Create Cloud Scheduler job: `portfolioesg-daily-analysis`
- [ ] Frequency: `0 9 * * *` (Daily at 9:00 AM UTC)
- [ ] Target: HTTP POST to Cloud Run service URL
- [ ] Auth: Use service account from Phase 1.3
- [ ] Payload (optional): `{"trigger": "scheduler"}`

#### 4.2 Test Scheduler
- [ ] Manually trigger job in Cloud Console
- [ ] Wait for execution and verify in Cloud Run logs
- [ ] Check GCS bucket for new output files

#### 4.3 GitHub Actions Integration (Optional)
- [ ] Create `.github/workflows/deploy-cloud-run.yml`
- [ ] Trigger: On push to `main` branch
- [ ] Action: Build Docker image → Push to Artifact Registry
- [ ] Auto-deploy to Cloud Run

---

### Phase 5: Code Modifications for GCS
**Status**: ⏳ Pending  
**Estimated Effort**: 2-3 hours  

#### 5.1 Update File I/O Paths
Current behavior: `run_all.sh` executes locally, writes to `data/` and `html/data/` directories  
New behavior: Cloud Run executes in container, writes to GCS bucket

**Files to Modify**:
- [ ] Engines that write output (A2, A3, A4, B series, C, D scripts)
- [ ] Change from writing to local filesystem to GCS bucket
- [ ] Example: `html/data/pipeline_latest.json` → `gs://portfolioesg-data-XXXXX/html/data/pipeline_latest.json`

**Pattern**:
```python
# Old: local filesystem
output_file = "html/data/pipeline_latest.json"
with open(output_file, 'w') as f:
    json.dump(data, f)

# New: GCS
from google.cloud import storage
bucket = storage.Client().bucket(os.getenv('GCS_BUCKET'))
blob = bucket.blob('html/data/pipeline_latest.json')
blob.upload_from_string(json.dumps(data))
```

#### 5.2 Update Data Loading
- [ ] Modify code to read input data from GCS (if needed for second run, historical comparison)
- [ ] Handle missing files gracefully (first run has no historical data)

#### 5.3 Add GCS Helper Module
- [ ] Create `shared_tools/gcs_utils.py` with helper functions:
  - `upload_to_gcs(local_file, gcs_path)`
  - `download_from_gcs(gcs_path, local_file)`
  - `list_gcs_files(gcs_prefix)`

#### 5.4 Test Locally with Mock GCS
- [ ] Install `google-cloud-storage` in `requirements.txt`
- [ ] Test file uploads/downloads locally using GCS emulator or mock credentials

---

### Phase 6: Frontend Migration to Firebase
**Status**: ⏳ Pending  
**Estimated Effort**: 3-4 hours  

#### 6.1 Firebase Project Setup
- [ ] Create Firebase project (or link existing GCP project)
- [ ] Enable Firebase Hosting
- [ ] Enable Firebase Authentication (Google Sign-In)
- [ ] Configure authorized domains

#### 6.2 Update Frontend to Read from GCS
Current behavior: Frontend loads from local `html/data/` files  
New behavior: Frontend fetches from GCS bucket

**Files to Modify**:
- [ ] `html/js/api.js` (or similar) — Update data loading
- [ ] `html/js/auth.js` — Update authentication to Firebase

**Pattern**:
```javascript
// Old: local file
fetch('data/portfolio.json')
  .then(r => r.json())
  .then(data => displayPortfolio(data));

// New: GCS with signed URL
const signedUrl = await getSignedUrl('data/portfolio.json');
fetch(signedUrl)
  .then(r => r.json())
  .then(data => displayPortfolio(data));
```

#### 6.3 Implement GCS Signed URLs (Backend)
- [ ] Add Cloud Function or Cloud Run endpoint: `/api/signed-url?path=...`
- [ ] Returns signed URL that frontend can use to fetch file
- [ ] Signed URLs expire after 1 hour (security)

**Alternative**: Make GCS bucket publicly readable
- ⚠️ Security consideration: Only if data is non-sensitive

#### 6.4 Update Firebase Authentication
- [ ] Replace current auth.js with Firebase SDK
- [ ] Configure Google Sign-In button
- [ ] Store user session in Firebase Auth
- [ ] Protect frontend routes (require login)

#### 6.5 Test Locally
- [ ] Use Firebase emulator: `firebase emulators:start`
- [ ] Test auth flow locally
- [ ] Test data loading from GCS

---

### Phase 7: Firebase Hosting Deployment
**Status**: ⏳ Pending  
**Estimated Effort**: 1-2 hours  

#### 7.1 Configure Firebase CLI
```bash
npm install -g firebase-tools
firebase login
firebase init hosting
```
- [ ] Initialize Firebase in project root
- [ ] Select hosting directory: `html/`
- [ ] Configure `firebase.json`

#### 7.2 Update firebase.json
```json
{
  "hosting": {
    "public": "html",
    "cleanUrls": true,
    "rewrites": [
      {
        "source": "/**",
        "destination": "/index.html"
      }
    ]
  }
}
```
- [ ] Redirect all routes to index.html (SPA support)
- [ ] Enable clean URLs (remove .html extensions)

#### 7.3 Deploy Frontend
```bash
firebase deploy --only hosting
```
- [ ] Deploy to Firebase Hosting
- [ ] Verify at default URL: `https://PROJECT_ID.web.app`
- [ ] Test authentication and data loading

#### 7.4 Configure Custom Domain (Optional)
- [ ] Add custom domain in Firebase Console
- [ ] Point DNS to Firebase Hosting
- [ ] SSL/TLS certificate auto-provisioned

#### 7.5 Setup Auto-Deployment
- [ ] Create `.github/workflows/deploy-firebase.yml`
- [ ] Trigger: On push to `main` branch
- [ ] Action: Deploy to Firebase Hosting using `firebase-tools`

---

### Phase 8: End-to-End Testing & Optimization
**Status**: ⏳ Pending  
**Estimated Effort**: 2-3 hours  

#### 8.1 Full Integration Test
- [ ] Manually trigger Cloud Scheduler job
- [ ] Monitor Cloud Run execution logs
- [ ] Verify output in GCS bucket
- [ ] Refresh frontend → Should show latest data
- [ ] Test on different devices/browsers

#### 8.2 Performance Optimization
- [ ] Monitor Cloud Run memory usage (adjust if needed)
- [ ] Check Docker image size (target: <500MB)
- [ ] Optimize analysis runtime (A1 + A2 + A3 + A4 should complete in <30 min)
- [ ] Cache dependencies in Cloud Run (warm up image)

#### 8.3 Cost Analysis
- [ ] Enable billing alerts in GCP Console
- [ ] Estimate monthly cost:
  - Cloud Run: ~$1-5/month (daily execution)
  - Cloud Scheduler: Free (< 3 jobs)
  - GCS: ~$0.50-2/month (storage + requests)
  - Firebase Hosting: Free tier usually sufficient
  - **Total estimated**: $5-10/month

#### 8.4 Error Handling & Rollback
- [ ] Setup Cloud Monitoring alerts (Cloud Run failures)
- [ ] Configure notifications (email/Slack on failures)
- [ ] Document rollback procedure (redeploy previous Docker image)

---

### Phase 9: Monitoring & Documentation
**Status**: ⏳ Pending  
**Estimated Effort**: 2 hours  

#### 9.1 Setup Cloud Monitoring
- [ ] Create Cloud Monitoring dashboard:
  - Cloud Run execution time
  - Cloud Run failure rate
  - GCS storage usage
  - Firebase analytics
- [ ] Set up alerts:
  - Cloud Run execution fails
  - Execution takes > 30 minutes
  - GCS storage exceeds threshold

#### 9.2 Configure Logging
- [ ] Enable Cloud Logging for Cloud Run
- [ ] Create log filters for errors
- [ ] Archive logs to GCS for long-term retention

#### 9.3 Documentation
- [ ] Update `README.md` with GCP deployment instructions
- [ ] Create `docs/GCP_SETUP.md` with detailed setup steps
- [ ] Create `docs/TROUBLESHOOTING.md` with common issues
- [ ] Document environment variables and configuration

#### 9.4 Update Project README
- [ ] Remove AWS references
- [ ] Add GCP deployment quick start
- [ ] Link to GCP documentation files

---

## 🔑 Key Decisions & Rationale

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Backend Service** | Cloud Run | Supports containerized workloads, pay-per-invocation, simple deployment, 30-min timeout sufficient |
| **Scheduling** | Cloud Scheduler | Native GCP integration, reliable, free for first 3 jobs, cron-like interface |
| **Data Storage** | GCS + Firestore (optional) | GCS for large files (reports, historical data), Firestore optional for real-time DB |
| **Frontend Hosting** | Firebase Hosting | Integrated with GCP, free tier, SSL by default, auto-deployment |
| **Container Registry** | Artifact Registry | Modern GCP service, supports Docker/OCI images, integrated with Cloud Build |
| **CI/CD** | GitHub Actions + Cloud Build | GitHub Actions for frontend, Cloud Build for backend (both free within limits) |
| **Secrets** | Secret Manager | Native GCP, secure, integrates with Cloud Run |

---

## 💰 Cost Estimation

### Monthly Breakdown (Estimated)

| Service | Usage | Cost |
|---------|-------|------|
| **Cloud Run** | 1 daily execution × 20 min × 2GB RAM | $0.50 |
| **Cloud Scheduler** | 1 job, 30 executions/month | Free* |
| **GCS Storage** | 100 MB stored | $0.05 |
| **GCS Requests** | ~500 requests/month | Free (within free tier) |
| **Firebase Hosting** | <1 GB storage, <5 GB bandwidth | Free |
| **Artifact Registry** | <1 GB stored | Free (within free tier) |
| **Secret Manager** | 1 secret, < 10k requests | Free |
| **Cloud Logging** | <100 MB logs | Free (within free tier) |
| **Total** | | **$0.55-1.50/month** |

*Cloud Scheduler: First 3 jobs free, then $0.10/job after. For 1 job, cost remains free.

### Annual Estimate
- **Production (stable)**: $10-20/year
- **Development (testing)**: $20-50/year (higher due to testing runs)

---

## ⚠️ Known Challenges & Solutions

| Challenge | Impact | Solution |
|-----------|--------|----------|
| **Python dependencies size** | Docker image > 500MB (slow cold starts) | Use slim base image, multi-stage builds, remove unused deps |
| **File I/O refactoring** | Significant code changes needed | Create `gcs_utils.py` helper module, test locally first |
| **First run has no historical data** | Analysis may fail if it expects historical files | Handle missing files gracefully, provide seed data if needed |
| **Cloud Run timeout** | Analysis takes > 30 minutes | Monitor performance, optimize bottlenecks in A3 (GA algorithm) |
| **GCS bucket naming** | Bucket names must be globally unique | Use timestamp/random suffix: `portfolioesg-data-20260523` |
| **Secret rotation** | API keys may expire | Use Secret Manager, rotate regularly, automate if possible |
| **Cost overruns** | Unexpected billing | Set up billing alerts, monitor Cloud Run memory usage |

---

## 📊 Progress Tracking

### Overall Status
- **Phase 1**: ⏳ Not Started
- **Phase 2**: ⏳ Not Started
- **Phase 3**: ⏳ Not Started
- **Phase 4**: ⏳ Not Started
- **Phase 5**: ⏳ Not Started
- **Phase 6**: ⏳ Not Started
- **Phase 7**: ⏳ Not Started
- **Phase 8**: ⏳ Not Started
- **Phase 9**: ⏳ Not Started

**Overall Progress**: 0% (0 of 9 phases complete)

### Detailed Checklist by Phase

See checklist items above (marked with `[ ]` for pending, `[x]` for completed).

---

## 📚 Reference Documentation

- [GCP Cloud Run Docs](https://cloud.google.com/run/docs)
- [Firebase Hosting Docs](https://firebase.google.com/docs/hosting)
- [Cloud Scheduler Docs](https://cloud.google.com/scheduler/docs)
- [Google Cloud Storage Docs](https://cloud.google.com/storage/docs)
- [Artifact Registry Docs](https://cloud.google.com/artifact-registry/docs)
- [Secret Manager Docs](https://cloud.google.com/secret-manager/docs)

---

## 🤝 Notes for AI Assistants

**IMPORTANT CURRENT STATE**:
- Project is **local-only**, NOT on AWS or any cloud platform
- User manually runs `./engines/run_all.sh` daily
- Frontend is served locally via `python -m http.server`
- Goal: Automate this via GCP Cloud Run + Cloud Scheduler

This document is designed to be:
1. **Self-contained**: Each phase includes all required steps and context
2. **Updateable**: Track progress by marking checklist items as complete
3. **Trackable**: Use status indicators (⏳ Not Started, 🔄 In Progress, ✅ Complete)
4. **Debuggable**: Document challenges and solutions for future reference
5. **Referenceable**: Include direct links and code examples

When updating this doc:
- Update phase status at the top
- Mark completed checklist items
- Document any deviations from the plan
- Add new challenges discovered
- Update progress percentage

---

## 📝 Update History

| Date | Version | Changes | Author |
|------|---------|---------|--------|
| 2026-05-23 | 1.0 | Initial migration plan | @gabrielcampos |

