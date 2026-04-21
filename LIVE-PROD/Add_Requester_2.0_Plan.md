# Add Requester 2.0 - Streaming Progress (Fast Implementation)

**Goal:** Add real-time progress tracking to existing Add Requester bulk upload. No new pages, minimal changes.

**Timeline:** 2-3 hours

**Approach:** Server-Sent Events (SSE) streaming from existing processor

---

## What We're Adding

**Current flow:**
```
Upload CSV → POST /process → Wait 20 min → Get all results at end
```

**New flow:**
```
Upload CSV → POST /process/stream → Get progress events every 2 sec → Final results
```

---

## Files to Modify (Only 3 Files!)

### **1. `app.py` - Add SSE endpoint** (~50 lines)

Add ONE new endpoint after existing `/process`:

```python
from fastapi.responses import StreamingResponse
import json

@app.post("/process/stream", include_in_schema=False)
async def process_stream(
    file: UploadFile = File(...),
    created_by: str = Form(default="IRS PIN Operator"),
):
    """
    Stream processing progress as Server-Sent Events.
    
    Event format:
    data: {"type": "progress", "current": 5, "total": 100, "status": "Created", "pin": "123456789"}
    data: {"type": "complete", "summary": {...}, "results": [...]}
    """
    async def generate():
        try:
            # Parse rows
            rows = parse_input_bytes(file.filename, await file.read())
            total = len(rows)
            
            yield f"data: {json.dumps({'type': 'init', 'total': total})}\n\n"
            
            # Process rows one by one
            results = []
            for idx, row in enumerate(rows):
                # Call modified process_single_row (see below)
                result = process_single_row_sync(row, app.state.client, created_by)
                results.append(result)
                
                # Send progress event
                progress_event = {
                    "type": "progress",
                    "current": idx + 1,
                    "total": total,
                    "row": {
                        "seid": result.get("seid"),
                        "status": result.get("status"),
                        "pin": result.get("generated_pin"),
                    }
                }
                yield f"data: {json.dumps(progress_event)}\n\n"
            
            # Send complete event
            summary = _build_summary(results)
            complete_event = {
                "type": "complete",
                "summary": summary,
                "results": results
            }
            yield f"data: {json.dumps(complete_event)}\n\n"
        
        except Exception as e:
            error_event = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


def process_single_row_sync(row, client, created_by):
    """
    Process ONE row synchronously, return result dict.
    
    This is a simplified version of process_rows() that handles 1 row.
    Copy logic from processor.py process_rows() loop body.
    """
    # TODO: Extract single-row logic from processor.py
    # For now, call existing process_rows with 1 row
    result = process_rows([row], client=client, created_by=created_by, write_output=False)
    return result.row_results[0].to_dict()
```

---

### **2. `frontend.py` - Add streaming UI** (~100 lines)

Find the bulk upload section (around line 800-900) and ADD this:

```python
# After existing bulk upload button, add streaming option

st.markdown("---")
st.markdown("### 🚀 Upload with Live Progress (Beta)")

uploaded_file_stream = st.file_uploader(
    "Upload CSV/Excel for streaming progress",
    type=["csv", "xlsx", "xls"],
    key="add_bulk_stream_uploader"
)

if st.button("Upload with Live Progress", type="secondary", disabled=not uploaded_file_stream):
    st.session_state.streaming_active = True
    st.session_state.stream_file = uploaded_file_stream
    st.rerun()

# Streaming progress section
if st.session_state.get("streaming_active"):
    uploaded_file = st.session_state.stream_file
    
    # Progress placeholders
    progress_bar = st.progress(0)
    status_text = st.empty()
    metrics_cols = st.columns(4)
    results_table = st.empty()
    
    # Counters
    total = 0
    current = 0
    created = 0
    failed = 0
    activated = 0
    deactivated = 0
    
    try:
        # Open SSE connection
        response = requests.post(
            f"{BACKEND_URL}/process/stream",
            files={"file": (uploaded_file.name, uploaded_file.getvalue())},
            stream=True,
            timeout=7200  # 2 hours
        )
        
        results = []
        
        # Read SSE stream
        for line in response.iter_lines():
            if not line:
                continue
            
            # Parse SSE event
            if line.startswith(b"data: "):
                event_data = json.loads(line[6:])
                event_type = event_data.get("type")
                
                if event_type == "init":
                    total = event_data["total"]
                    status_text.info(f"Processing {total} rows...")
                
                elif event_type == "progress":
                    current = event_data["current"]
                    row_data = event_data["row"]
                    
                    # Update counters
                    if row_data["status"] == "Created":
                        created += 1
                    elif row_data["status"] == "Failed":
                        failed += 1
                    elif row_data["status"] == "Activated":
                        activated += 1
                    elif row_data["status"] == "Deactivated":
                        deactivated += 1
                    
                    # Update UI
                    progress_bar.progress(current / total)
                    status_text.info(f"Processing row {current}/{total}... ({row_data['seid']})")
                    
                    metrics_cols[0].metric("Total", total)
                    metrics_cols[1].metric("Created", created)
                    metrics_cols[2].metric("Failed", failed)
                    metrics_cols[3].metric("Progress", f"{int(current/total*100)}%")
                
                elif event_type == "complete":
                    results = event_data["results"]
                    summary = event_data["summary"]
                    
                    progress_bar.progress(1.0)
                    status_text.success(f"✅ Completed! Created: {summary.get('Created', 0)}, Failed: {summary.get('Failed', 0)}")
                    
                    # Show results table
                    render_bulk_result({"results": results, "summary": summary})
                    
                    # Clear streaming state
                    del st.session_state.streaming_active
                    del st.session_state.stream_file
                    
                    break
                
                elif event_type == "error":
                    st.error(f"Error: {event_data['message']}")
                    del st.session_state.streaming_active
                    break
    
    except Exception as e:
        st.error(f"Streaming failed: {str(e)}")
        del st.session_state.streaming_active
```

