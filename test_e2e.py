"""End-to-end test script for v3 pipeline — checks LinkedIn scrape results, 
then runs Snov.io contact discovery and email enrichment."""
import time
import requests
import json

BASE = "http://localhost:8000"

def check_status():
    r = requests.get(f"{BASE}/api/status")
    return r.json()["status"]

def wait_for_idle(timeout=300):
    """Wait until pipeline status returns to idle."""
    start = time.time()
    while time.time() - start < timeout:
        status = check_status()
        print(f"  Status: {status}")
        if status == "idle":
            return True
        time.sleep(10)
    print("  TIMEOUT waiting for idle")
    return False

# Step 3: Wait for LinkedIn scrape to finish
print("=" * 60)
print("STEP 3: Waiting for LinkedIn scrape to complete...")
print("=" * 60)
wait_for_idle(timeout=300)

# Check leads
r = requests.get(f"{BASE}/api/leads")
data = r.json()
print(f"\nLeads found: {data['total']}")
if data["leads"]:
    for i, lead in enumerate(data["leads"][:10]):
        print(f"  {i+1}. {lead.get('company_name', '?')} | {lead.get('website', '?')} | {lead.get('industry', '?')}")
else:
    print("  No leads found. LinkedIn scrape may have returned empty results.")
    print("  This could be due to the Apify actor not finding results for these keywords.")
    print("  Skipping remaining steps.")
    exit(0)

# Step 4: Snov.io contact discovery
print("\n" + "=" * 60)
print("STEP 4: Starting Snov.io contact discovery...")
print("=" * 60)
r = requests.post(f"{BASE}/api/contacts")
print(f"  Response: {r.status_code} {r.json()}")
wait_for_idle(timeout=300)

# Step 5: Email enrichment waterfall
print("\n" + "=" * 60)
print("STEP 5: Starting email enrichment waterfall...")
print("=" * 60)
r = requests.post(f"{BASE}/api/enrich/email")
print(f"  Response: {r.status_code} {r.json()}")
wait_for_idle(timeout=300)

# Step 6: Check Snov.io status
print("\n" + "=" * 60)
print("STEP 6: Checking Snov.io auth status...")
print("=" * 60)
r = requests.get(f"{BASE}/api/snov/status")
print(f"  Snov.io: {r.json()}")

# Step 7: Export
print("\n" + "=" * 60)
print("STEP 7: Exporting to Excel...")
print("=" * 60)
r = requests.get(f"{BASE}/api/export")
if r.status_code == 200:
    with open("test_final_leads.xlsx", "wb") as f:
        f.write(r.content)
    print("  Exported to test_final_leads.xlsx")
else:
    print(f"  Export failed: {r.status_code} {r.text}")

print("\n" + "=" * 60)
print("END-TO-END TEST COMPLETE")
print("=" * 60)
