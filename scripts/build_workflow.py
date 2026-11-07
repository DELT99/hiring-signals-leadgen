#!/usr/bin/env python3
"""Assemble workflow/hiring-signal-lead-engine.json from src/nodes/*.js.

Usage:  python3 scripts/build_workflow.py
Edit the JS files in src/nodes/, then rebuild and re-import into n8n.
"""
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODES = ROOT / "src" / "nodes"
OUT = ROOT / "workflow" / "hiring-signal-lead-engine.json"

# Stable IDs so rebuilding doesn't create noisy diffs
NS = uuid.UUID("6f1c2a2e-5b1e-4d7a-9c39-2b8f3a1d0e11")
def nid(name):
    return str(uuid.uuid5(NS, name))

LEAD_COLUMNS = [
    "Date Added", "Time Added", "Mode", "Company", "Job Title", "Location",
    "Job Board", "Job URL", "Snippet", "Fit Score", "Fit Reason", "Angle / Tip",
    "Contact Name", "Contact Title", "Contact LinkedIn", "Search Keywords",
    "Run By", "Search Run ID", "Status", "Dedupe Key",
]
RUNLOG_COLUMNS = [
    "Run ID", "Date", "Time", "Mode", "Run By", "Keywords", "Location", "Ranking", "Boards",
    "Target", "Saved", "Skipped", "Low Fit", "Duplicates", "Attempts", "AI Errors",
    "Status", "Last Error",
]

DOC = {"__rl": True, "value": "PASTE_YOUR_GOOGLE_SHEET_ID", "mode": "id"}
def tab(name):
    return {"__rl": True, "value": name, "mode": "name"}

def js(file):
    return (NODES / file).read_text().strip()