---

### **3. `processor.py` - Extract single-row function** (~50 lines)

Add helper function at top of file:

```python
def process_single_row_for_stream(
    row: ParsedRow,
    client: ConnectQAClient,
    created_by: str,
) -> dict:
    """
    Process ONE row, return simplified result for streaming.
    
    This is a lightweight version for SSE - doesn't write to DB/files.
    """
    # Copy main logic from process_rows loop (line 378+)
    # But skip:
    # - batch_id
    # - registry writes
    # - payload_list
    # - output file writes
    
    # Return simple dict:
    return {
        "row_number": row.row_number,
        "seid": row.seid,
        "action": row.contact_status,
        "status": "Created",  # or Failed, Activated, etc.
        "generated_pin": "123456789",  # actual PIN
        "notes": ["..."],
        "matched_site_name": "...",
    }
```

**OR simpler:** Just call existing `process_rows([row], ...)` with 1 row at a time. Slower but works immediately.

---

## That's It! 3 Files, ~200 Lines

### **Testing (10 min):**

1. Restart containers:
   ```bash
   docker compose up -d --build
   ```

2. Upload 10-row CSV with "Upload with Live Progress"

3. Should see:
   - Progress bar moving
   - "Processing row 3/10..."
   - Metrics updating live
   - Final results table

---

## Fallback: If Streaming Fails

Keep existing button! Users can use old synchronous upload (still works with 1200s timeout).

**Two buttons:**
- "Upload CSV" - existing sync (reliable, no progress)
- "Upload with Live Progress" - new streaming (experimental)

---

## Production-Ready Checklist (30 min)

- [ ] Test with 10-row CSV - works?
- [ ] Test with 100-row CSV - progress updates?
- [ ] Test with connection drop - shows error?
- [ ] Old upload button still works?
- [ ] Add note: "Beta feature - use standard upload if issues"

---

## If You Have 3 Hours

**Hour 1:** Add `/process/stream` endpoint to `app.py`

**Hour 2:** Add streaming UI to `frontend.py`

**Hour 3:** Test + deploy

---

## Minimal MVP (1 hour version)

Skip single-row optimization. Just do:

```python
# app.py
@app.post("/process/stream")
async def process_stream(file: UploadFile = File(...)):
    async def generate():
        rows = parse_input_bytes(file.filename, await file.read())
        
        for idx, row in enumerate(rows):
            # Call existing process_rows with 1 row (slower but works)
            result = process_rows([row], client=app.state.client, write_output=False)
            
            yield f"data: {json.dumps({'current': idx+1, 'total': len(rows)})}\n\n"
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

**Frontend:** Just show progress bar, no metrics. Simple.

---

## Questions?

1. Want 1-hour MVP or 3-hour full version?
2. Keep old upload button as fallback? (YES recommended)
3. Show live metrics or just progress bar?

**Recommendation:** 3-hour full version with fallback. Production-ready with minimal risk.