def code(name, file, pos):
    return {"parameters": {"jsCode": js(file)}, "id": nid(name), "name": name,
            "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos}

def iff(name, expr, pos):
    return {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [{
                    "id": nid(name + ":cond"), "leftValue": expr, "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        },
        "id": nid(name), "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": pos,
    }

def http(name, url, body_expr, pos, note):
    return {
        "parameters": {
            "method": "POST",
            "url": url,
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body_expr,
            "options": {"response": {"response": {"neverError": True}}, "timeout": 60000},
        },
        "id": nid(name), "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "onError": "continueRegularOutput", "position": pos, "notes": note, "notesInFlow": True,
    }

def sheet_append(name, tab_name, columns, pos):
    return {
        "parameters": {
            "operation": "append",
            "documentId": DOC,
            "sheetName": tab(tab_name),
            "columns": {
                "mappingMode": "defineBelow",
                "value": {c: "={{ $json['%s'] }}" % c for c in columns},
                "matchingColumns": [],
                "schema": [{"id": c, "displayName": c, "required": False, "defaultMatch": False,
                            "canBeUsedToMatch": True, "display": True, "type": "string",
                            "removed": False} for c in columns],
                "attemptToConvertTypes": False,
                "convertFieldsToString": False,
            },
            "options": {},
        },
        "id": nid(name), "name": name, "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5,
        "retryOnFail": True, "maxTries": 3, "waitBetweenTries": 3000, "position": pos,
    }

def dropdown(label, opts, multi=False):
    f = {"fieldLabel": label, "fieldType": "dropdown", "requiredField": True,
         "fieldOptions": {"values": [{"option": o} for o in opts]}}
    if multi:
        f["multiselect"] = True
    return f

form = {
    "parameters": {
        "formTitle": "Hiring Signal Lead Engine",
        "formDescription": "Find companies that are hiring (as sales leads) or jobs that fit you. Results go to the Leads tab of your Google Sheet.",
        "formFields": {"values": [
            dropdown("Mode", ["Find clients (companies that are hiring)", "Find jobs for me"]),
            {"fieldLabel": "Your name", "requiredField": True},
            {"fieldLabel": "Role or skill keywords", "requiredField": True,
             "placeholder": "e.g. Flutter developer, Mobile app developer"},
            {"fieldLabel": "Location", "requiredField": True, "placeholder": "e.g. Lahore / Karachi / Remote"},
            dropdown("Job boards", ["LinkedIn Jobs", "Rozee.pk", "Indeed", "Bayt", "Greenhouse", "Lever", "Any website"], multi=True),
            dropdown("Posted within", ["Past week", "Past 24 hours", "Past month", "Any time"]),
            {"fieldLabel": "What you offer / your CV summary", "fieldType": "textarea", "requiredField": True,
             "placeholder": "Clients mode: what your company sells. Jobs mode: your skills, experience and what you want."},
            dropdown("Ranking method", ["AI ranking (Gemini)", "Keyword ranking (no AI)", "No ranking (save all)"]),
            dropdown("Minimum fit score (1-5)", ["3", "4", "5", "2", "1"]),
            dropdown("Find a decision-maker? (clients mode)", ["Yes", "No"]),
            dropdown("Maximum leads", ["10", "25", "50"]),
        ]},
        "options": {},
    },
    "id": nid("Lead Intake Form"), "name": "Lead Intake Form", "webhookId": nid("form-webhook"),
    "type": "n8n-nodes-base.formTrigger", "typeVersion": 2.2, "position": [0, 0],
}

load = {
    "parameters": {"operation": "read", "documentId": DOC, "sheetName": tab("Leads"), "options": {}},
    "id": nid("Load Existing Leads"), "name": "Load Existing Leads",
    "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5,
    "alwaysOutputData": True, "executeOnce": True, "position": [220, 0],
}

nodes = [
    form,
    load,
    code("Init Run State", "init_run_state.js", [440, 0]),
    code("Build Search Query", "build_search_query.js", [660, 0]),
    iff("Has Queued Candidates?", "={{ $json.useQueue }}", [880, 0]),
    http("Firecrawl Search", "https://api.firecrawl.dev/v2/search",
         "={{ JSON.stringify($json.firecrawlBody) }}", [1100, 160],
         "Header Auth: Authorization = Bearer fc-..."),
    code("Extract Job Candidate", "extract_job_candidate.js", [1320, 0]),
    iff("Has Candidate?", "={{ $json.hasCandidate }}", [1540, 0]),
    iff("Use AI Ranking?", "={{ $json.config.useAi }}", [1760, -40]),
    code("Rule-Based Score", "rule_based_score.js", [1980, 60]),
    code("Build AI Prompt", "build_ai_prompt.js", [1980, -200]),
    http("Gemini Qualify",
         "=https://generativelanguage.googleapis.com/v1beta/models/{{ $json.config.aiModel }}:generateContent",
         "={{ JSON.stringify($json.geminiBody) }}", [2200, -200],
         "Header Auth: x-goog-api-key = your Gemini key"),
    code("Parse AI Result", "parse_ai_result.js", [2420, -200]),
    iff("Qualified?", "={{ $json.qualified }}", [2860, -120]),
    iff("Find Contact?", "={{ $json.needContact }}", [3080, -240]),
    code("Build Contact Query", "build_contact_query.js", [3300, -360]),
    http("Firecrawl Contact Search", "https://api.firecrawl.dev/v2/search",
         "={{ JSON.stringify($json.contactBody) }}", [3520, -360],
         "Same Firecrawl credential"),
    code("Extract Contact", "extract_contact.js", [3740, -360]),
    code("Prepare Row", "prepare_row.js", [3960, -240]),
    sheet_append("Append Lead to Sheet", "Leads", LEAD_COLUMNS, [4180, -240]),
    code("Tag Created", "tag_created.js", [4400, -240]),
    code("Tag Skipped", "tag_missed.js", [3080, 40]),
    code("Tag Missed", "tag_missed.js", [1760, 200]),
    code("Update Counters", "update_counters.js", [4620, 40]),
    iff("Should Continue?", "={{ $json.shouldContinue }}", [4840, 40]),
    code("Run Summary", "run_summary.js", [5060, 160]),
    sheet_append("Append Run Log", "Run Log", RUNLOG_COLUMNS, [5280, 160]),
]

def link(*targets):
    return {"main": [[{"node": t, "type": "main", "index": 0}] for t in targets]}

connections = {
    "Lead Intake Form": link("Load Existing Leads"),
    "Load Existing Leads": link("Init Run State"),
    "Init Run State": link("Build Search Query"),
    "Build Search Query": link("Has Queued Candidates?"),
    "Has Queued Candidates?": link("Extract Job Candidate", "Firecrawl Search"),
    "Firecrawl Search": link("Extract Job Candidate"),
    "Extract Job Candidate": link("Has Candidate?"),
    "Has Candidate?": link("Use AI Ranking?", "Tag Missed"),
    "Use AI Ranking?": link("Build AI Prompt", "Rule-Based Score"),
    "Rule-Based Score": link("Qualified?"),
    "Build AI Prompt": link("Gemini Qualify"),
    "Gemini Qualify": link("Parse AI Result"),
    "Parse AI Result": link("Qualified?"),
    "Qualified?": link("Find Contact?", "Tag Skipped"),
    "Find Contact?": link("Build Contact Query", "Prepare Row"),
    "Build Contact Query": link("Firecrawl Contact Search"),
    "Firecrawl Contact Search": link("Extract Contact"),
    "Extract Contact": link("Prepare Row"),
    "Prepare Row": link("Append Lead to Sheet"),
    "Append Lead to Sheet": link("Tag Created"),
    "Tag Created": link("Update Counters"),
    "Tag Skipped": link("Update Counters"),
    "Tag Missed": link("Update Counters"),
    "Update Counters": link("Should Continue?"),
    "Should Continue?": link("Build Search Query", "Run Summary"),
    "Run Summary": link("Append Run Log"),
}

workflow = {
    "name": "Hiring Signal Lead Engine",
    "nodes": nodes,
    "pinData": {},
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1", "timezone": "Asia/Karachi"},
    "tags": [],
}

OUT.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
(ROOT / "sheets" / "leads_headers.csv").write_text(",".join(LEAD_COLUMNS) + "\n")
(ROOT / "sheets" / "run_log_headers.csv").write_text(",".join(RUNLOG_COLUMNS) + "\n")
print(f"Wrote {OUT.relative_to(ROOT)} ({len(nodes)} nodes)")
